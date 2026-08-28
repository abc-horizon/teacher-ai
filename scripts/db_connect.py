"""Connect to the elearning database and report exactly what works.

    .venv/Scripts/python.exe scripts/db_connect.py

Prints the settings in use (never the password), says whether the database
is reachable, and on success lists the Moodle tables that matter to us with
their row counts — so a successful run is proof of real data, not just a
successful handshake.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database


def main() -> int:
    print("=== settings ===")
    for key, value in database.describe().items():
        print(f"  {key:14} {value}")
    print()

    print("=== connection ===")
    result = database.probe()

    if not result["ok"]:
        print(f"  NOT CONNECTED — {result['reason']}")
        print(f"  Fix: {result['fix']}")
        return 1

    print(f"  CONNECTED to {result['database']} on MariaDB {result['server']}")
    print(f"  tables in schema: {result['tables']}")
    print()

    print("=== Moodle tables ===")
    prefix = database.PREFIX
    for table in ("user", "course", "assign", "assign_submission",
                  "grading_definitions", "gradingform_btec_criteria"):
        name = f"{prefix}{table}"
        try:
            rows = database.query(f"SELECT COUNT(*) AS n FROM `{name}`")
            print(f"  {name:34} {rows[0]['n']:>8,} rows")
        except database.DatabaseError:
            print(f"  {name:34} {'absent':>8}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
