"""One focused check: for every assignment this token can see, what
grading method (if any) is configured? Read-only. Self-contained (does not
import other scripts/ files — see explore_grading_criteria.py for why).
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

MOODLE_URL = os.getenv("MOODLE_URL", "").rstrip("/")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", "")


class MoodleCallError(Exception):
    pass


def call_moodle(wsfunction: str, **params) -> dict:
    query = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": wsfunction,
        "moodlewsrestformat": "json",
    }
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                query[f"{key}[{index}]"] = item
        else:
            query[key] = value

    try:
        response = requests.get(
            f"{MOODLE_URL}/webservice/rest/server.php", params=query, timeout=20
        )
    except requests.RequestException:
        raise MoodleCallError(
            "Network error while contacting Moodle (check MOODLE_URL/connectivity)."
        )

    if response.status_code != 200:
        raise MoodleCallError(f"HTTP {response.status_code} from Moodle server.")

    try:
        data = response.json()
    except ValueError:
        raise MoodleCallError(
            "Response was not valid JSON (check MOODLE_URL points at the Moodle root)."
        )

    if isinstance(data, dict) and ("exception" in data or "errorcode" in data):
        errorcode = data.get("errorcode", "unknown_error")
        message = data.get("message", "")
        raise MoodleCallError(f"{errorcode}: {message}")

    return data


def main():
    if not MOODLE_URL or not MOODLE_TOKEN:
        print("✗ MOODLE_URL أو MOODLE_TOKEN غير مضبوطين في .env — أوقفت التنفيذ.")
        return

    try:
        assign_data = call_moodle("mod_assign_get_assignments")
    except MoodleCallError as exc:
        print(f"✗ فشل mod_assign_get_assignments: {exc}")
        return

    rows = []
    for course in assign_data.get("courses", []):
        course_id = course.get("id")
        for assignment in course.get("assignments", []):
            rows.append(
                {
                    "cmid": assignment.get("cmid"),
                    "courseid": course_id,
                    "assignment_id": assignment.get("id"),
                }
            )

    for row in rows:
        try:
            definitions_data = call_moodle(
                "core_grading_get_definitions",
                cmids=[row["cmid"]],
                areaname="submissions",
            )
            activemethod = None
            areas = definitions_data.get("areas", [])
            if areas:
                activemethod = areas[0].get("activemethod")
            row["activemethod"] = activemethod
        except MoodleCallError:
            row["activemethod"] = "ERROR"

    print(f"{'cmid':<8}{'courseid':<10}{'assignment_id':<15}{'activemethod'}")
    print("-" * 50)
    for row in rows:
        print(
            f"{str(row['cmid']):<8}{str(row['courseid']):<10}"
            f"{str(row['assignment_id']):<15}{row['activemethod']}"
        )

    total = len(rows)
    none_count = sum(1 for r in rows if r["activemethod"] is None)
    btec_count = sum(1 for r in rows if r["activemethod"] == "btec")
    error_count = sum(1 for r in rows if r["activemethod"] == "ERROR")
    other = {}
    for r in rows:
        m = r["activemethod"]
        if m is not None and m != "btec" and m != "ERROR":
            other[m] = other.get(m, 0) + 1

    print()
    print("=== الملخص ===")
    print(f"العدد الكلي للواجبات المفحوصة: {total}")
    print(f"activemethod = None (لا تقييم متقدم): {none_count}")
    print(f"activemethod = 'btec': {btec_count}")
    if other:
        print(f"activemethod = طرق أخرى: {other}")
    else:
        print("activemethod = طرق أخرى: لا يوجد")
    if error_count:
        print(f"تعذّر فحصها (خطأ في core_grading_get_definitions): {error_count}")


if __name__ == "__main__":
    main()
