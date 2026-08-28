import json
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.grading.llm_client import evaluate
from app.grading.prompt_builder import build_prompt
from app.grading.schemas import EvaluationResponse
from app.models import CriteriaSnapshot, Criterion, Unit

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"

SUBMISSION_TEXT = (
    "Coal, oil and natural gas are fossil fuels. Coal is extracted by mining. "
    "Oil and gas are extracted by drilling. These fuels are used for power "
    "generation and transport."
)

SELECTED_CODES = ["P1", "P2", "M1"]


def main():
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
            select(Criterion)
            .where(Criterion.snapshot_id == snapshot.id)
            .order_by(Criterion.id)
        ).all()

    selected_criteria = [c for c in criteria if c.code in SELECTED_CODES]

    prompt, _was_truncated = build_prompt(selected_criteria, SUBMISSION_TEXT)
    raw_response, usage = evaluate(prompt)
    evaluation = EvaluationResponse.model_validate_json(json.dumps(raw_response))
    print(f"usage: {usage}")

    for result in evaluation.criteria_results:
        print(f"{result.criterion_code}: achieved={result.achieved}")
        print(f"  evidence_quote: {result.evidence_quote}")
        print(f"  feedback_draft: {result.feedback_draft}")
        print(f"  confidence: {result.confidence}")


if __name__ == "__main__":
    main()
