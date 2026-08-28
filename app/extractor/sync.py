"""Read-only Moodle data-fetching for T1.3. Every function here only calls
core_course_get_courses / mod_assign_get_assignments / mod_assign_get_submissions
/ core_enrol_get_enrolled_users — no write function is called anywhere in
this module. Nothing here writes to the project database; these functions
only return plain dicts for a caller to store or print.

Every function takes an optional `client` (an app.extractor.moodle_client.
MoodleClient) so callers can target a specific Moodle site — defaults to
`default_client` (the elearning.abchorizon.com instance), so every existing
call site keeps working unchanged.
"""

from app.extractor.moodle_client import default_client


def fetch_courses(client=None) -> list[dict]:
    """Real (non-site) courses only."""
    client = client or default_client
    courses = client.call("core_course_get_courses")
    return [
        {
            "id": course.get("id"),
            "shortname": course.get("shortname"),
            "fullname": course.get("fullname"),
            "visible": course.get("visible"),
        }
        for course in courses
        if course.get("format") != "site"
    ]


def fetch_assignments(course_ids: list[int], client=None) -> list[dict]:
    client = client or default_client
    data = client.call("mod_assign_get_assignments", courseids=course_ids)
    assignments = []
    for course in data.get("courses", []):
        course_id = course.get("id")
        for assignment in course.get("assignments", []):
            assignments.append(
                {
                    "id": assignment.get("id"),
                    "cmid": assignment.get("cmid"),
                    "course": course_id,
                    "name": assignment.get("name"),
                    "duedate": assignment.get("duedate"),
                }
            )
    return assignments


def fetch_submissions(assignment_ids: list[int], client=None) -> list[dict]:
    client = client or default_client
    data = client.call("mod_assign_get_submissions", assignmentids=assignment_ids)
    submissions = []
    for assignment in data.get("assignments", []):
        assignment_id = assignment.get("assignmentid")
        for submission in assignment.get("submissions", []):
            files = []
            for plugin in submission.get("plugins", []):
                for filearea in plugin.get("fileareas", []):
                    for file_info in filearea.get("files", []):
                        files.append(
                            {
                                "filename": file_info.get("filename"),
                                "fileurl": file_info.get("fileurl"),
                                "filesize": file_info.get("filesize"),
                            }
                        )
            submissions.append(
                {
                    "id": submission.get("id"),
                    "userid": submission.get("userid"),
                    "assignment_id": assignment_id,
                    "status": submission.get("status"),
                    "timemodified": submission.get("timemodified"),
                    "files": files,
                }
            )
    return submissions


def fetch_user_names(course_id: int, user_ids: list[int], client=None) -> dict[int, str]:
    """userid -> fullname, for display in the portal only — never for prompts."""
    client = client or default_client
    enrolled_users = client.call("core_enrol_get_enrolled_users", courseid=course_id)
    wanted = set(user_ids)
    return {
        user["id"]: user["fullname"]
        for user in enrolled_users
        if user.get("id") in wanted
    }


# ---------------------------------------------------------------------------
# BTEC advanced-grading chain (read-only).
#
# These four functions reconstruct — over the API alone — most of the table
# chain that docs/moodle_data_access_plan.md section 1 originally assumed
# needed direct SQL. Verified live on elearning.abchorizon.com:
#
#   fetch_grading_definition(cmid=1640)     -> definition_id 16005
#   fetch_assign_grades([333])              -> itemid 813, grade "4.00000"
#   fetch_grading_instances(16005)          -> instance 2111 for itemid 813
#   fetch_btec_verdicts(373, [8158])        -> "Distinction"
#
# Only the criterion TEXT and the PER-CRITERION teacher remarks still need
# SQL (app/extractor/moodle_db.py). The definition_id and instance_id that
# those SQL queries take as parameters come from here — which is why the SQL
# credential needs no access to Moodle's grading_* core tables at all.
# ---------------------------------------------------------------------------

# Moodle's grading-definition status for "ready to use". A definition still
# in draft (status 10) must not be used as a grading source.
DEFINITION_STATUS_READY = 20


def fetch_grading_definition(cmid: int, client=None) -> dict | None:
    """The active advanced-grading definition for one assignment's cmid.

    Returns None when the assignment has no advanced grading configured, or
    when its active method is not 'btec' — callers must not fall back to a
    rubric/guide definition, since this project only understands BTEC.

    NOTE: this returns the definition's identity only. Moodle's API does NOT
    include the criteria themselves in this response (confirmed live: the
    payload for cmid 1640 carries method/name/status and no criteria array),
    which is precisely the gap app/extractor/moodle_db.py fills.
    """
    client = client or default_client
    data = client.call(
        "core_grading_get_definitions", cmids=[cmid], areaname="submissions"
    )

    for area in data.get("areas", []):
        if area.get("activemethod") != "btec":
            continue
        for definition in area.get("definitions", []):
            if definition.get("method") != "btec":
                continue
            return {
                "definition_id": definition.get("id"),
                "name": definition.get("name"),
                "status": definition.get("status"),
                "is_ready": definition.get("status") == DEFINITION_STATUS_READY,
                "cmid": area.get("cmid"),
                "contextid": area.get("contextid"),
            }
    return None


def fetch_assign_grades(assignment_ids: list[int], client=None) -> list[dict]:
    """Teacher-entered grades per submission attempt.

    `id` here is mdl_assign_grades.id — the same value that appears as
    `itemid` in fetch_grading_instances(), and the join key between a
    student's submission and its BTEC advanced-grading instance.

    An ungraded row still exists (Moodle pre-creates it) with grade "" and
    grader 0, so `is_graded` is derived rather than assuming presence
    means graded.
    """
    client = client or default_client
    data = client.call("mod_assign_get_grades", assignmentids=assignment_ids)

    grades = []
    for assignment in data.get("assignments", []):
        assignment_id = assignment.get("assignmentid")
        for grade in assignment.get("grades", []):
            raw = grade.get("grade")
            # Moodle uses -1 for "no grade" on scale-graded items, and ""
            # for never-touched rows. Both mean ungraded.
            try:
                numeric = float(raw) if raw not in (None, "") else None
            except (TypeError, ValueError):
                numeric = None
            if numeric is not None and numeric < 0:
                numeric = None

            grades.append(
                {
                    "itemid": grade.get("id"),
                    "assignment_id": assignment_id,
                    "userid": grade.get("userid"),
                    "attemptnumber": grade.get("attemptnumber"),
                    "grade": numeric,
                    "grader_userid": grade.get("grader") or None,
                    "graded_at": grade.get("timemodified"),
                    "is_graded": numeric is not None,
                }
            )
    return grades


def fetch_grading_instances(definition_id: int, client=None) -> list[dict]:
    """BTEC advanced-grading instances for one definition, keyed by itemid.

    `rawgrade` is deliberately not returned: it is null on every instance for
    the btec method (confirmed live across all 15 instances of definition
    16005), because the gradingform_btec plugin stores its scores in its own
    tables instead of Moodle's shared rawgrade column. Use
    fetch_btec_verdicts() for the overall outcome and
    moodle_db.fetch_fillings() for the per-criterion detail.
    """
    client = client or default_client
    data = client.call(
        "core_grading_get_gradingform_instances", definitionid=definition_id
    )

    return [
        {
            "instance_id": instance.get("id"),
            "itemid": instance.get("itemid"),
            "rater_userid": instance.get("raterid"),
            "status": instance.get("status"),
            "modified_at": instance.get("timemodified"),
        }
        for instance in data.get("instances", [])
    ]


# BTEC's grade scale as configured on this Moodle: grademin 1, grademax 4,
# rangeformatted "Refer-Distinction". Mapped explicitly rather than trusting
# `gradeformatted`'s wording alone, so a site that localises the scale label
# still yields a canonical value.
BTEC_SCALE = {1: "REFER", 2: "PASS", 3: "MERIT", 4: "DISTINCTION"}


def fetch_btec_verdicts(
    course_id: int, cmid: int, user_ids: list[int], client=None
) -> dict[int, dict]:
    """userid -> the teacher's FINAL BTEC verdict for one assignment.

    This is the human ground truth to compare the AI's own verdict against,
    and it is available over the API — no SQL needed. gradereport_user_get_
    grade_items returns `gradeformatted` as the scale's display label
    ("Distinction") plus `graderaw` as its numeric position (4).

    Called per user because the report function is scoped that way; callers
    handling a whole cohort should expect one API round-trip per student.
    Returns only users whose grade item was found and graded.
    """
    client = client or default_client
    verdicts = {}

    for user_id in user_ids:
        try:
            data = client.call(
                "gradereport_user_get_grade_items",
                courseid=course_id,
                userid=user_id,
            )
        except Exception:
            # One unreadable student must not abort a cohort-wide sync;
            # an absent entry already means "no verdict available".
            continue

        for user_grades in data.get("usergrades", []):
            for item in user_grades.get("gradeitems", []):
                if item.get("cmid") != cmid:
                    continue
                raw = item.get("graderaw")
                if raw is None:
                    continue  # grade item exists but is not graded yet
                verdicts[user_id] = {
                    "userid": user_id,
                    "grade_raw": raw,
                    "verdict": BTEC_SCALE.get(int(raw), "UNKNOWN"),
                    "verdict_label": item.get("gradeformatted"),
                    "graded_at": item.get("gradedategraded"),
                    "grade_min": item.get("grademin"),
                    "grade_max": item.get("grademax"),
                }
    return verdicts
