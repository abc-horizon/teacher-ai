"""Tests for the BTEC advanced-grading chain in app/extractor/sync.py.

These four functions replaced five of the seven tables that
docs/moodle_data_access_plan.md originally wanted direct SQL access for, so
their row mapping is what keeps the SQL credential's scope down to two
tables. Every payload shape below is copied from a real response observed
live on elearning.abchorizon.com, including its quirks.

A FakeClient is passed explicitly via client= (the same approach as
tests/test_grade_pusher.py) so no test depends on monkeypatching internals
or reaches a real Moodle site.
"""

import pytest

from app.extractor.sync import (
    fetch_assign_grades,
    fetch_btec_verdicts,
    fetch_grading_definition,
    fetch_grading_instances,
)


class FakeClient:
    """Returns a canned payload and records what was asked for."""

    def __init__(self, payload, fail_for_userids=()):
        self.payload = payload
        self.fail_for_userids = set(fail_for_userids)
        self.calls = []

    def call(self, wsfunction, **params):
        self.calls.append((wsfunction, params))
        if params.get("userid") in self.fail_for_userids:
            raise RuntimeError("simulated per-user API failure")
        return self.payload


# --- fetch_grading_definition ---------------------------------------------

BTEC_DEFINITION_PAYLOAD = {
    "areas": [
        {
            "cmid": 1640,
            "contextid": 11436,
            "areaname": "submissions",
            "activemethod": "btec",
            "definitions": [
                {"id": 16005, "method": "btec", "name": "Sustainable Energy",
                 "status": 20},
            ],
        }
    ],
    "warnings": [],
}


def test_fetch_grading_definition_extracts_the_btec_definition():
    client = FakeClient(BTEC_DEFINITION_PAYLOAD)

    definition = fetch_grading_definition(1640, client=client)

    assert definition["definition_id"] == 16005
    assert definition["is_ready"] is True      # status 20 == READY
    assert definition["contextid"] == 11436


def test_fetch_grading_definition_ignores_non_btec_methods():
    """A rubric-graded assignment must yield None, not a rubric definition —
    this project's criteria model only understands BTEC, so silently
    accepting a rubric would produce nonsense downstream.
    """
    client = FakeClient({
        "areas": [{
            "cmid": 99, "activemethod": "rubric",
            "definitions": [{"id": 777, "method": "rubric", "name": "R",
                             "status": 20}],
        }]
    })

    assert fetch_grading_definition(99, client=client) is None


def test_fetch_grading_definition_flags_a_draft_as_not_ready():
    client = FakeClient({
        "areas": [{
            "cmid": 1640, "activemethod": "btec",
            "definitions": [{"id": 16005, "method": "btec", "name": "SE",
                             "status": 10}],
        }]
    })

    definition = fetch_grading_definition(1640, client=client)

    assert definition["definition_id"] == 16005
    assert definition["is_ready"] is False


# --- fetch_assign_grades ---------------------------------------------------

def test_fetch_assign_grades_treats_every_ungraded_form_as_ungraded():
    """Moodle pre-creates a grade row for each enrolled student. Observed
    live, an ungraded one carries grade "" and grader 0; a scale item with
    no grade carries "-1.00000". All three must read as not graded, or the
    portal would show phantom marks.
    """
    client = FakeClient({
        "assignments": [{
            "assignmentid": 333,
            "grades": [
                {"id": 813, "userid": 8158, "attemptnumber": 0,
                 "grade": "4.00000", "grader": 8181, "timemodified": 1784886372},
                {"id": 988, "userid": 10109, "attemptnumber": 0,
                 "grade": "", "grader": 0, "timemodified": 1784886380},
                {"id": 1658, "userid": 10311, "attemptnumber": 0,
                 "grade": "-1.00000", "grader": -1, "timemodified": 1779263982},
                {"id": 1700, "userid": 10400, "attemptnumber": 0,
                 "grade": None, "grader": 0, "timemodified": 0},
            ],
        }]
    })

    grades = fetch_assign_grades([333], client=client)
    by_item = {g["itemid"]: g for g in grades}

    assert by_item[813]["is_graded"] is True
    assert by_item[813]["grade"] == 4.0
    assert by_item[813]["grader_userid"] == 8181

    for ungraded_itemid in (988, 1658, 1700):
        assert by_item[ungraded_itemid]["is_graded"] is False
        assert by_item[ungraded_itemid]["grade"] is None
        # grader 0 / -1 are Moodle's "nobody", not real user ids.
        assert by_item[ungraded_itemid]["grader_userid"] in (None, -1)


def test_fetch_assign_grades_exposes_itemid_as_the_join_key():
    """itemid is mdl_assign_grades.id, the value that links a submission to
    its grading instance and to moodle_db.fetch_fillings(). Renaming it
    would break that join, so pin the name.
    """
    client = FakeClient({
        "assignments": [{"assignmentid": 333, "grades": [
            {"id": 813, "userid": 8158, "grade": "4.00000", "grader": 8181,
             "attemptnumber": 0, "timemodified": 1}]}]
    })

    assert fetch_assign_grades([333], client=client)[0]["itemid"] == 813


# --- fetch_grading_instances ----------------------------------------------

def test_fetch_grading_instances_joins_to_grades_on_itemid():
    client = FakeClient({
        "instances": [
            {"id": 2111, "raterid": 8181, "itemid": 813, "rawgrade": None,
             "status": 1, "timemodified": 1784885437},
            {"id": 1546, "raterid": 8158, "itemid": 992, "rawgrade": None,
             "status": 1, "timemodified": 1780324032},
        ]
    })

    instances = fetch_grading_instances(16005, client=client)
    by_item = {i["itemid"]: i for i in instances}

    assert by_item[813]["instance_id"] == 2111
    assert by_item[813]["rater_userid"] == 8181
    # rawgrade is null for every btec instance (the plugin stores scores in
    # its own tables), so it is deliberately not surfaced at all.
    assert "rawgrade" not in instances[0]


# --- fetch_btec_verdicts --------------------------------------------------

def _grade_item_payload(cmid, graderaw, label):
    return {"usergrades": [{"gradeitems": [
        {"cmid": cmid, "itemname": "Sustainable Energy Assignment",
         "graderaw": graderaw, "gradeformatted": label,
         "grademin": 1, "grademax": 4, "gradedategraded": 1784886372},
    ]}]}


@pytest.mark.parametrize(
    "graderaw,expected",
    [(1, "REFER"), (2, "PASS"), (3, "MERIT"), (4, "DISTINCTION")],
)
def test_fetch_btec_verdicts_maps_the_whole_scale(graderaw, expected):
    client = FakeClient(_grade_item_payload(1640, graderaw, "whatever"))

    verdicts = fetch_btec_verdicts(373, 1640, [8158], client=client)

    assert verdicts[8158]["verdict"] == expected


def test_verdict_comes_from_the_number_not_moodles_label():
    """This site's scale has a typo — level 3 is labelled "Miret", not
    "Merit" (observed live). Deriving the verdict from graderaw keeps the
    canonical value correct while still preserving the raw label for
    display, so a site typo or a localised scale cannot corrupt grading data.
    """
    client = FakeClient(_grade_item_payload(1640, 3, "Miret"))

    verdict = fetch_btec_verdicts(373, 1640, [8158], client=client)[8158]

    assert verdict["verdict"] == "MERIT"
    assert verdict["verdict_label"] == "Miret"


def test_fetch_btec_verdicts_skips_other_assignments_grade_items():
    """A course has many grade items; only the requested cmid's may be read."""
    client = FakeClient(_grade_item_payload(9999, 4, "Distinction"))

    assert fetch_btec_verdicts(373, 1640, [8158], client=client) == {}


def test_ungraded_student_is_absent_rather_than_reported_as_refer():
    """graderaw None means "not marked yet". Defaulting it to 1 would read
    as the teacher having failed the student."""
    client = FakeClient(_grade_item_payload(1640, None, None))

    assert fetch_btec_verdicts(373, 1640, [8158], client=client) == {}


def test_one_unreadable_student_does_not_abort_the_cohort():
    client = FakeClient(
        _grade_item_payload(1640, 4, "Distinction"), fail_for_userids=[10109]
    )

    verdicts = fetch_btec_verdicts(373, 1640, [8158, 10109, 10207], client=client)

    assert set(verdicts) == {8158, 10207}
