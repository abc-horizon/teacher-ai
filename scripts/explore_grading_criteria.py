"""Explore whether BTEC assessment criteria (rubrics/marking guides) are
reachable through the Moodle Web Services API for this token.

Read-only. Self-contained on purpose (does not import scripts/
test_moodle_connection.py, since `python scripts/this_file.py` does not put
the project root on sys.path — only this file's own directory).
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


def summarize_safe(data) -> str:
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


def find_sample_criterion(node, path=""):
    """Walks the JSON tree for the first dict with a non-empty 'description'
    string — the shared marker field for rubric/guide criteria in Moodle's
    advanced grading schemas. Returns (path, dict) or None.

    Deliberately schema-agnostic: printing the exact response only tells us
    for certain what Moodle returns, rather than assuming remembered field
    names are still accurate for this Moodle version.
    """
    if isinstance(node, list):
        for index, item in enumerate(node):
            found = find_sample_criterion(item, f"{path}[{index}]")
            if found:
                return found
    elif isinstance(node, dict):
        description = node.get("description")
        if isinstance(description, str) and description.strip():
            return path, node
        for key, value in node.items():
            found = find_sample_criterion(value, f"{path}.{key}" if path else key)
            if found:
                return found
    return None


def main():
    print("=== استكشاف الوصول لمعايير التقييم (BTEC criteria) عبر Moodle API ===")
    print(f"MOODLE_URL: {MOODLE_URL or '(غير مضبوط)'}\n")

    if not MOODLE_URL or not MOODLE_TOKEN:
        print("✗ MOODLE_URL أو MOODLE_TOKEN غير مضبوطين في .env — أوقفت التنفيذ.")
        return

    results = {}

    # --- تحضير: mod_assign_get_assignments بلا courseids يرجع كل الواجبات
    # التي يراها التوكن في استدعاء واحد (أسرع بكثير من فحص كل مادة على حدة) ---
    print("تحضير: جلب كل الواجبات الحقيقية المتاحة لهذا التوكن (بلا courseids)...")
    all_assignment_cmids = []
    real_course_id = None
    assignment_cmid = None
    assignment_id = None
    try:
        assign_data = call_moodle("mod_assign_get_assignments")
        for c in assign_data.get("courses", []):
            for a in c.get("assignments", []):
                all_assignment_cmids.append((c.get("id"), a.get("id"), a.get("cmid")))
        if all_assignment_cmids:
            real_course_id, assignment_id, assignment_cmid = all_assignment_cmids[0]
        print(
            f"   ✓ وجدت {len(all_assignment_cmids)} واجب حقيقي عبر "
            f"{len(assign_data.get('courses', []))} مادة (site-wide، بدون فحص متسلسل)\n"
        )
    except MoodleCallError as exc:
        print(f"   ✗ فشل mod_assign_get_assignments: {exc}\n")

    # --- المجموعة 1: دوال التقييم المتقدم ---
    # نختبر كل الواجبات الحقيقية الموجودة (وليس أول واحد فقط) لأن accessexception
    # قد يكون خاصًا بواجب معيّن أو عامًا لكل التوكن — الفرق مهم للتشخيص.
    definition_id = None
    if not all_assignment_cmids:
        skip_test(
            "1", "core_grading_get_definitions", "لا يوجد أي cmid لواجب حقيقي", results
        )
    else:
        print(f"1. core_grading_get_definitions (على {len(all_assignment_cmids)} واجب حقيقي، كل واحد على حدة)")
        any_success = False
        for course_id, assign_id, cmid in all_assignment_cmids:
            try:
                definitions_data = call_moodle(
                    "core_grading_get_definitions", cmids=[cmid], areaname="submissions"
                )
                any_success = True
                print(f"   ✓ نجح على cmid={cmid} (course={course_id}, assignment={assign_id})")
                print(summarize_safe(definitions_data))
                for area in definitions_data.get("areas", []):
                    print(
                        f"       area: areaname={area.get('areaname')!r}, "
                        f"activemethod={area.get('activemethod')!r}"
                    )
                    for definition in area.get("definitions", []):
                        print(f"       حقول definition: {sorted(definition.keys())}")
                        if definition.get("id") is not None:
                            definition_id = definition.get("id")
                found = find_sample_criterion(definitions_data)
                if found:
                    path, criterion = found
                    print(f"   >>> وُجد عنصر يشبه معيارًا عند: {path}")
                    print(f"       حقوله: {sorted(criterion.keys())}")
                    print(f"       عيّنة الوصف: {criterion.get('description')!r}")
                else:
                    print("   >>> لا يوجد حقل 'description' غير فارغ في النتيجة.")
            except MoodleCallError as exc:
                print(f"   ✗ فشل على cmid={cmid} (course={course_id}, assignment={assign_id}): {exc}")
        results["core_grading_get_definitions"] = any_success
        print()

    if definition_id is not None:
        run_test(
            "2",
            "gradingform_rubric_get_definition",
            results,
            definitionid=definition_id,
            returndetails=1,
        )
    else:
        run_test("2", "gradingform_rubric_get_definition", results)

    run_test("3", "core_grading_get_gradingform_instances", results)

    # --- المجموعة 2: دوال معلومات المقرر ---
    if real_course_id is None:
        skip_test("4", "core_course_get_contents", "لا يوجد courseid حقيقي", results)
        skip_test(
            "5", "core_course_get_courses_by_field", "لا يوجد courseid حقيقي", results
        )
    else:
        contents_data = run_test(
            "4", "core_course_get_contents", results, courseid=real_course_id
        )
        if contents_data:
            activity_kinds = {}
            for section in contents_data:
                for module in section.get("modules", []):
                    modname = module.get("modname", "?")
                    activity_kinds[modname] = activity_kinds.get(modname, 0) + 1
            print(f"   >>> أنواع الأنشطة الموجودة في المادة: {activity_kinds}\n")

        by_field_data = run_test(
            "5",
            "core_course_get_courses_by_field",
            results,
            field="id",
            value=real_course_id,
        )
        if by_field_data:
            for course in by_field_data.get("courses", []):
                customfields = course.get("customfields")
                if customfields:
                    print(f"   >>> customfields موجودة على المادة: {customfields}")
                else:
                    print("   >>> لا يوجد customfields على هذه المادة.")
            print()

    # --- المجموعة 3: استكشاف عام عبر قائمة الدوال المتاحة ---
    site_info = run_test("6", "core_webservice_get_site_info", results)
    keywords = ["grad", "btec", "rubric", "criteri", "mzi", "zoho"]
    if site_info and "functions" in site_info:
        matches = [
            fn["name"]
            for fn in site_info["functions"]
            if any(kw in fn["name"].lower() for kw in keywords)
        ]
        print(f"   >>> دوال تحتوي إحدى الكلمات المفتاحية {keywords}:")
        if matches:
            for name in sorted(matches):
                print(f"       - {name}")
        else:
            print("       (لا توجد)")
        print(f"   >>> إجمالي عدد كل الدوال المتاحة لهذا التوكن: {len(site_info['functions'])}")
    print()

    # --- جدول النتائج ---
    print("=== جدول النتائج ===")
    for wsfunction, ok in results.items():
        if ok is True:
            status = "✓ متاح"
        elif ok is False:
            status = "✗ ممنوع/فشل"
        else:
            status = "⊘ لم يُختبر"
        print(f"  {wsfunction}: {status}")

    # --- التحليل النهائي بالعربية ---
    print("\n=== التحليل ===")
    if results.get("core_grading_get_definitions") is True:
        print(
            "core_grading_get_definitions نجحت. هذه هي الدالة الصحيحة لجلب تعريف "
            "الـ rubric/marking guide المرتبط بواجب معيّن عبر cmid — إن ظهرت في "
            "الأعلى بنية rubric_criteria/guide_criteria بنصوص فعلية، فمعايير BTEC "
            "متاحة عبر هذه الدالة مباشرة، بشرط أن يكون الواجب نفسه مُعدًّا بطريقة "
            "Advanced Grading (rubric/guide) داخل Moodle وليس بتقدير بسيط."
        )
    elif results.get("core_grading_get_definitions") is False:
        print(
            "core_grading_get_definitions فشلت لهذا التوكن/الواجب — إما التوكن لا "
            "يملك صلاحية الوصول لتقييم متقدم، أو الواجب المُختبر لا يستخدم "
            "rubric/guide أصلاً."
        )
    else:
        print(
            "core_grading_get_definitions لم تُختبر (لم نجد واجبًا حقيقيًا للاختبار "
            "عليه) — لا يمكن الحكم بعد."
        )
    print(
        "إن لم تُرجع core_grading_get_definitions معايير فعلية، فمصدر معايير BTEC "
        "الحقيقي على الأرجح ليس Moodle rubric بل مصدر خارجي (Zoho، حسب "
        "zoho_unit_id في نموذج Unit الحالي في المشروع) — وهذا يطابق افتراض "
        "المشروع الحالي أصلاً بأن المعايير تأتي من مكان غير Moodle."
    )


if __name__ == "__main__":
    main()
