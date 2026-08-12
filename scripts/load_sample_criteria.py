import json
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import CriteriaSnapshot, Criterion, Unit

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def main():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    assessment_criteria = json.loads(
        (SAMPLE_DATA_DIR / "sustainable-energy-assessment-criteria.json").read_text(
            encoding="utf-8"
        )
    )

    # Context-only files: read as raw text/dict for later use as a prompt
    # context layer. They are never inserted into the database and must
    # never be treated as assessment criteria.
    assignment_guidance_text = (
        SAMPLE_DATA_DIR / "sustainable-energy-assignment-guidance.json"
    ).read_text(encoding="utf-8")
    command_verbs_text = (SAMPLE_DATA_DIR / "command-verbs.json").read_text(
        encoding="utf-8"
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

    print(f"Criteria inserted: {len(criteria)}")
    print("First 3 criteria:")
    for criterion in criteria[:3]:
        print(f"  {criterion.code}: {criterion.descriptor}")

    print(
        f"assignment-guidance.json read successfully "
        f"({len(assignment_guidance_text)} characters)"
    )
    print(
        f"command-verbs.json read successfully "
        f"({len(command_verbs_text)} characters)"
    )


if __name__ == "__main__":
    main()
