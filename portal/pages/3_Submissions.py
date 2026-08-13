import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db import get_engine
from app.models import AssignmentMap, Submission, SubmissionFile

load_dotenv()

st.set_page_config(page_title="Submissions")

st.caption(
    f"Environment: {os.getenv('APP_ENV', 'development').upper()} (local sample data)"
)
st.markdown("**اقتراح آلي — القرار للمدرّس**")

st.header("Submissions")

assignment_map_id = st.session_state.get("selected_assignment_map_id")

if assignment_map_id is None:
    st.warning("اختر واجبًا أولاً من صفحة Assignments.")
else:
    if st.button("تحديث البيانات"):
        st.info("لا يوجد اتصال حقيقي بـ Moodle بعد (سيُضاف في T1.3).")

    engine = get_engine()
    with Session(engine) as session:
        assignment_map = session.get(AssignmentMap, assignment_map_id)
        submissions = session.exec(
            select(Submission).where(
                Submission.assignment_map_id == assignment_map_id
            )
        ).all()

        rows = []
        for submission in submissions:
            submission_file = session.exec(
                select(SubmissionFile).where(
                    SubmissionFile.submission_id == submission.id
                )
            ).first()
            rows.append(
                {
                    "submission_id": submission.id,
                    "student_internal_id": submission.student_internal_id,
                    "submitted_at": submission.submitted_at,
                    "extract_status": submission_file.extract_status
                    if submission_file
                    else "unknown",
                }
            )

    st.write(f"Assignment (Moodle ID: {assignment_map.moodle_assign_id})")

    if not rows:
        st.info("No submissions found for this assignment.")
    else:
        header_cols = st.columns([2, 2, 2, 1])
        header_cols[0].write("**student_internal_id**")
        header_cols[1].write("**submitted_at**")
        header_cols[2].write("**extract_status**")

        for row in rows:
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            col1.write(row["student_internal_id"])
            col2.write(row["submitted_at"])
            col3.write(row["extract_status"])
            with col4:
                if st.button("Open", key=f"submission-{row['submission_id']}"):
                    st.session_state["selected_submission_id"] = row["submission_id"]
                    st.switch_page("pages/4_Submission_Detail.py")
