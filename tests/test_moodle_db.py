"""Tests for app/extractor/moodle_db.py.

The write-guard and password-secrecy tests are the important ones: they
encode the module's safety contract, so a future edit that weakens it fails
here rather than in production against a real Moodle database.

No test in this file opens a database connection. The two that need query
results monkeypatch `_query` directly, which is the seam between "our SQL
and row mapping" (worth testing) and "pymysql actually talking to MariaDB"
(not our code to test).
"""

import pytest

from app.extractor import moodle_db


# --- safety contract -------------------------------------------------------

@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE mdl_assign SET grade = 1",
        "DELETE FROM mdl_gradingform_btec_fillings",
        "INSERT INTO mdl_grading_instances VALUES (1)",
        "DROP TABLE mdl_user",
        "TRUNCATE mdl_assign_grades",
        "  update mdl_assign set grade = 1",  # leading space + lowercase
        "",
    ],
)
def test_query_refuses_every_non_read_statement(statement):
    """The guard must fire before any connection is attempted, so this test
    passes whether or not credentials happen to be configured.
    """
    with pytest.raises(moodle_db.MoodleDBError) as excinfo:
        moodle_db._query(statement)
    assert "SELECT-only" in str(excinfo.value)


@pytest.mark.parametrize("statement", ["SELECT 1", "SHOW TABLES LIKE 'x'"])
def test_query_guard_allows_read_statements_through(statement, monkeypatch):
    """A read statement must get PAST the guard. Verified by asserting it
    reaches _connect() — patched here so no real connection is made.
    """
    reached = []
    monkeypatch.setattr(
        moodle_db, "_connect",
        lambda: (_ for _ in ()).throw(RuntimeError("reached _connect")),
    )
    with pytest.raises(RuntimeError, match="reached _connect"):
        moodle_db._query(statement)


def test_describe_config_never_exposes_the_password(monkeypatch):
    monkeypatch.setattr(moodle_db, "DB_PASSWORD", "SuperSecret123!")
    monkeypatch.setattr(moodle_db, "DB_HOST", "127.0.0.1")
    monkeypatch.setattr(moodle_db, "DB_NAME", "moodle_db")
    monkeypatch.setattr(moodle_db, "DB_USER", "btec_ro")

    config = moodle_db.describe_config()

    assert "SuperSecret123!" not in repr(config)
    # password_set tells an operator whether one is present without
    # revealing it or even its length.
    assert config["password_set"] is True
    assert config["configured"] is True


def test_unconfigured_access_raises_the_specific_not_configured_error(monkeypatch):
    """Callers with an API-only fallback catch MoodleDBNotConfigured, so a
    missing config must not surface as a generic MoodleDBError.
    """
    monkeypatch.setattr(moodle_db, "DB_HOST", "")
    monkeypatch.setattr(moodle_db, "DB_NAME", "")
    monkeypatch.setattr(moodle_db, "DB_USER", "")

    assert moodle_db.is_configured() is False
    with pytest.raises(moodle_db.MoodleDBNotConfigured):
        moodle_db.fetch_criteria(16005)


def test_check_access_reports_instead_of_raising(monkeypatch):
    monkeypatch.setattr(moodle_db, "DB_HOST", "")
    monkeypatch.setattr(moodle_db, "DB_NAME", "")
    monkeypatch.setattr(moodle_db, "DB_USER", "")

    report = moodle_db.check_access()

    assert report["error"] == "not configured"
    assert report["connected"] is False


def test_unsupported_db_type_names_the_problem(monkeypatch):
    monkeypatch.setattr(moodle_db, "DB_HOST", "127.0.0.1")
    monkeypatch.setattr(moodle_db, "DB_NAME", "moodle_db")
    monkeypatch.setattr(moodle_db, "DB_USER", "btec_ro")
    monkeypatch.setattr(moodle_db, "DB_TYPE", "postgresql")

    with pytest.raises(moodle_db.MoodleDBError, match="not supported"):
        moodle_db._connect()


# --- BTEC level derivation -------------------------------------------------

@pytest.mark.parametrize(
    "shortname,expected",
    [
        ("A.P1", "PASS"),
        ("A.M2", "MERIT"),
        ("B.D1", "DISTINCTION"),
        ("P3", "PASS"),
        ("M1", "MERIT"),
        ("D2", "DISTINCTION"),
        ("X.Z9", "UNKNOWN"),
        ("", "UNKNOWN"),
    ],
)
def test_level_read_from_last_dot_segment_not_first_letter(shortname, expected):
    """"A.M2" must be MERIT, not "A" — the learning-aim prefix must not be
    mistaken for the BTEC level.
    """
    assert moodle_db._level_from_shortname(shortname) == expected


# --- table-name resolution -------------------------------------------------

def _show_tables_rows(*names):
    """Mimics SHOW TABLES output: one column named "Tables_in_<db>", which
    moodle_db reads positionally because the db name varies per site.
    """
    return [{"Tables_in_moodle_db": name} for name in names]


@pytest.mark.parametrize(
    "present",
    ["mdl_gradingform_btec_fillings", "mdl_gradingform_btec_filling"],
)
def test_fillings_table_accepts_plural_or_singular(present, monkeypatch):
    """The gradingform_btec plugin ships one spelling or the other and even
    its author hedged — resolve it from the server, never hard-code.
    """
    monkeypatch.setattr(moodle_db, "DB_PREFIX", "mdl_")
    monkeypatch.setattr(
        moodle_db, "_query", lambda sql, params=(): _show_tables_rows(present)
    )

    assert moodle_db.fillings_table() == present


def test_fillings_table_error_names_the_likely_causes(monkeypatch):
    monkeypatch.setattr(moodle_db, "_query", lambda sql, params=(): [])

    with pytest.raises(moodle_db.MoodleDBError) as excinfo:
        moodle_db.fillings_table()

    message = str(excinfo.value)
    # A wrong-instance credential is the most likely real cause, so the
    # message must point at it rather than just saying "not found".
    assert "prefix" in message.lower() or "PREFIX" in message
    assert "different Moodle site" in message


# --- row mapping -----------------------------------------------------------

def test_fetch_criteria_shape_matches_the_json_fixture_shape(monkeypatch):
    """SQL rows and sample_data/*.json entries must be interchangeable, so
    callers need no branch for where the criteria came from.
    """
    monkeypatch.setattr(
        moodle_db, "_query",
        lambda sql, params=(): [
            {"id": 501, "shortname": "A.P1",
             "description": "  Describe the sources and uses of oil.  ",
             "sortorder": 0},
            {"id": 502, "shortname": "B.M2", "description": "Compare X and Y.",
             "sortorder": 3},
        ],
    )

    criteria = moodle_db.fetch_criteria(16005)

    assert criteria[0]["criterion_code"] == "P1"      # bare, as Criterion.code
    assert criteria[0]["source_code"] == "A.P1"       # as stored in Moodle
    assert criteria[0]["level"] == "PASS"
    assert criteria[0]["criterion_text"] == "Describe the sources and uses of oil."
    assert criteria[1]["criterion_code"] == "M2"
    assert criteria[1]["level"] == "MERIT"


def test_fetch_fillings_separates_not_judged_from_judged_zero(monkeypatch):
    """A criterion with no filling row (teacher never looked) must be
    distinguishable from one the teacher explicitly marked not-achieved.
    Collapsing the two would silently invent a judgement.
    """
    monkeypatch.setattr(
        moodle_db, "fillings_table", lambda: "mdl_gradingform_btec_fillings"
    )
    monkeypatch.setattr(
        moodle_db, "_query",
        lambda sql, params=(): [
            {"criterion_id": 1, "shortname": "A.P1", "criterion_text": "t1",
             "sortorder": 0, "score": 1, "remark": "Well evidenced."},
            {"criterion_id": 2, "shortname": "A.P2", "criterion_text": "t2",
             "sortorder": 1, "score": 0, "remark": "Not shown."},
            {"criterion_id": 3, "shortname": "B.M1", "criterion_text": "t3",
             "sortorder": 2, "score": None, "remark": None},
        ],
    )

    judgements = moodle_db.fetch_fillings(instance_id=2111, definition_id=16005)

    achieved, refused, untouched = judgements

    assert (achieved["was_judged"], achieved["achieved"]) == (True, True)
    assert achieved["teacher_remark"] == "Well evidenced."

    assert (refused["was_judged"], refused["achieved"]) == (True, False)

    assert (untouched["was_judged"], untouched["achieved"]) == (False, None)
    assert untouched["teacher_remark"] is None
