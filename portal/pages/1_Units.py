import html
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db import get_engine
from app.extractor.importer import may_have_criteria, sync_course
from app.extractor.moodle_client import MoodleCallError, default_client
from app.extractor.sync import fetch_courses
from app.models import CriteriaSnapshot, Unit

load_dotenv()

st.set_page_config(page_title="Units")

st.caption(
    f"Environment: {os.getenv('APP_ENV', 'development').upper()} (local sample data)"
)
st.markdown("**اقتراح آلي — القرار للمدرّس**")

st.header("Units")


@st.cache_data(ttl=300, show_spinner=False)
def _cached_fetch_courses():
    """Cached so typing in the search box below doesn't re-hit Moodle on
    every keystroke — the full course list changes rarely within a session.
    """
    return fetch_courses()


def open_unit(courseid: int):
    """Syncs (if needed) then jumps to Assignments for this Moodle course."""
    with st.spinner("جارٍ مزامنة المادة..."):
        try:
            counters = sync_course(courseid)
        except MoodleCallError as exc:
            st.error(f"فشل الاتصال بـ Moodle: {exc}")
            return
    if not counters["criteria_available"]:
        st.warning(
            "لا توجد معايير تقييم لهذه المادة — لا في قاعدة بيانات Moodle ولا "
            "في الملفات المحلية. إن كان وصول SQL مضبوطًا، فقد لا يكون لهذا "
            "الواجب تعريف تقييم BTEC جاهز (انظر docs/moodle_data_access_plan.md)."
        )
        return
    # Provenance matters to a teacher about to trust a grading run: a fixture
    # is a hand-maintained transcription that may have drifted from what is
    # configured in Moodle, whereas moodle_sql is read from Moodle itself.
    if counters.get("criteria_source", "").startswith("fixture:"):
        st.info(
            "المعايير المستخدمة من ملف محلي وليست من قاعدة بيانات Moodle "
            f"({counters['criteria_source']}) — قد تكون قديمة إن عدّلها المدرّس في Moodle."
        )
    with Session(get_engine()) as session:
        unit = session.exec(
            select(Unit).where(Unit.zoho_unit_id == str(courseid))
        ).first()
    st.session_state["selected_unit_id"] = unit.id
    st.switch_page("pages/2_Assignments.py")


engine = get_engine()
with Session(engine) as session:
    known_units = session.exec(select(Unit)).all()
    units_with_snapshot = {
        s.unit_id for s in session.exec(select(CriteriaSnapshot)).all()
    }

if known_units:
    st.subheader("موادك المُفعّلة سابقًا")
    for unit in known_units:
        ready = unit.id in units_with_snapshot
        col1, col2 = st.columns([4, 1])
        with col1:
            label = f"**{unit.zoho_unit_id}** — {unit.name}"
            st.write(label if ready else f"{label} — ⏳ لا معايير تقييم بعد")
        with col2:
            if ready and st.button("Open", key=f"unit-{unit.id}"):
                st.session_state["selected_unit_id"] = unit.id
                st.switch_page("pages/2_Assignments.py")

st.subheader("اختيار مادة أخرى من كل موادنا في Moodle")

try:
    all_courses = _cached_fetch_courses()
except MoodleCallError as exc:
    st.error(f"تعذّر الاتصال بـ Moodle: {exc}")
    all_courses = []

search = st.text_input(
    f"ابحث بالاسم ({len(all_courses)} مادة متاحة)", value="", key="unit_search"
)

if search.strip():
    query = search.strip().lower()
    matches = [
        c
        for c in all_courses
        if query in f"{c.get('fullname', '')} {c.get('shortname', '')}".lower()
    ]
    MAX_RESULTS = 30
    if not matches:
        st.info("لا توجد مادة مطابقة لهذا البحث.")
    else:
        if len(matches) > MAX_RESULTS:
            st.caption(f"{len(matches)} نتيجة — تُعرض أول {MAX_RESULTS} فقط، دقّق البحث لتضييق القائمة.")
        for course in matches[:MAX_RESULTS]:
            courseid = course["id"]
            name = html.unescape(course.get("fullname") or course.get("shortname") or str(courseid))
            ready = may_have_criteria(courseid, default_client)
            col1, col2 = st.columns([4, 1])
            with col1:
                label = f"**{courseid}** — {name}"
                st.write(label if ready else f"{label} — ⏳ لا معايير تقييم بعد")
            with col2:
                if ready:
                    if st.button("اختيار", key=f"course-{courseid}"):
                        open_unit(courseid)
else:
    st.caption("اكتب اسم المادة للبحث ضمن كل المواد المتاحة على Moodle.")
