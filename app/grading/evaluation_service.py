import json
import logging
import re

from sqlmodel import Session, select

from app.grading.llm_client import evaluate as llm_evaluate
from app.grading.prompt_builder import build_prompt, prepare_submission_text
from app.grading.schemas import EvaluationResponse, validate_full_coverage
from app.models import AuditLog, Criterion, CriterionResult, Evaluation

logger = logging.getLogger(__name__)


def _normalize_for_comparison(text: str) -> str:
    """Collapses whitespace runs and unifies quote/dash variants before
    checking evidence_quote against submission text — docx extraction often
    introduces spacing/typographic differences that are not real mismatches.
    """
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    return re.sub(r"\s+", " ", text).strip()


def evaluate_submission(
    session: Session,
    submission_id: int,
    criteria: list[Criterion],
    submission_text: str,
    model_id: str = "deepseek-chat",
    prompt_version: str = "v1",
) -> tuple[Evaluation, list[CriterionResult], bool]:
    """Returns (evaluation, results, was_truncated)."""
    prompt, was_truncated = build_prompt(criteria, submission_text)
    # Must match exactly what build_prompt sent to the model (pseudonymized
    # and, if applicable, truncated) — comparing against the raw original
    # would falsely fail on any real [NAME]/[EMAIL]/[PHONE] quote, and would
    # falsely pass on a quote from text the model never actually saw.
    prepared_text, _ = prepare_submission_text(submission_text)
    raw_response, usage = llm_evaluate(prompt)
    validated = EvaluationResponse.model_validate_json(json.dumps(raw_response))
    validate_full_coverage(validated, [criterion.code for criterion in criteria])

    criteria_by_code = {criterion.code: criterion for criterion in criteria}

    evaluation = Evaluation(
        submission_id=submission_id,
        prompt_version=prompt_version,
        model_id=model_id,
        status="draft",
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)

    results = []
    for judgment in validated.criteria_results:
        criterion = criteria_by_code[judgment.criterion_code]
        is_evidence_verified = _normalize_for_comparison(
            judgment.evidence_quote
        ) in _normalize_for_comparison(prepared_text)
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

    return evaluation, results, was_truncated


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
