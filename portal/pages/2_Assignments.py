import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db import get_engine
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
