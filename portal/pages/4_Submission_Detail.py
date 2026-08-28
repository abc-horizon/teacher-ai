import os
import re
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db import get_engine
from app.extractor.grade_pusher import build_feedback_comment, push_grade_to_moodle
from app.extractor.importer import client_and_courseid_for_key
from app.extractor.moodle_client import MoodleCallError
from app.grading.evaluation_service import approve_evaluation, evaluate_submission
from app.grading.grade_calculator import calculate_suggested_grade
from app.models import (
    AssignmentMap,
    AuditLog,
    CriteriaSnapshot,
    Criterion,
    CriterionResult,
    Evaluation,
    Submission,
    SubmissionFile,
    Unit,
)
from portal._deep_link import resolve_deep_link

load_dotenv()

resolve_deep_link()

LEVEL_ORDER = {"P": 0, "M": 1, "D": 2}
MIN_SUBMISSION_TEXT_LENGTH = 50


def has_usable_text(text) -> bool:
    """Single source of truth for "is there enough text to show/evaluate?" —
    a submission_text that is None, empty, or too short to mean anything is
    treated identically everywhere on this page.
    """
    return bool(text) and len(text.strip()) >= MIN_SUBMISSION_TEXT_LENGTH


def criterion_sort_key(code: str) -> tuple[int, int]:
    """Orders codes as P's, then M's, then D's; numerically within a level."""
    match = re.match(r"([A-Za-z]+)(\d+)", code)
    letter = (match.group(1) if match else code)[0].upper()
    number = int(match.group(2)) if match else 0
    return (LEVEL_ORDER.get(letter, 99), number)

st.set_page_config(page_title="Submission Detail")

st.caption(
    f"Environment: {os.getenv('APP_ENV', 'development').upper()} (local sample data)"
)
st.markdown("**اقتراح آلي — القرار للمدرّس**")

st.header("Submission Detail")

submission_id = st.session_state.get("selected_submission_id")

if submission_id is None:
    st.warning("اختر تسليمًا أولاً من صفحة Submissions.")
    st.stop()

engine = get_engine()
with Session(engine) as session:
    submission = session.get(Submission, submission_id)
    submission_file = session.exec(
        select(SubmissionFile)
        .where(SubmissionFile.submission_id == submission_id)
        .order_by(SubmissionFile.id)
    ).first()
    assignment_map = session.get(AssignmentMap, submission.assignment_map_id)
    criteria = session.exec(
        select(Criterion).where(Criterion.snapshot_id == assignment_map.snapshot_id)
    ).all()

st.write(f"Student: **{submission.student_internal_id}**")

submission_text = submission_file.extracted_text if submission_file else None
text_is_usable = has_usable_text(submission_text)

if text_is_usable:
    word_count = len(submission_text.split())
    st.caption(f"نص التسليم متاح ({word_count} كلمة) — اضغط لعرضه")
    with st.expander("📄 عرض نص التسليم", expanded=False):
        st.text_area(
            "النص المستخرج",
            value=submission_text,
            height=300,
            disabled=True,
            label_visibility="collapsed",
        )
else:
    st.info(
        f"لا يوجد نص مستخرج لهذا التسليم (أو النص أقصر من "
        f"{MIN_SUBMISSION_TEXT_LENGTH} حرفًا)."
    )

st.subheader("Assessment Criteria")
for criterion in sorted(criteria, key=lambda c: criterion_sort_key(c.code)):
    st.write(f"**{criterion.code}**: {criterion.descriptor}")

st.divider()

criteria_by_id = {criterion.id: criterion for criterion in criteria}
cache_key = f"evaluation_cache_{submission_id}"


def load_latest_evaluation_into_cache():
    with Session(engine) as session:
        evaluation = session.exec(
            select(Evaluation)
            .where(Evaluation.submission_id == submission_id)
            .order_by(Evaluation.created_at.desc())
        ).first()
        if evaluation is None:
            return None
        results = session.exec(
            select(CriterionResult).where(
                CriterionResult.evaluation_id == evaluation.id
            )
        ).all()
        return {
            "evaluation_id": evaluation.id,
            "status": evaluation.status,
            "results": sorted(
                (
                    {
                        "id": result.id,
                        "criterion_code": criteria_by_id[result.criterion_id].code,
                        "criterion_descriptor": criteria_by_id[
                            result.criterion_id
                        ].descriptor,
                        "achieved": result.achieved,
                        "evidence_quote": result.evidence_quote,
                        "feedback_draft": result.teacher_final_feedback
                        or result.feedback_draft,
                        "confidence": result.confidence,
                        "is_evidence_verified": result.is_evidence_verified,
                    }
                    for result in results
                ),
                key=lambda r: criterion_sort_key(r["criterion_code"]),
            ),
        }


if cache_key not in st.session_state:
    st.session_state[cache_key] = load_latest_evaluation_into_cache()

if st.session_state.get("approve_message"):
    st.success(st.session_state["approve_message"])
    st.session_state["approve_message"] = None


def run_evaluation():
    with Session(engine) as session:
        evaluation, results, was_truncated = evaluate_submission(
            session=session,
            submission_id=submission_id,
            criteria=criteria,
            submission_text=submission_text,
        )
        if was_truncated:
            st.warning(
                "⚠️ نص التسليم أطول من الحد المسموح به وتم اقتطاعه قبل "
                "إرساله للتقييم — قد لا يكون التقييم شاملاً لكل النص."
            )
        st.session_state[cache_key] = {
            "evaluation_id": evaluation.id,
            "status": evaluation.status,
            "results": sorted(
                (
                    {
                        "id": result.id,
                        "criterion_code": criteria_by_id[result.criterion_id].code,
                        "criterion_descriptor": criteria_by_id[
                            result.criterion_id
                        ].descriptor,
                        "achieved": result.achieved,
                        "evidence_quote": result.evidence_quote,
                        "feedback_draft": result.feedback_draft,
                        "confidence": result.confidence,
                        "is_evidence_verified": result.is_evidence_verified,
                    }
                    for result in results
                ),
                key=lambda r: criterion_sort_key(r["criterion_code"]),
            ),
        }


if not text_is_usable:
    st.info(
        f"لا يوجد نص مستخرج لتقييمه (أو النص أقصر من "
        f"{MIN_SUBMISSION_TEXT_LENGTH} حرفًا)."
    )
else:
    # One-click flow from the Moodle "🤖 قيّم بالـ AI" button: resolve_deep_link()
    # marks this submission for auto-evaluation; consume the flag once so a
    # plain page refresh or normal in-app navigation never re-triggers it.
    should_auto_evaluate = (
        st.session_state.pop("auto_evaluate_submission_id", None) == submission_id
        and st.session_state[cache_key] is None
    )
    if should_auto_evaluate:
        with st.spinner("جارٍ سحب النص وتقييمه بالذكاء الاصطناعي..."):
            run_evaluation()

    has_existing = st.session_state[cache_key] is not None
    button_label = "إعادة التقييم" if has_existing else "قيّم هذا التسليم (AI)"

    if st.button(button_label, type="primary" if not has_existing else "secondary"):
        with st.spinner("جارٍ التقييم..."):
            run_evaluation()

    cached = st.session_state[cache_key]
    if cached:
        st.subheader("نتيجة التقييم")
        st.caption(f"الحالة: {cached['status']}")

        live_results = [
            {
                "criterion_code": result["criterion_code"],
                "achieved": st.session_state.get(
                    f"achieved_{result['id']}", result["achieved"]
                ),
            }
            for result in cached["results"]
        ]
        suggested_grade = calculate_suggested_grade(live_results)
        st.info(
            f"**الدرجة المقترحة: {suggested_grade}**  \n"
            "(اقتراح آلي — القرار النهائي للمدرّس)"
        )

        for result in cached["results"]:
            with st.container(border=True):
                col_text, col_toggle = st.columns([3, 1])
                with col_text:
                    st.markdown(
                        f"**{result['criterion_code']}**: {result['criterion_descriptor']}"
                    )
                with col_toggle:
                    achieved_now = st.toggle(
                        "achieved",
                        value=result["achieved"],
                        key=f"achieved_{result['id']}",
                        label_visibility="collapsed",
                    )

                if achieved_now:
                    st.success("✅ achieved")
                else:
                    st.error("❌ not achieved")
                if achieved_now != result["achieved"]:
                    st.caption("⚠️ سيتم تسجيله كـ teacher_override عند الاعتماد")

                st.markdown(f"> {result['evidence_quote']}")
                if result.get("is_evidence_verified") is False:
                    st.warning(
                        "⚠️ الدليل لم يُطابق نص التسليم حرفياً — يُرجى التحقق يدوياً"
                    )

                st.text_area(
                    "ملاحظة المسودة (قابلة للتعديل)",
                    value=result["feedback_draft"],
                    key=f"feedback_{result['id']}",
                )

                st.caption(f"Confidence: {result['confidence']:.2f}")

        if cached["status"] == "draft":
            if st.button("اعتماد محلي", type="primary"):
                updates = {}
                for result in cached["results"]:
                    new_achieved = st.session_state.get(
                        f"achieved_{result['id']}", result["achieved"]
                    )
                    new_feedback = st.session_state.get(
                        f"feedback_{result['id']}", result["feedback_draft"]
                    )
                    entry = {}
                    if new_achieved != result["achieved"]:
                        entry["achieved"] = new_achieved
                    if new_feedback != result["feedback_draft"]:
                        entry["teacher_final_feedback"] = new_feedback
                    if entry:
                        updates[result["id"]] = entry

                with Session(engine) as session:
                    approve_evaluation(
                        session=session,
                        evaluation_id=cached["evaluation_id"],
                        criterion_result_updates=updates,
                        actor="teacher-local",
                    )

                st.session_state[cache_key] = load_latest_evaluation_into_cache()
                st.session_state["approve_message"] = "تم الاعتماد بنجاح."
                st.rerun()
        else:
            st.info("تم اعتماد هذا التقييم بالفعل.")

            if submission.moodle_userid is None:
                st.caption(
                    "هذا تسليم تجريبي (رفع يدوي) غير مرتبط بطالب حقيقي على Moodle — "
                    "لا يمكن إرسال نتيجته."
                )
            else:
                st.subheader("إرسال النتيجة إلى Moodle")
                st.caption(
                    "تُكتب الدرجة الإجمالية (Refer/Pass/Merit/Distinction) وملخص كل "
                    "معيار كتعليق واحد في Moodle — وليس شبكة BTEC الرسمية لكل معيار "
                    "على حدة (نص معايير BTEC غير قابل للكتابة عبر أي Moodle API حاليًا، "
                    "انظر docs/moodle_data_access_plan.md)."
                )

                with Session(engine) as session:
                    last_push = session.exec(
                        select(AuditLog)
                        .where(
                            AuditLog.entity_type == "Evaluation",
                            AuditLog.entity_id == cached["evaluation_id"],
                            AuditLog.action == "push_to_moodle",
                        )
                        .order_by(AuditLog.timestamp.desc())
                    ).first()
                if last_push:
                    st.success(
                        f"أُرسل إلى Moodle بتاريخ {last_push.timestamp:%Y-%m-%d %H:%M} "
                        f"({last_push.details})."
                    )

                live_results = [
                    {
                        "criterion_code": result["criterion_code"],
                        "achieved": result["achieved"],
                    }
                    for result in cached["results"]
                ]
                grade_label = calculate_suggested_grade(live_results)
                feedback_html = build_feedback_comment(
                    [
                        {
                            "code": result["criterion_code"],
                            "achieved": result["achieved"],
                            "feedback": result["feedback_draft"],
                        }
                        for result in cached["results"]
                    ]
                )

                with st.expander("📋 معاينة ما سيُرسَل إلى Moodle", expanded=False):
                    st.write(f"**الدرجة**: {grade_label}")
                    st.markdown(feedback_html, unsafe_allow_html=True)

                button_label = (
                    "إعادة الإرسال إلى Moodle" if last_push else "إرسال إلى Moodle الآن"
                )
                if st.button(button_label):
                    with st.spinner("جارٍ الإرسال إلى Moodle..."):
                        try:
                            with Session(engine) as session:
                                snapshot = session.get(
                                    CriteriaSnapshot, assignment_map.snapshot_id
                                )
                                unit = session.get(Unit, snapshot.unit_id)
                            push_client, _ = client_and_courseid_for_key(unit.zoho_unit_id)
                            push_grade_to_moodle(
                                assignment_id=assignment_map.moodle_assign_id,
                                userid=submission.moodle_userid,
                                grade_label=grade_label,
                                feedback_html=feedback_html,
                                client=push_client,
                            )
                        except MoodleCallError as exc:
                            st.error(f"فشل الإرسال إلى Moodle: {exc}")
                        else:
                            with Session(engine) as session:
                                session.add(
                                    AuditLog(
                                        actor="teacher-local",
                                        action="push_to_moodle",
                                        entity_type="Evaluation",
                                        entity_id=cached["evaluation_id"],
                                        details=f"grade={grade_label}",
                                    )
                                )
                                session.commit()
                            st.success("تم الإرسال إلى Moodle بنجاح.")
                            st.rerun()
