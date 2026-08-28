import pytest

from app.extractor.grade_pusher import build_feedback_comment, push_grade_to_moodle


def test_build_feedback_comment_marks_achieved_and_not_achieved():
    rows = [
        {"code": "P1", "achieved": True, "feedback": "Good coverage."},
        {"code": "M1", "achieved": False, "feedback": "Missing comparison."},
    ]

    comment = build_feedback_comment(rows)

    assert "P1" in comment and "✅" in comment and "Good coverage." in comment
    assert "M1" in comment and "❌" in comment and "Missing comparison." in comment


class FakeMoodleClient:
    """Records the exact call push_grade_to_moodle makes, without touching
    any real Moodle site — passed explicitly via the client= param, so this
    test does not depend on monkeypatching internal names.
    """

    def __init__(self):
        self.captured = {}

    def call(self, wsfunction, **params):
        self.captured["wsfunction"] = wsfunction
        self.captured["params"] = params
        return []


def test_push_grade_to_moodle_sends_correct_grade_level_and_uses_post():
    fake_client = FakeMoodleClient()

    push_grade_to_moodle(
        assignment_id=333,
        userid=999,
        grade_label="MERIT",
        feedback_html="<p>ok</p>",
        client=fake_client,
    )

    captured = fake_client.captured

    assert captured["wsfunction"] == "mod_assign_save_grade"
    assert captured["params"]["http_method"] == "POST"
    assert captured["params"]["assignmentid"] == 333
    assert captured["params"]["userid"] == 999
    assert captured["params"]["grade"] == 3  # MERIT -> level 3
    assert (
        captured["params"]["plugindata[assignfeedbackcomments_editor][text]"]
        == "<p>ok</p>"
    )


def test_push_grade_to_moodle_rejects_unknown_grade_label():
    with pytest.raises(ValueError):
        push_grade_to_moodle(
            assignment_id=333, userid=999, grade_label="???", feedback_html=""
        )
