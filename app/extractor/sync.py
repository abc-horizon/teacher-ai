"""Read-only Moodle data-fetching for T1.3. Every function here only calls
core_course_get_courses / mod_assign_get_assignments / mod_assign_get_submissions
/ core_enrol_get_enrolled_users — no write function is called anywhere in
this module. Nothing here writes to the project database; these functions
only return plain dicts for a caller to store or print.
"""

from app.extractor.moodle_client import call_moodle


def fetch_courses() -> list[dict]:
    """Real (non-site) courses only."""
    courses = call_moodle("core_course_get_courses")
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


def fetch_assignments(course_ids: list[int]) -> list[dict]:
    data = call_moodle("mod_assign_get_assignments", courseids=course_ids)
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


def fetch_submissions(assignment_ids: list[int]) -> list[dict]:
    data = call_moodle("mod_assign_get_submissions", assignmentids=assignment_ids)
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


def fetch_user_names(course_id: int, user_ids: list[int]) -> dict[int, str]:
    """userid -> fullname, for display in the portal only — never for prompts."""
    enrolled_users = call_moodle("core_enrol_get_enrolled_users", courseid=course_id)
    wanted = set(user_ids)
    return {
        user["id"]: user["fullname"]
        for user in enrolled_users
        if user.get("id") in wanted
    }
