"""Resolves a Moodle-originated deep link (?cmid=...&userid=...) into the
matching local session_state, so a teacher clicking "قيّم بالـ AI" inside
Moodle lands directly on the right assignment/submission in this portal —
instead of navigating Units -> Assignments -> Submissions manually.

Called at the top of portal/pages/3_Submissions.py and
portal/pages/4_Submission_Detail.py; a no-op when the URL has no `cmid`
param, so normal in-app navigation is unaffected.

Security note: this only ever calls Moodle from the server side (this
Streamlit process, where MOODLE_TOKEN/LMS_MOODLE_TOKEN are safely held) —
the injected Moodle-side JavaScript that builds the link never touches any
token, only the current page's own cmid/userid, already present in its URL.

Leading underscore on the filename: Streamlit's multipage router only
treats files directly under portal/pages/ as navigable pages, so this stays
an importable helper, not a sidebar entry.
"""

import streamlit as st
from sqlmodel import Session, select

from app.db import get_engine
from app.extractor.importer import sync_course
from app.extractor.moodle_client import MoodleCallError, lms_client
from app.models import AssignmentMap, Submission


def resolve_deep_link():
    params = st.query_params
    cmid = params.get("cmid")
    if not cmid:
        return

    try:
        cmid = int(cmid)
    except ValueError:
        st.error("رابط غير صالح (cmid غير رقمي).")
        st.stop()

    # Only wired for lms.abchorizon.com for now — that is the only site with
    # an injected "قيّم بالـ AI" button (see docs/moodle_ai_grade_button.html).
    try:
        cm_info = lms_client.call("core_course_get_course_module", cmid=cmid)
    except MoodleCallError as exc:
        st.error(f"تعذّر التعرّف على هذا الواجب من Moodle: {exc}")
        st.stop()

    cm = cm_info.get("cm", {})
    courseid = cm.get("course")
    instance_id = cm.get("instance")
    if cm.get("modname") != "assign" or courseid is None or instance_id is None:
        st.error("هذا الرابط لا يشير إلى واجب صالح.")
        st.stop()

    with st.spinner("جارٍ مزامنة الواجب من Moodle..."):
        try:
            counters = sync_course(courseid, client=lms_client)
        except MoodleCallError as exc:
            st.error(f"فشل الاتصال بـ Moodle: {exc}")
            st.stop()

    if not counters["criteria_available"]:
        st.warning(
            "لا توجد معايير تقييم محلية لهذه المادة بعد — بانتظار حل وصول "
            "SQL/Zoho لمعايير BTEC (انظر docs/moodle_data_access_plan.md)."
        )
        st.stop()

    with Session(get_engine()) as session:
        assignment_map = session.exec(
            select(AssignmentMap).where(AssignmentMap.moodle_assign_id == instance_id)
        ).first()
    if assignment_map is None:
        st.error("تعذّر إيجاد هذا الواجب محليًا بعد المزامنة.")
        st.stop()

    st.session_state["selected_assignment_map_id"] = assignment_map.id

    userid = params.get("userid")
    try:
        userid = int(userid) if userid else None
    except ValueError:
        userid = None

    if userid is not None:
        with Session(get_engine()) as session:
            submission = session.exec(
                select(Submission).where(
                    Submission.assignment_map_id == assignment_map.id,
                    Submission.moodle_userid == userid,
                )
            ).first()
        if submission:
            st.session_state["selected_submission_id"] = submission.id
            # Consumed once by Submission_Detail.py: run the AI evaluation
            # immediately on arrival from Moodle, matching the requested
            # one-click flow (button in Moodle -> evaluated result, no
            # separate manual "قيّم هذا التسليم" click needed in between).
            st.session_state["auto_evaluate_submission_id"] = submission.id
        else:
            st.info(
                "لم يُعثر على تسليم هذا الطالب محليًا بعد — اضغطي 'تحديث البيانات' "
                "أدناه إن كان قد سلّم للتو."
            )
