import json

import pytest
from pydantic import ValidationError

from app.grading.schemas import (
    CriterionJudgment,
    EvaluationResponse,
    validate_full_coverage,
)

VALID_JUDGMENT = {
    "criterion_code": "P1",
    "achieved": True,
    "evidence_quote": "See paragraph 2 for the full argument.",
    "feedback_draft": "Good use of evidence throughout.",
    "confidence": 0.85,
}


def make_response(*codes):
    return EvaluationResponse(
        criteria_results=[{**VALID_JUDGMENT, "criterion_code": code} for code in codes]
    )


def test_full_valid_evaluation_response():
    response = EvaluationResponse(criteria_results=[VALID_JUDGMENT])
    assert len(response.criteria_results) == 1
    assert response.criteria_results[0].criterion_code == "P1"
    assert response.criteria_results[0].confidence == 0.85


@pytest.mark.parametrize("confidence", [1.5, -0.2])
def test_confidence_out_of_range_rejected(confidence):
    judgment = {**VALID_JUDGMENT, "confidence": confidence}
    with pytest.raises(ValidationError):
        CriterionJudgment(**judgment)


def test_empty_evidence_quote_rejected():
    judgment = {**VALID_JUDGMENT, "evidence_quote": ""}
    with pytest.raises(ValidationError):
        CriterionJudgment(**judgment)


def test_short_evidence_quote_rejected():
    judgment = {**VALID_JUDGMENT, "evidence_quote": "ab"}
    with pytest.raises(ValidationError):
        CriterionJudgment(**judgment)


def test_empty_criteria_results_rejected():
    with pytest.raises(ValidationError):
        EvaluationResponse(criteria_results=[])


def test_valid_deepseek_style_json_parses_successfully():
    raw_json = json.dumps(
        {
            "criteria_results": [
                {
                    "criterion_code": "M2",
                    "achieved": True,
                    "evidence_quote": "The analysis in section 3 is thorough.",
                    "feedback_draft": "Strong analytical depth.",
                    "confidence": 0.92,
                }
            ]
        }
    )
    response = EvaluationResponse.model_validate_json(raw_json)
    assert response.criteria_results[0].criterion_code == "M2"


def test_invalid_json_missing_field_raises_validation_error():
    raw_json = json.dumps(
        {
            "criteria_results": [
                {
                    "criterion_code": "D1",
                    "achieved": True,
                    "evidence_quote": "Missing feedback_draft field here.",
                    "confidence": 0.7,
                }
            ]
        }
    )
    with pytest.raises(ValidationError):
        EvaluationResponse.model_validate_json(raw_json)


def test_validate_full_coverage_accepts_exact_match():
    response = make_response("P1", "P2", "M1")
    validate_full_coverage(response, ["P1", "P2", "M1"])


def test_validate_full_coverage_rejects_missing_criterion():
    response = make_response("P1", "P2")
    with pytest.raises(ValueError, match="Missing"):
        validate_full_coverage(response, ["P1", "P2", "M1"])


def test_validate_full_coverage_rejects_duplicate_criterion_code():
    response = make_response("P1", "P1", "M1")
    with pytest.raises(ValueError, match="Duplicate"):
        validate_full_coverage(response, ["P1", "M1", "D1"])


def test_validate_full_coverage_rejects_invented_criterion_code():
    response = make_response("P1", "M1", "Z9")
    with pytest.raises(ValueError, match="Unknown"):
        validate_full_coverage(response, ["P1", "M1"])
