"""Move the application's own database from the local SQLite dev file onto a
real server (PostgreSQL or MySQL/MariaDB).

Copies app_dev.db -> whatever DATABASE_URL points at. This is the app's OWN
data (units, submissions, evaluations); it has nothing to do with Moodle's
database, which is read-only and never written by this project.

    # 1. point .env at the target server
    DATABASE_URL=postgresql+psycopg://user:pass@host:5432/btek

    # 2. dry run first -- reports what WOULD be copied, writes nothing
    .venv/Scripts/python.exe scripts/migrate_app_db.py --dry-run

    # 3. do it
    .venv/Scripts/python.exe scripts/migrate_app_db.py

WHY IDs ARE PRESERVED
---------------------
Rows are inserted with their existing primary keys, because Evaluation and
CriterionResult reference Criterion.id, and portal deep links
(portal/_deep_link.py) put submission ids in the URL. Renumbering would
break both. That means the target's identity sequences must be advanced past
the copied ids afterwards, which _resync_sequences() does for PostgreSQL
(MySQL AUTO_INCREMENT and SQLite both derive the next value from MAX(id), so
they need nothing).

SAFETY
------
* Refuses to run unless DATABASE_URL is set to a NON-SQLite backend -- so it
  can never be pointed back at app_dev.db and copy a file onto itself.
* Refuses a target that already holds rows, unless --replace is passed. A
  half-merged database is far worse than a refused migration.
* Reads the source read-only and never deletes it: app_dev.db survives, so a
  failed migration costs nothing.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, func, insert, select
from sqlmodel import SQLModel

import app.models  # noqa: F401  -- registers every table on SQLModel.metadata
from app.db import DB_PATH, DB_URL, IS_SQLITE_DEV, SQLITE_DEV_URL


def _target_engine():
    if IS_SQLITE_DEV:
        raise SystemExit(
            "DATABASE_URL is not set (or still points at the local SQLite dev "
            "file), so there is nothing to migrate TO.\n"
            "Set it in .env first, e.g.\n"
            "  DATABASE_URL=postgresql+psycopg://user:pass@host:5432/btek"
        )
    return create_engine(DB_URL)


def _source_engine():
    if not DB_PATH.exists():
        raise SystemExit(f"Source database not found: {DB_PATH}")
    # Explicitly the dev file, NOT get_engine() -- get_engine() now follows
    # DATABASE_URL, which at this point is the destination.
    return create_engine(SQLITE_DEV_URL)


def _counts(engine, tables):
    with engine.connect() as conn:
        return {
            t.name: conn.execute(select(func.count()).select_from(t)).scalar_one()
            for t in tables
        }


def _resync_sequences(engine, tables):
    """Advance PostgreSQL identity sequences past the copied ids.

    Without this the first newly-created row reuses id 1 and fails on the
    primary key. Silently a no-op on other backends.
    """
    if engine.dialect.name != "postgresql":
        return []

    resynced = []
    with engine.begin() as conn:
        for table in tables:
            pk = list(table.primary_key.columns)
            if len(pk) != 1:
                continue
            column = pk[0]
            highest = conn.execute(select(func.max(column))).scalar_one_or_none()
            if highest is None:
                continue
            # pg_get_serial_sequence resolves the real sequence name for both
            # SERIAL and GENERATED-AS-IDENTITY columns, so we never guess at a
            # "<table>_<column>_seq" spelling that may not exist.
            conn.exec_driver_sql(
                "SELECT setval(pg_get_serial_sequence(%(t)s, %(c)s), %(v)s)",
                {"t": table.name, "c": column.name, "v": int(highest)},
            )
            resynced.append(f"{table.name}.{column.name} -> {highest}")
    return resynced


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be copied; write nothing")
    parser.add_argument("--replace", action="store_true",
                        help="allow a target that already holds rows "
                             "(existing rows in those tables are DELETED)")
    parser.add_argument("--batch", type=int, default=500,
                        help="rows per INSERT (default 500)")
    args = parser.parse_args()

    target = _target_engine()
    source = _source_engine()

    # sorted_tables is topologically ordered by foreign key, so parents are
    # always inserted before children.
    tables = list(SQLModel.metadata.sorted_tables)

    print(f"source : {DB_PATH}")
    print(f"target : {target.dialect.name} @ "
          f"{target.url.render_as_string(hide_password=True)}")
    print()

    source_counts = _counts(source, tables)
    total = sum(source_counts.values())
    for name, n in source_counts.items():
        print(f"  {name:20} {n:>6}")
    print(f"  {'TOTAL':20} {total:>6}")
    print()

    if args.dry_run:
        print("--dry-run: nothing written.")
        return 0

    print("Creating any missing tables on the target...")
    SQLModel.metadata.create_all(target)

    target_counts = _counts(target, tables)
    occupied = {n: c for n, c in target_counts.items() if c}
    if occupied and not args.replace:
        print()
        print("[X] Target already holds rows -- refusing to merge blindly:")
        for name, n in occupied.items():
            print(f"    {name:20} {n:>6}")
        print()
        print("  Pass --replace to DELETE those rows and copy fresh, or point")
        print("  DATABASE_URL at an empty database.")
        return 1

    with target.begin() as target_conn:
        if occupied:
            # Reverse order: children before parents, so no foreign key is
            # ever left dangling mid-delete.
            for table in reversed(tables):
                target_conn.execute(table.delete())
            print("Cleared existing rows (--replace).")

        with source.connect() as source_conn:
            for table in tables:
                rows = [
                    dict(row)
                    for row in source_conn.execute(select(table)).mappings()
                ]
                if not rows:
                    continue
                for start in range(0, len(rows), args.batch):
                    target_conn.execute(
                        insert(table), rows[start:start + args.batch]
                    )
                print(f"  copied {table.name:20} {len(rows):>6}")

    resynced = _resync_sequences(target, tables)
    if resynced:
        print()
        print("Resynced identity sequences:")
        for line in resynced:
            print(f"  {line}")

    print()
    print("Verifying row counts match...")
    final_counts = _counts(target, tables)
    mismatches = [
        (name, source_counts[name], final_counts[name])
        for name in source_counts
        if source_counts[name] != final_counts[name]
    ]
    if mismatches:
        print("[X] Row counts differ after copy:")
        for name, expected, actual in mismatches:
            print(f"    {name:20} expected {expected}, got {actual}")
        return 1

    print(f"[OK] All {len(tables)} tables match ({total} rows).")
    print()
    print("app_dev.db was NOT deleted -- keep it until the server copy is")
    print("confirmed good in the portal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
