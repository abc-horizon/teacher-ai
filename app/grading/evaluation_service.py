import json
import logging

from sqlmodel import Session, select

from app.grading.llm_client import evaluate as llm_evaluate
from app.grading.prompt_builder import build_prompt
from app.grading.schemas import EvaluationResponse, validate_full_coverage
from app.models import AuditLog, Criterion, CriterionResult, Evaluation

logger = logging.getLogger(__name__)


def evaluate_submission(
    session: Session,
    submission_id: int,
    criteria: list[Criterion],
    submission_text: str,
    model_id: str = "deepseek-chat",
    prompt_version: str = "v1",
) -> tuple[Evaluation, list[CriterionResult]]:
    prompt = build_prompt(criteria, submission_text)
    raw_response = llm_evaluate(prompt)
    validated = EvaluationResponse.model_validate_json(json.dumps(raw_response))
    validate_full_coverage(validated, [criterion.code for criterion in criteria])

    criteria_by_code = {criterion.code: criterion for criterion in criteria}

    evaluation = Evaluation(
        submission_id=submission_id,
        prompt_version=prompt_version,
        model_id=model_id,
        status="draft",
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)

    results = []
    for judgment in validated.criteria_results:
        criterion = criteria_by_code[judgment.criterion_code]
        is_evidence_verified = judgment.evidence_quote in submission_text
        if not is_evidence_verified:
            logger.warning(
                "evidence_quote is not a verbatim substring of submission_text "
                "for criterion_code=%s: %r",
                judgment.criterion_code,
                judgment.evidence_quote,
            )
        result = CriterionResult(
            evaluation_id=evaluation.id,
            criterion_id=criterion.id,
            achieved=judgment.achieved,
            evidence_quote=judgment.evidence_quote,
            feedback_draft=judgment.feedback_draft,
            confidence=judgment.confidence,
            is_evidence_verified=is_evidence_verified,
        )
        session.add(result)
        results.append(result)
    session.commit()
    for result in results:
        session.refresh(result)

    return evaluation, results


def approve_evaluation(
    session: Session,
    evaluation_id: int,
    criterion_result_updates: dict[int, dict],
    actor: str = "teacher-local",
) -> Evaluation:
    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"Evaluation {evaluation_id} not found")

    results = session.exec(
        select(CriterionResult).where(CriterionResult.evaluation_id == evaluation_id)
    ).all()

    for result in results:
        update = criterion_result_updates.get(result.id, {})

        new_achieved = update.get("achieved", result.achieved)
        if new_achieved != result.achieved:
            result.achieved = new_achieved
            result.teacher_override = True

        final_feedback = update.get("teacher_final_feedback")
        if final_feedback is not None:
            result.teacher_final_feedback = final_feedback

        session.add(result)

    evaluation.status = "approved"
    session.add(evaluation)

    session.add(
        AuditLog(
            actor=actor,
            action="approve_evaluation",
            entity_type="Evaluation",
            entity_id=evaluation.id,
        )
    )

    session.commit()
    session.refresh(evaluation)
    return evaluation
