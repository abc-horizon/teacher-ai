import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.grading.evaluation_service import approve_evaluation, evaluate_submission
from app.models import (
    AssignmentMap,
    AuditLog,
    CriteriaSnapshot,
    Criterion,
    CriterionResult,
    Evaluation,
    Submission,
    Unit,
)

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"

SUBMISSION_TEXT = (
    "Coal, oil and natural gas are fossil fuels. Coal is extracted by mining. "
    "Oil and gas are extracted by drilling. These fuels are used for power "
    "generation and transport."
)


@pytest.fixture(scope="module")
def evaluated_submission():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    assessment_criteria = json.loads(
        (SAMPLE_DATA_DIR / "sustainable-energy-assessment-criteria.json").read_text(
            encoding="utf-8"
        )
    )

    with Session(engine) as session:
        unit = Unit(zoho_unit_id="28", name="Sustainable Energy")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        for item in assessment_criteria["criteria"]:
            session.add(
                Criterion(
                    snapshot_id=snapshot.id,
                    code=item["criterion_code"],
                    descriptor=item["criterion_text"],
                )
            )
        session.commit()

        criteria = session.exec(
            select(Criterion).where(Criterion.snapshot_id == snapshot.id)
        ).all()

        assignment_map = AssignmentMap(moodle_assign_id=9999, snapshot_id=snapshot.id)
        session.add(assignment_map)
        session.commit()
        session.refresh(assignment_map)

        submission = Submission(
            assignment_map_id=assignment_map.id,
            moodle_submission_id=1,
            student_internal_id="S-9001",
            submitted_at=datetime.utcnow(),
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)

        evaluation, results = evaluate_submission(
            session=session,
            submission_id=submission.id,
            criteria=criteria,
            submission_text=SUBMISSION_TEXT,
        )

        return {
            "engine": engine,
            "submission_id": submission.id,
            "evaluation_id": evaluation.id,
            "criteria_count": len(criteria),
            "result_ids": [result.id for result in results],
        }


def test_full_evaluation_stores_draft_evaluation_and_results(evaluated_submission):
    engine = evaluated_submission["engine"]

    with Session(engine) as session:
        evaluation = session.get(Evaluation, evaluated_submission["evaluation_id"])
        results = session.exec(
            select(CriterionResult).where(
                CriterionResult.evaluation_id == evaluation.id
            )
        ).all()

    assert evaluation.status == "draft"
    assert evaluation.submission_id == evaluated_submission["submission_id"]
    assert len(results) == evaluated_submission["criteria_count"]
    for result in results:
        assert result.evidence_quote
        assert 0.0 <= result.confidence <= 1.0
        assert result.teacher_override is False


def test_approve_evaluation_with_manual_override_records_audit_log(
    evaluated_submission,
):
    engine = evaluated_submission["engine"]
    evaluation_id = evaluated_submission["evaluation_id"]

    with Session(engine) as session:
        results = session.exec(
            select(CriterionResult).where(
                CriterionResult.evaluation_id == evaluation_id
            )
        ).all()
        flipped_result = results[0]
        flipped_id = flipped_result.id
        original_achieved = flipped_result.achieved
        untouched_ids = [r.id for r in results if r.id != flipped_id]

        approve_evaluation(
            session=session,
            evaluation_id=evaluation_id,
            criterion_result_updates={
                flipped_id: {
                    "achieved": not original_achieved,
                    "teacher_final_feedback": "Manually reviewed by teacher.",
                }
            },
            actor="teacher-local",
        )

    with Session(engine) as session:
        flipped_after = session.get(CriterionResult, flipped_id)
        untouched_after = [session.get(CriterionResult, rid) for rid in untouched_ids]
        audit_logs = session.exec(
            select(AuditLog).where(
                AuditLog.entity_type == "Evaluation",
                AuditLog.entity_id == evaluation_id,
            )
        ).all()

    assert flipped_after.achieved == (not original_achieved)
    assert flipped_after.teacher_override is True
    assert flipped_after.teacher_final_feedback == "Manually reviewed by teacher."
    for other in untouched_after:
        assert other.teacher_override is False

    assert len(audit_logs) == 1
    assert audit_logs[0].actor == "teacher-local"
    assert audit_logs[0].action == "approve_evaluation"
    assert audit_logs[0].entity_type == "Evaluation"
    assert audit_logs[0].entity_id == evaluation_id


def test_approve_evaluation_transitions_status_from_draft_to_approved(
    evaluated_submission,
):
    # Relies on the approve() call in the previous test having already
    # committed to the shared in-memory engine for this module.
    engine = evaluated_submission["engine"]
    evaluation_id = evaluated_submission["evaluation_id"]

    with Session(engine) as session:
        evaluation = session.get(Evaluation, evaluation_id)

    assert evaluation.status == "approved"


def _make_criterion_and_submission(session, code, descriptor):
    unit = Unit(zoho_unit_id=f"ZU-EV-{code}", name="Evidence Verification Unit")
    session.add(unit)
    session.commit()
    session.refresh(unit)

    snapshot = CriteriaSnapshot(unit_id=unit.id)
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)

    criterion = Criterion(snapshot_id=snapshot.id, code=code, descriptor=descriptor)
    session.add(criterion)
    session.commit()
    session.refresh(criterion)

    assignment_map = AssignmentMap(
        moodle_assign_id=hash(code) % 1_000_000, snapshot_id=snapshot.id
    )
    session.add(assignment_map)
    session.commit()
    session.refresh(assignment_map)

    submission = Submission(
        assignment_map_id=assignment_map.id,
        moodle_submission_id=1,
        student_internal_id="S-EV-1",
        submitted_at=datetime.utcnow(),
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)

    return criterion, submission


def test_is_evidence_verified_true_when_quote_matches_submission_verbatim(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    submission_text = "Coal is a fossil fuel used for electricity generation."

    monkeypatch.setattr(
        "app.grading.evaluation_service.llm_evaluate",
        lambda prompt: {
            "criteria_results": [
                {
                    "criterion_code": "P1",
                    "achieved": True,
                    "evidence_quote": submission_text,
                    "feedback_draft": "Good description.",
                    "confidence": 0.9,
                }
            ]
        },
    )

    with Session(engine) as session:
        criterion, submission = _make_criterion_and_submission(
            session, "P1", "Describe a fossil fuel"
        )
        _evaluation, results = evaluate_submission(
            session=session,
            submission_id=submission.id,
            criteria=[criterion],
            submission_text=submission_text,
        )

    assert results[0].is_evidence_verified is True


def test_is_evidence_verified_false_when_quote_does_not_match_submission(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    submission_text = "Coal is a fossil fuel used for electricity generation."

    monkeypatch.setattr(
        "app.grading.evaluation_service.llm_evaluate",
        lambda prompt: {
            "criteria_results": [
                {
                    "criterion_code": "P2",
                    "achieved": True,
                    "evidence_quote": "This exact sentence never appears in the submission.",
                    "feedback_draft": "Good description.",
                    "confidence": 0.9,
                }
            ]
        },
    )

    with Session(engine) as session:
        criterion, submission = _make_criterion_and_submission(
            session, "P2", "Describe a fossil fuel"
        )
        _evaluation, results = evaluate_submission(
            session=session,
            submission_id=submission.id,
            criteria=[criterion],
            submission_text=submission_text,
        )

    assert results[0].is_evidence_verified is False
