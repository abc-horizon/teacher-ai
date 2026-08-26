"""T1.3 trial run: fetch real courses/assignments/submissions from Moodle
and print what was found. Read-only end to end — no write wsfunction is
called, and nothing is written to the project database at this stage.

Terminal-output rule: real Moodle userid/fullname/email never printed —
students are shown as S-001, S-002, ... assigned locally for this run only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extractor.moodle_client import MoodleCallError, call_moodle
from app.extractor.sync import (
    fetch_assignments,
    fetch_courses,
    fetch_submissions,
    fetch_user_names,
)


def anonymize_map(user_ids):
    return {uid: f"S-{i + 1:03d}" for i, uid in enumerate(sorted(set(user_ids)))}


def summarize_files(files):
    """Never print a raw filename — students sometimes put their own name in
    it (e.g. "energy exam ziad.docx"). Summarize by extension + count only.
    """
    from collections import Counter

    extensions = Counter()
    for f in files:
        filename = f.get("filename") or ""
        if "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()
        else:
            ext = "(بلا امتداد)"
        extensions[ext] += 1

    if not extensions:
        return "(لا ملفات مرفقة)"
    return ", ".join(
        f"ملف .{ext} ({count} ملفات)" if ext != "(بلا امتداد)" else f"{ext} ({count})"
        for ext, count in sorted(extensions.items())
    )


def main():
    print("=== 1. جلب كل المواد الحقيقية ===")
    try:
        courses = fetch_courses()
    except MoodleCallError as exc:
        print(f"✗ فشل fetch_courses: {exc}")
        return
    print(f"عدد المواد الحقيقية: {len(courses)}\n")

    print("=== 2. البحث عن مادة 'Sustainable Energy' ===")
    matches = [
        c
        for c in courses
        if "sustainable energy"
        in f"{c.get('fullname', '')} {c.get('shortname', '')}".lower()
    ]
    if not matches:
        print("لم يُعثر على أي مادة بهذا الاسم بين المواد المتاحة لهذا التوكن.\n")
    else:
        for c in matches:
            print(f"  id={c['id']} | shortname={c['shortname']!r}")
        print()

    target_ids = [c["id"] for c in matches]

    print("=== 3. جلب واجبات هذه المادة/المواد ===")
    try:
        assignments = fetch_assignments(target_ids) if target_ids else []
    except MoodleCallError as exc:
        print(f"✗ فشل fetch_assignments: {exc}")
        assignments = []
    if assignments:
        for a in assignments:
            print(f"  id={a['id']} | cmid={a['cmid']} | name={a['name']!r}")
    else:
        print("لا توجد واجبات مرئية لهذا التوكن ضمن مادة/مواد Sustainable Energy.")
    print()

    if not assignments:
        print(
            "=== fallback: لا يوجد واجب مستهدف لاختبار الخطوتين 4 و5 عليه، "
            "أستخدم أي واجب متاح فعليًا لهذا التوكن لإثبات أن المسار يعمل ==="
        )
        try:
            raw = call_moodle("mod_assign_get_assignments")
        except MoodleCallError as exc:
            print(f"✗ فشل حتى الـ fallback: {exc}")
            return
        for course in raw.get("courses", []):
            for a in course.get("assignments", []):
                assignments.append(
                    {
                        "id": a.get("id"),
                        "cmid": a.get("cmid"),
                        "course": course.get("id"),
                        "name": a.get("name"),
                        "duedate": a.get("duedate"),
                    }
                )
        if not assignments:
            print("لا يوجد أي واجب مرئي لهذا التوكن إطلاقًا. توقفت هنا.")
            return
        print(f"استخدمت أول واجب متاح: cmid={assignments[0]['cmid']}\n")

    first_assignment = assignments[0]

    print("=== 4. تسليمات أول واجب ===")
    try:
        submissions = fetch_submissions([first_assignment["id"]])
    except MoodleCallError as exc:
        print(f"✗ فشل fetch_submissions: {exc}")
        return

    total = len(submissions)
    submitted_count = sum(1 for s in submissions if s.get("status") == "submitted")
    print(f"العدد الكلي للتسليمات: {total}")
    print(f"عدد الحالة status='submitted': {submitted_count}")

    student_ids = [s["userid"] for s in submissions if s.get("userid") is not None]
    anon = anonymize_map(student_ids)

    print("ملفات كل تسليم (امتداد وعدد فقط — لا أسماء ملفات كاملة، قد تحتوي اسم الطالب):")
    if not submissions:
        print("  (لا توجد تسليمات)")
    for s in submissions:
        label = anon.get(s.get("userid"), "S-???")
        print(f"  {label}: {summarize_files(s.get('files', []))}")
    print()

    print("=== 5. اختبار fetch_user_names ===")
    course_id_for_names = first_assignment.get("course")
    if not student_ids or course_id_for_names is None:
        print("لا يوجد userid أو courseid كافٍ لاختبار هذه الدالة.")
    else:
        try:
            names = fetch_user_names(course_id_for_names, student_ids)
            print(f"تم جلب {len(names)} اسماً بنجاح.")
        except MoodleCallError as exc:
            print(f"✗ فشل fetch_user_names: {exc}")


if __name__ == "__main__":
    main()
