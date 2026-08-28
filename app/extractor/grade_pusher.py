"""Pushes an approved evaluation's overall result back into Moodle's own
gradebook, via mod_assign_save_grade.

Scope limit (intentional, not an oversight): mod_assign_save_grade only
writes the assignment's single overall grade field + one feedback comment.
It does NOT write Moodle's custom BTEC advanced-grading tables
(gradingform_btec_criteria / _fillings) — no Moodle Web Service exposes the
real criterion ids needed to target those rows (confirmed empirically:
core_grading_get_definitions returns only the definition, never criterion
ids), the same access gap documented in docs/moodle_data_access_plan.md for
reading criteria text. Until that is resolved (direct SQL or a Zoho
integration), per-criterion (P1/M1/D1...) results are visible only in this
project's own portal, never inside Moodle's BTEC grading grid.

What DOES transfer correctly: this course's assignment grade item is
configured 1-4 ("Refer" to "Distinction" — confirmed live via
gradereport_user_get_grade_items for courseid=373, grademin=1/grademax=4),
which lines up exactly with calculate_suggested_grade()'s four levels. So
the overall grade shown in Moodle's gradebook, plus a full text summary of
every criterion as the feedback comment, is both correct and immediately
useful to the teacher/student in Moodle — just not the official per-criterion
BTEC grid entry.
"""

import html

from app.extractor.moodle_client import default_client

GRADE_LEVEL_BY_LABEL = {
    "NOT_YET_ACHIEVED": 1,
    "PASS": 2,
    "MERIT": 3,
    "DISTINCTION": 4,
}


def build_feedback_comment(criterion_rows: list[dict]) -> str:
    """criterion_rows: [{"code", "achieved", "feedback"}], already sorted
    P->M->D by the caller (same ordering the portal already shows).

    Escapes `feedback` before embedding it in HTML — it is LLM-generated
    text that quotes fragments of the student's own submission, so it must
    be treated as untrusted when rendered as HTML (both in our own preview
    and, more importantly, in Moodle's comment view once sent).
    """
    lines = []
    for row in criterion_rows:
        mark = "✅" if row["achieved"] else "❌"
        code = html.escape(str(row["code"]))
        feedback = html.escape(str(row["feedback"]))
        lines.append(f"<p><strong>{code}</strong> {mark} — {feedback}</p>")
    return "\n".join(lines)


def push_grade_to_moodle(
    assignment_id: int, userid: int, grade_label: str, feedback_html: str, client=None
) -> dict:
    """Writes the overall grade (1-4) + one feedback comment for one
    student's submission. Raises MoodleCallError on any failure — callers
    must not treat a partial/ambiguous response as success.

    client defaults to the elearning instance — pass
    app.extractor.moodle_client.lms_client explicitly when the submission
    came from lms.abchorizon.com (confirmed live: that site's test course
    uses the same 1-4 Refer/Pass/Merit/Distinction scale, so the mapping
    below applies unchanged).
    """
    client = client or default_client
    grade_level = GRADE_LEVEL_BY_LABEL.get(grade_label)
    if grade_level is None:
        raise ValueError(f"unknown grade_label: {grade_label!r}")

    return client.call(
        "mod_assign_save_grade",
        http_method="POST",
        assignmentid=assignment_id,
        userid=userid,
        grade=grade_level,
        attemptnumber=-1,
        addattempt=0,
        workflowstate="graded",
        applytoall=0,
        **{
            "plugindata[assignfeedbackcomments_editor][text]": feedback_html,
            "plugindata[assignfeedbackcomments_editor][format]": 1,
        },
    )
