"""Direct read-only SQL access to Moodle's BTEC grading-form tables.

WHY THIS MODULE EXISTS
----------------------
Two pieces of BTEC data are not exposed by ANY Moodle Web Service function,
and are therefore unreachable through app/extractor/moodle_client.py:

  1. The criterion text itself  -> mdl_gradingform_btec_criteria
     (P1/M1/D1 shortnames + their full descriptions)
  2. The teacher's per-criterion judgement -> mdl_gradingform_btec_fillings
     (score + remark for one criterion on one submission)

Everything else the project needs — courses, assignments, submissions,
files, enrolled users, and even the teacher's FINAL BTEC verdict
(Refer/Pass/Merit/Distinction, see app/extractor/sync.py:fetch_btec_verdicts)
— comes from the Web Services API and must keep coming from there. This
module is deliberately narrow: it covers only the two-table gap, so the SQL
credential's required scope stays as small as possible.

See docs/moodle_data_access_plan.md section 7-د for how that scope was
narrowed from seven tables to two.

SAFETY CONTRACT (do not weaken)
-------------------------------
* Read-only. `_query()` refuses any statement that is not SELECT/SHOW, so a
  future edit cannot accidentally turn this into a writer. The database user
  itself should also be GRANTed SELECT only — defence in depth, because a
  code-level guard protects against our own mistakes, not against a
  compromised credential.
* The password is read from the environment and never logged, never included
  in an exception message, and never returned by describe_config().
* No student personal data is read here. mdl_user is never queried — student
  names come from core_enrol_get_enrolled_users via the API instead.

CONFIGURATION
-------------
Set these in .env (all blank by default; the module reports "not configured"
rather than failing at import time, so the app runs fine without them):

    MOODLE_DB_TYPE=mariadb      # mariadb | mysql
    MOODLE_DB_HOST=127.0.0.1    # usually a local SSH-tunnel endpoint
    MOODLE_DB_PORT=3306
    MOODLE_DB_NAME=
    MOODLE_DB_USER=             # SELECT privilege only
    MOODLE_DB_PASSWORD=
    MOODLE_DB_PREFIX=mdl_

Moodle binds its database to localhost on the server, so MOODLE_DB_HOST is
normally the local end of an SSH tunnel, e.g.:

    ssh -N -L 3307:127.0.0.1:3306 <tunnel-user>@<server>

...and then MOODLE_DB_HOST=127.0.0.1, MOODLE_DB_PORT=3307.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DB_TYPE = os.getenv("MOODLE_DB_TYPE", "mariadb").strip().lower()
DB_HOST = os.getenv("MOODLE_DB_HOST", "").strip()
DB_PORT = os.getenv("MOODLE_DB_PORT", "").strip()
DB_NAME = os.getenv("MOODLE_DB_NAME", "").strip()
DB_USER = os.getenv("MOODLE_DB_USER", "").strip()
DB_PASSWORD = os.getenv("MOODLE_DB_PASSWORD", "")
DB_PREFIX = os.getenv("MOODLE_DB_PREFIX", "mdl_").strip()

SUPPORTED_DB_TYPES = {"mariadb", "mysql"}

# Moodle's own default; only used when MOODLE_DB_PORT is left blank.
DEFAULT_PORT = 3306


class MoodleDBError(Exception):
    """Any failure reaching or reading Moodle's database.

    Never carries a driver exception's raw text when that text could embed
    the connection string (and therefore the password).
    """


class MoodleDBNotConfigured(MoodleDBError):
    """Raised when SQL access is requested but no credentials are set.

    Callers that have an API-only fallback should catch THIS specifically
    rather than MoodleDBError, so a genuine connection failure is not
    silently treated as "not configured yet".
    """


def is_configured() -> bool:
    """True when enough is set to attempt a connection.

    Password is intentionally not required to be non-empty — a socket/IAM
    auth setup can legitimately have none — but host/name/user are.
    """
    return bool(DB_HOST and DB_NAME and DB_USER)


def describe_config() -> dict:
    """Connection facts safe to print in a terminal or log.

    Deliberately omits the password entirely — not even its length, which
    would narrow a brute-force search.
    """
    return {
        "configured": is_configured(),
        "type": DB_TYPE,
        "host": DB_HOST or "(unset)",
        "port": DB_PORT or str(DEFAULT_PORT),
        "database": DB_NAME or "(unset)",
        "user": DB_USER or "(unset)",
        "prefix": DB_PREFIX,
        "password_set": bool(DB_PASSWORD),
    }


def table(name: str) -> str:
    """Prefixes a bare Moodle table name, e.g. "assign" -> "mdl_assign".

    Table names are interpolated into SQL (they cannot be bound as
    parameters), so every name reaching this function must be a literal from
    this module — never caller input.
    """
    return f"{DB_PREFIX}{name}"


def _connect():
    """Opens a short-lived read-only connection. Caller must close it."""
    if not is_configured():
        raise MoodleDBNotConfigured(
            "Moodle SQL access is not configured — set MOODLE_DB_HOST, "
            "MOODLE_DB_NAME and MOODLE_DB_USER in .env "
            "(see this module's docstring)."
        )

    if DB_TYPE not in SUPPORTED_DB_TYPES:
        raise MoodleDBError(
            f"MOODLE_DB_TYPE={DB_TYPE!r} is not supported by this module "
            f"(supported: {', '.join(sorted(SUPPORTED_DB_TYPES))}). "
            "PostgreSQL would additionally need a psycopg driver installed."
        )

    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError:
        raise MoodleDBError(
            "pymysql is not installed — add it to requirements.txt."
        )

    try:
        return pymysql.connect(
            host=DB_HOST,
            port=int(DB_PORT) if DB_PORT else DEFAULT_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=10,
            # Read-only intent, enforced three ways: no autocommit (nothing
            # can be committed), a SELECT/SHOW-only guard in _query(), and a
            # SELECT-only database GRANT on the server side.
            autocommit=False,
        )
    except Exception as exc:
        # pymysql's OperationalError text can include host/user/database.
        # It does not include the password, but keep the surface minimal and
        # surface only the error class plus our own context.
        raise MoodleDBError(
            f"Could not connect to Moodle database at {DB_HOST}:"
            f"{DB_PORT or DEFAULT_PORT} as {DB_USER!r} "
            f"({type(exc).__name__}). If Moodle's database is bound to "
            "localhost on the server, an SSH tunnel must be running."
        )


def _query(sql: str, params: tuple = ()) -> list[dict]:
    """Runs one read-only statement and returns all rows as dicts.

    Refuses anything that is not a SELECT or SHOW. This guard exists so that
    a later well-meaning edit ("just one UPDATE to mark it synced...") fails
    loudly in this module rather than writing to a production Moodle.
    """
    first_word = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
    if first_word not in {"SELECT", "SHOW"}:
        raise MoodleDBError(
            f"Refused a non-read statement ({first_word or 'empty'}). This "
            "module is SELECT-only by contract; writes to Moodle must go "
            "through the Web Services API, never through direct SQL."
        )

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
    except MoodleDBError:
        raise
    except Exception as exc:
        raise MoodleDBError(
            f"Moodle database read failed ({type(exc).__name__}). The "
            "SELECT grant may not cover the requested table."
        )
    finally:
        # Nothing was committed (autocommit=False and no write ran), so
        # closing discards the implicit read transaction.
        connection.close()


def fillings_table() -> str:
    """Resolves the BTEC fillings table's real name at runtime.

    The gradingform_btec plugin's own code checks BOTH the plural
    ("..._fillings") and singular ("..._filling") spellings, because even
    its author was unsure which one ships — see
    docs/moodle_data_access_plan.md section 2-ج. Rather than hard-code a
    guess, ask the server.

    Raises MoodleDBError if neither exists, which is the clearest possible
    signal that this database has no BTEC grading-form plugin installed
    (e.g. the credential points at the wrong Moodle instance).
    """
    pattern = f"{DB_PREFIX}gradingform_btec_filling%"
    rows = _query("SHOW TABLES LIKE %s", (pattern,))

    # SHOW TABLES returns a single column whose key is "Tables_in_<dbname>",
    # so read the value positionally rather than by a guessed key name.
    names = {next(iter(row.values())) for row in rows if row}

    for candidate in (table("gradingform_btec_fillings"), table("gradingform_btec_filling")):
        if candidate in names:
            return candidate

    raise MoodleDBError(
        f"No BTEC fillings table found matching {pattern!r} in database "
        f"{DB_NAME!r}. Either the gradingform_btec plugin is not installed "
        "on this Moodle instance, or MOODLE_DB_PREFIX is wrong, or the "
        "credential points at a different Moodle site than expected."
    )


def fetch_criteria(definition_id: int) -> list[dict]:
    """The real BTEC criteria for one grading definition, in display order.

    definition_id comes from the API, not from SQL:
    core_grading_get_definitions(cmids=[...], areaname='submissions') returns
    it (16005 for the Sustainable Energy assignment) — so no grading_*
    core-table access is needed here.

    Returned dict keys match sample_data/*-assessment-criteria.json's
    "criteria" entries, so a caller can treat a SQL row and a JSON fixture
    row identically:
        criterion_code, source_code, criterion_text, level
    """
    rows = _query(
        f"""
        SELECT id, shortname, description, sortorder
        FROM {table('gradingform_btec_criteria')}
        WHERE definitionid = %s
        ORDER BY sortorder, id
        """,
        (definition_id,),
    )

    criteria = []
    for row in rows:
        shortname = (row.get("shortname") or "").strip()
        criteria.append(
            {
                "criterion_id": row.get("id"),
                # Moodle stores e.g. "A.P1"; the project keys criteria by the
                # bare "P1" (Criterion.code), so expose both rather than
                # forcing every caller to re-derive one from the other.
                "criterion_code": shortname.rsplit(".", 1)[-1],
                "source_code": shortname,
                "criterion_text": (row.get("description") or "").strip(),
                "level": _level_from_shortname(shortname),
                "sortorder": row.get("sortorder"),
            }
        )
    return criteria


def _level_from_shortname(shortname: str) -> str:
    """"A.P1" / "P1" -> "PASS". Unrecognised -> "UNKNOWN".

    BTEC encodes the level in the letter preceding the number, so read the
    first letter of the LAST dot-segment ("A.M2" -> "M"), not of the whole
    string — otherwise every criterion in learning aim A would read as "A".
    """
    tail = shortname.rsplit(".", 1)[-1].strip().upper()
    return {"P": "PASS", "M": "MERIT", "D": "DISTINCTION"}.get(
        tail[:1], "UNKNOWN"
    )


def fetch_fillings(instance_id: int, definition_id: int) -> list[dict]:
    """The teacher's per-criterion judgement for ONE graded submission.

    instance_id comes from the API too:
    core_grading_get_gradingform_instances(definitionid=...) returns each
    instance's id alongside the itemid that links it to a submission (see
    app/extractor/sync.py:fetch_grading_instances).

    LEFT JOIN, not INNER: a criterion the teacher left untouched has no
    filling row at all, and the caller needs to see it as "not judged"
    rather than have it vanish from the list.
    """
    fillings = fillings_table()
    rows = _query(
        f"""
        SELECT
            c.id            AS criterion_id,
            c.shortname     AS shortname,
            c.description   AS criterion_text,
            c.sortorder     AS sortorder,
            f.score         AS score,
            f.remark        AS remark
        FROM {table('gradingform_btec_criteria')} c
        LEFT JOIN {fillings} f
               ON f.criterionid = c.id AND f.instanceid = %s
        WHERE c.definitionid = %s
        ORDER BY c.sortorder, c.id
        """,
        (instance_id, definition_id),
    )

    judgements = []
    for row in rows:
        shortname = (row.get("shortname") or "").strip()
        score = row.get("score")
        judgements.append(
            {
                "criterion_id": row.get("criterion_id"),
                "criterion_code": shortname.rsplit(".", 1)[-1],
                "source_code": shortname,
                "criterion_text": (row.get("criterion_text") or "").strip(),
                "level": _level_from_shortname(shortname),
                "score": score,
                "teacher_remark": (row.get("remark") or "").strip() or None,
                # Distinguish "teacher marked it not-achieved" (a real 0)
                # from "teacher never looked at it" (no row -> score None).
                "was_judged": score is not None,
                "achieved": bool(score) if score is not None else None,
            }
        )
    return judgements


def check_access() -> dict:
    """One-call diagnostic: can we connect, and is this the right database?

    Returns a report dict instead of raising, so a setup script can print
    every finding at once. Never raises for a configuration or connection
    problem — only genuinely unexpected errors propagate.
    """
    report = dict(describe_config())
    report.update({"connected": False, "fillings_table": None,
                   "criteria_rows": None, "error": None})

    if not is_configured():
        report["error"] = "not configured"
        return report

    try:
        report["fillings_table"] = fillings_table()
        report["connected"] = True
        rows = _query(
            f"SELECT COUNT(*) AS n FROM {table('gradingform_btec_criteria')}"
        )
        report["criteria_rows"] = rows[0]["n"] if rows else 0
    except MoodleDBError as exc:
        report["error"] = str(exc)

    return report
