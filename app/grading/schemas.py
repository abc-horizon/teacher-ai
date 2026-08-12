from pydantic import BaseModel, field_validator


class CriterionJudgment(BaseModel):
    criterion_code: str
    achieved: bool
    evidence_quote: str
    feedback_draft: str
    confidence: float

    @field_validator("evidence_quote")
    @classmethod
    def evidence_quote_must_be_meaningful(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("evidence_quote must be at least 3 characters long")
        return value

    @field_validator("feedback_draft")
    @classmethod
    def feedback_draft_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("feedback_draft must not be empty")
        return value

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_in_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0 inclusive")
        return value


class EvaluationResponse(BaseModel):
    criteria_results: list[CriterionJudgment]

    @field_validator("criteria_results")
    @classmethod
    def criteria_results_must_not_be_empty(
        cls, value: list[CriterionJudgment]
    ) -> list[CriterionJudgment]:
        if len(value) < 1:
            raise ValueError("criteria_results must contain at least one item")
        return value
