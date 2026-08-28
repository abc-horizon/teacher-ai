import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlmodel import Session, func, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db import get_engine
from app.extractor.file_fetcher import extract_text
from app.extractor.importer import client_and_courseid_for_key, extract_pending_files, sync_course
from app.extractor.moodle_client import LMS_MOODLE_TOKEN, MoodleCallError, lms_client
from app.models import AssignmentMap, CriteriaSnapshot, Submission, SubmissionFile, Unit
from portal._deep_link import resolve_deep_link

resolve_deep_link()

load_dotenv()


def extract_text_from_upload(uploaded_file) -> tuple[str | None, str]:
    """Returns (extracted_text, extract_status)."""
    try:
        text = extract_text(uploaded_file.getvalue(), uploaded_file.name)
        return text, "success"
    except ValueError:
        return None, "unsupported_format"
    except Exception:
        return None, "failed"

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
        with Session(get_engine()) as session:
            assignment_map = session.get(AssignmentMap, assignment_map_id)
            snapshot = session.get(CriteriaSnapshot, assignment_map.snapshot_id)
            unit = session.get(Unit, snapshot.unit_id)

        with st.spinner("جارٍ الاتصال بـ Moodle وجلب التسليمات..."):
            try:
                client, courseid = client_and_courseid_for_key(unit.zoho_unit_id)
                sync_counters = sync_course(courseid, client=client)
                extract_token = LMS_MOODLE_TOKEN if client is lms_client else None
                extract_counters, _ = extract_pending_files(
                    token=extract_token, assignment_map_id=assignment_map_id
                )
            except MoodleCallError as exc:
                st.error(f"فشل الاتصال بـ Moodle: {exc}")
            else:
                st.success(
                    f"تم التحديث — تسليمات جديدة: {sync_counters['submissions_created']}، "
                    f"موجودة مسبقًا: {sync_counters['submissions_existing']}، "
                    f"ملفات استُخرج نصها الآن: {extract_counters['success']}"
                )
                st.rerun()

    with st.expander("أدوات تجريبية (رفع يدوي)", expanded=False):
        student_internal_id = st.text_input(
            "معرّف الطالب", value="", key="upload_student_id"
        )
        uploaded_file = st.file_uploader(
            "اختر ملف الواجب", type=["pdf", "docx", "txt"], key="upload_file"
        )

        if st.button("رفع ومعالجة", type="primary"):
            if not student_internal_id.strip():
                st.error("الرجاء إدخال معرّف الطالب.")
            elif uploaded_file is None:
                st.error("الرجاء اختيار ملف.")
            else:
                extracted_text, extract_status = extract_text_from_upload(
                    uploaded_file
                )
                contenthash = hashlib.sha256(uploaded_file.getvalue()).hexdigest()

                with Session(get_engine()) as session:
                    max_moodle_submission_id = session.exec(
                        select(func.max(Submission.moodle_submission_id))
                    ).first()
                    next_moodle_submission_id = (max_moodle_submission_id or 0) + 1

                    submission = Submission(
                        assignment_map_id=assignment_map_id,
                        moodle_submission_id=next_moodle_submission_id,
                        student_internal_id=student_internal_id.strip(),
                        submitted_at=datetime.utcnow(),
                    )
                    session.add(submission)
                    session.commit()
                    session.refresh(submission)

                    session.add(
                        SubmissionFile(
                            submission_id=submission.id,
                            contenthash=contenthash,
                            filename=uploaded_file.name,
                            extract_status=extract_status,
                            extracted_text=extracted_text,
                        )
                    )
                    session.commit()

                if extract_status == "success":
                    st.success("تم رفع الواجب واستخراج النص بنجاح.")
                else:
                    st.warning(
                        f"تم رفع الملف، لكن تعذّر استخراج النص (status: {extract_status})."
                    )
                st.rerun()

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
                    "student_name": submission.student_display_name
                    or submission.student_internal_id,
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
        header_cols = st.columns([2, 2, 2, 2, 1])
        header_cols[0].write("**اسم الطالب**")
        header_cols[1].write("**student_internal_id**")
        header_cols[2].write("**submitted_at**")
        header_cols[3].write("**extract_status**")

        for row in rows:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
            col1.write(row["student_name"])
            col2.write(row["student_internal_id"])
            col3.write(row["submitted_at"])
            col4.write(row["extract_status"])
            with col5:
                if st.button("Open", key=f"submission-{row['submission_id']}"):
                    st.session_state["selected_submission_id"] = row["submission_id"]
                    st.switch_page("pages/4_Submission_Detail.py")
