import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db import get_engine
from app.models import AssignmentMap, Criterion, Submission, SubmissionFile

load_dotenv()

st.set_page_config(page_title="Submission Detail")

st.caption(
    f"Environment: {os.getenv('APP_ENV', 'development').upper()} (local sample data)"
)
st.markdown("**اقتراح آلي — القرار للمدرّس**")

st.header("Submission Detail")

submission_id = st.session_state.get("selected_submission_id")

if submission_id is None:
    st.warning("اختر تسليمًا أولاً من صفحة Submissions.")
else:
    engine = get_engine()
    with Session(engine) as session:
        submission = session.get(Submission, submission_id)
        submission_file = session.exec(
            select(SubmissionFile).where(
                SubmissionFile.submission_id == submission_id
            )
        ).first()
        assignment_map = session.get(AssignmentMap, submission.assignment_map_id)
        criteria = session.exec(
            select(Criterion).where(
                Criterion.snapshot_id == assignment_map.snapshot_id
            )
        ).all()

    st.write(f"Student: **{submission.student_internal_id}**")

    left, right = st.columns(2)
    with left:
        st.subheader("Extracted Text")
        st.write(
            submission_file.extracted_text if submission_file else "No text extracted."
        )
    with right:
        st.subheader("Assessment Criteria")
        for criterion in criteria:
            st.write(f"**{criterion.code}**: {criterion.descriptor}")
