import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db import get_engine
from app.extractor.importer import client_and_courseid_for_key, sync_course
from app.extractor.moodle_client import MoodleCallError
from app.models import AssignmentMap, CriteriaSnapshot, Unit

load_dotenv()

st.set_page_config(page_title="Assignments")

st.caption(
    f"Environment: {os.getenv('APP_ENV', 'development').upper()} (local sample data)"
)
st.markdown("**اقتراح آلي — القرار للمدرّس**")

st.header("Assignments")

unit_id = st.session_state.get("selected_unit_id")

if unit_id is None:
    st.warning("اختر وحدة أولاً من صفحة Units.")
else:
    engine = get_engine()
    with Session(engine) as session:
        unit = session.get(Unit, unit_id)
        assignment_maps = session.exec(
            select(AssignmentMap)
            .join(CriteriaSnapshot, AssignmentMap.snapshot_id == CriteriaSnapshot.id)
            .where(CriteriaSnapshot.unit_id == unit_id)
        ).all()

    st.write(f"Unit: **{unit.zoho_unit_id} — {unit.name}**")

    if st.button("🔄 تحديث من Moodle"):
        with st.spinner("جارٍ الاتصال بـ Moodle وجلب الواجبات..."):
            try:
                client, courseid = client_and_courseid_for_key(unit.zoho_unit_id)
                counters = sync_course(courseid, client=client)
            except MoodleCallError as exc:
                st.error(f"فشل الاتصال بـ Moodle: {exc}")
            except ValueError:
                st.error("لا يمكن مزامنة هذه الوحدة — معرّفها ليس رقم مادة Moodle صالحًا.")
            else:
                st.success(
                    f"تم التحديث — واجبات جديدة: {counters['assignments_created']}، "
                    f"موجودة مسبقًا: {counters['assignments_existing']}، "
                    f"تسليمات جديدة: {counters['submissions_created']}"
                )
                st.rerun()

    if not assignment_maps:
        st.info("No assignments found for this unit.")
    else:
        for assignment_map in assignment_maps:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"Assignment (Moodle ID: {assignment_map.moodle_assign_id})")
            with col2:
                if st.button("Open", key=f"assignment-{assignment_map.id}"):
                    st.session_state["selected_assignment_map_id"] = assignment_map.id
                    st.switch_page("pages/3_Submissions.py")
