"""Diagnostic for direct Moodle SQL access (app/extractor/moodle_db.py).

Run this FIRST after setting the MOODLE_DB_* variables in .env — it proves
the credential works and points at the right Moodle instance, before any
other code depends on it.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/check_moodle_db.py

Everything here is read-only. The script also resolves the BTEC fillings
table's real name (plural vs singular — see
docs/moodle_data_access_plan.md 2-ج), which was an open question in the
access plan until a live database could answer it.

Terminal-output rule (same as the other scripts): no password is printed,
no student name, no email, no raw userid. Criterion text IS printed — it is
course material, not personal data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extractor import moodle_db
from app.extractor.moodle_client import MoodleCallError
from app.extractor.sync import fetch_grading_definition, fetch_grading_instances

# The Sustainable Energy assignment on elearning.abchorizon.com, used as the
# known-good probe target because its definition (16005) and instances are
# already verified live. Override with argv to check a different assignment.
DEFAULT_CMID = 1640


def main():
    cmid = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CMID

    print("=== 1. الإعداد الحالي (بلا كلمة المرور) ===")
    for key, value in moodle_db.describe_config().items():
        print(f"  {key:14} {value}")
    print()

    if not moodle_db.is_configured():
        print("✗ لم تُضبط متغيّرات MOODLE_DB_* في .env — توقفت هنا.")
        print("  راجع docstring في app/extractor/moodle_db.py.")
        return 1

    print("=== 2. الاتصال + اسم جدول الـ fillings ===")
    report = moodle_db.check_access()
    if report["error"]:
        print(f"✗ {report['error']}")
        return 1
    print(f"  ✓ متصل. جدول الـ fillings: {report['fillings_table']}")
    print(f"  ✓ عدد صفوف المعايير في القاعدة كلها: {report['criteria_rows']}")
    print()

    print(f"=== 3. تعريف التقييم لهذا الواجب (cmid={cmid}) — عبر API ===")
    try:
        definition = fetch_grading_definition(cmid)
    except MoodleCallError as exc:
        print(f"✗ فشل استدعاء API: {exc}")
        return 1
    if definition is None:
        print(f"✗ لا يوجد تقييم متقدم بطريقة 'btec' على cmid={cmid}.")
        return 1
    print(f"  definition_id={definition['definition_id']} "
          f"name={definition['name']!r} ready={definition['is_ready']}")
    print()

    definition_id = definition["definition_id"]

    print("=== 4. نص المعايير الحقيقي — عبر SQL (الفجوة التي نغلقها) ===")
    criteria = moodle_db.fetch_criteria(definition_id)
    if not criteria:
        print("  ⚠ صفر معايير لهذا التعريف. تحقق أن القاعدة هي قاعدة نفس الموقع")
        print("    الذي جاء منه definition_id أعلاه (elearning ≠ lms).")
        return 1
    print(f"  عدد المعايير: {len(criteria)}")
    for criterion in criteria:
        text = criterion["criterion_text"]
        preview = text if len(text) <= 90 else text[:87] + "..."
        print(f"   {criterion['source_code']:8} [{criterion['level']:11}] {preview}")
    print()

    print("=== 5. حكم المدرّس لكل معيار — عبر SQL ===")
    try:
        instances = fetch_grading_instances(definition_id)
    except MoodleCallError as exc:
        print(f"✗ فشل جلب المثائل: {exc}")
        return 1
    if not instances:
        print("  (لا مثائل تقييم لهذا التعريف)")
        return 0

    instance = instances[0]
    print(f"  مثال على مثيل واحد: instance_id={instance['instance_id']} "
          f"itemid={instance['itemid']}")
    judgements = moodle_db.fetch_fillings(instance["instance_id"], definition_id)
    judged = [j for j in judgements if j["was_judged"]]
    print(f"  معايير مُحكَّمة: {len(judged)} من {len(judgements)}")
    for judgement in judgements:
        if not judgement["was_judged"]:
            continue
        remark = judgement["teacher_remark"] or "(بلا ملاحظة)"
        if len(remark) > 60:
            remark = remark[:57] + "..."
        mark = "✓" if judgement["achieved"] else "✗"
        print(f"   {mark} {judgement['source_code']:8} score={judgement['score']} "
              f"| {remark}")

    print()
    print("✓ كل المسارات تعمل. نص المعايير وأحكام المدرّس متاحة الآن للنظام.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
