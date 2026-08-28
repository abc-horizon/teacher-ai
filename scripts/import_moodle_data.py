"""T1.3 CLI wrapper: import real Moodle course/assignment/submission data
into the local project database (app_dev.db) so it shows up in the portal.

All actual logic lives in app/extractor/importer.py (shared with the portal
pages) — this script is only a thin command-line entry point for manual /
admin use (e.g. onboarding a brand-new course).

Terminal-output rule: never print MOODLE_TOKEN, a student name, an email, or
a raw userid. The summary this script prints reports counts only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse

from app.extractor.importer import sync_course
from app.extractor.moodle_client import MoodleCallError, default_client, lms_client


def main():
    parser = argparse.ArgumentParser(description="Import real Moodle data into app_dev.db")
    parser.add_argument("--courseid", type=int, default=373)
    parser.add_argument(
        "--site",
        choices=["elearning", "lms"],
        default="elearning",
        help="which Moodle instance courseid refers to (default: elearning)",
    )
    args = parser.parse_args()
    client = lms_client if args.site == "lms" else default_client

    print(f"=== استيراد بيانات Moodle ({args.site}) لمادة courseid={args.courseid} ===\n")
    try:
        counters = sync_course(args.courseid, client=client)
    except MoodleCallError as exc:
        print(f"✗ فشل الاستيراد: {exc}")
        return

    print("=== الملخص ===")
    print(f"Unit — جديد: {counters['unit_created']} | موجود مسبقًا: {counters['unit_existing']}")
    if not counters["criteria_available"]:
        print(
            "⏳ لا توجد معايير تقييم محلية لهذه المادة بعد "
            "(انظر app/extractor/importer.py:CRITERIA_FILE_BY_COURSE_KEY) — "
            "توقّفت المزامنة هنا، لم تُستورد أي واجبات أو تسليمات."
        )
        return
    print(f"معايير مُدرَجة (عند إنشاء snapshot جديد فقط): {counters['criteria_created']}")
    print(
        f"AssignmentMap — جديد: {counters['assignments_created']} "
        f"| موجود مسبقًا: {counters['assignments_existing']}"
    )
    print(
        f"Submission — جديد: {counters['submissions_created']} "
        f"| موجود مسبقًا (تم تخطّيه): {counters['submissions_existing']} "
        f"| متجاوَز (لم يُسلَّم بعد): {counters['submissions_skipped_not_submitted']}"
    )
    print(
        f"SubmissionFile — جديد: {counters['files_created']} "
        f"| fileurl مُحدَّث لملفات قديمة: {counters['files_backfilled']}"
    )


if __name__ == "__main__":
    main()
