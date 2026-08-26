"""Read-only exploration of which Moodle Web Service functions this token
can call, before anything is built on top of them. Never calls a write
function (e.g. mod_assign_save_grade) and never prints MOODLE_TOKEN.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extractor.moodle_client import MOODLE_TOKEN, MOODLE_URL, MoodleCallError, call_moodle  # noqa: E402


def summarize_safe(data) -> str:
    """Structure only: counts and field names, never field values."""
    if isinstance(data, list):
        line = f"     → list, {len(data)} عنصر"
        if data and isinstance(data[0], dict):
            line += f"\n     → حقول العنصر: {sorted(data[0].keys())}"
        return line
    if isinstance(data, dict):
        return f"     → dict, الحقول: {sorted(data.keys())}"
    return f"     → {type(data).__name__}"


def run_test(label, wsfunction, results, **params):
    print(f"{label}. {wsfunction}")
    try:
        data = call_moodle(wsfunction, **params)
        print("   ✓ نجح")
        print(summarize_safe(data))
        results[wsfunction] = True
        print()
        return data
    except MoodleCallError as exc:
        print(f"   ✗ فشل: {exc}")
        results[wsfunction] = False
        print()
        return None


def skip_test(label, wsfunction, reason, results):
    print(f"{label}. {wsfunction}")
    print(f"   ⊘ تخطّي: {reason}")
    results[wsfunction] = None
    print()


def main():
    print("=== اختبار الاتصال بـ Moodle Web Services API ===")
    print(f"MOODLE_URL: {MOODLE_URL or '(غير مضبوط)'}\n")

    if not MOODLE_URL or not MOODLE_TOKEN:
        print("✗ MOODLE_URL أو MOODLE_TOKEN غير مضبوطين في .env — أوقفت التنفيذ.")
        return

    results = {}

    run_test("1", "core_webservice_get_site_info", results)

    courses = run_test("2", "core_course_get_courses", results)
    first_course_id = None
    if isinstance(courses, list) and courses:
        first_course_id = courses[0].get("id")

    run_test("3", "core_course_get_categories", results)

    assignments_data = run_test("4", "mod_assign_get_assignments", results)
    first_assign_id = None
    if isinstance(assignments_data, dict):
        for course in assignments_data.get("courses", []):
            course_assignments = course.get("assignments", [])
            if course_assignments:
                first_assign_id = course_assignments[0].get("id")
                break

    if first_course_id is None:
        skip_test(
            "5",
            "core_enrol_get_enrolled_users",
            "لا يوجد courseid متاح من الخطوة 2",
            results,
        )
    else:
        run_test(
            "5",
            "core_enrol_get_enrolled_users",
            results,
            courseid=first_course_id,
        )

    if first_assign_id is None:
        skip_test(
            "6",
            "mod_assign_get_submissions",
            "لا يوجد assignid متاح من الخطوة 4",
            results,
        )
    else:
        run_test(
            "6",
            "mod_assign_get_submissions",
            results,
            assignmentids=[first_assign_id],
        )

    run_test(
        "7",
        "core_files_get_files",
        results,
        contextid=1,
        component="",
        filearea="",
        itemid=0,
        filepath="/",
        filename="",
    )

    if first_course_id is None:
        skip_test(
            "8",
            "gradereport_user_get_grade_items",
            "لا يوجد courseid متاح من الخطوة 2",
            results,
        )
    else:
        run_test(
            "8",
            "gradereport_user_get_grade_items",
            results,
            courseid=first_course_id,
        )

    print("=== جدول النتائج ===")
    for wsfunction, ok in results.items():
        if ok is True:
            status = "✓ متاح"
        elif ok is False:
            status = "✗ ممنوع/فشل"
        else:
            status = "⊘ لم يُختبر (لا معطيات مسبقة)"
        print(f"  {wsfunction}: {status}")

    def available(name):
        return results.get(name) is True

    print("\n=== الملخص بالعربية ===")

    working = [fn for fn, ok in results.items() if ok is True]
    blocked = [fn for fn, ok in results.items() if ok is False]
    skipped = [fn for fn, ok in results.items() if ok is None]

    print(f"ما نستطيع سحبه فعليًا ({len(working)}): {working or 'لا شيء'}")
    print(f"ما هو ممنوع/فاشل ({len(blocked)}): {blocked or 'لا شيء'}")
    if skipped:
        print(f"ما لم يُختبر لعدم توفر معطيات مسبقة ({len(skipped)}): {skipped}")

    print()
    print(f"- المواد (courses): {'نعم' if available('core_course_get_courses') else 'لا'}")
    print(
        f"- الواجبات (assignments): "
        f"{'نعم' if available('mod_assign_get_assignments') else 'لا'}"
    )
    print(
        f"- التسليمات (submissions): "
        f"{'نعم' if available('mod_assign_get_submissions') else 'لا'}"
    )
    print(
        f"- ملفات التسليمات (files): "
        f"{'نعم' if available('core_files_get_files') else 'لا'}"
    )


if __name__ == "__main__":
    main()
