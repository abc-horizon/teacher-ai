import json
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, select

from app.db import DB_PATH, get_engine
from app.models import (
    AssignmentMap,
    CriteriaSnapshot,
    Criterion,
    Submission,
    SubmissionFile,
    Unit,
)

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"

STUDENT_SUBMISSIONS = [
    {
        "student_internal_id": "S-1001",
        "submitted_at": datetime(2026, 6, 1, 9, 30),
        "extracted_text": (
            "Coal is a fossil fuel extracted by mining and used mainly for "
            "electricity generation in power stations."
        ),
    },
    {
        "student_internal_id": "S-1002",
        "submitted_at": datetime(2026, 6, 2, 14, 15),
        "extracted_text": (
            "Solar panels convert sunlight directly into electricity and are "
            "a renewable alternative to fossil fuels."
        ),
    },
    {
        "student_internal_id": "S-1003",
        "submitted_at": datetime(2026, 6, 3, 11, 0),
        "extracted_text": (
            "Nuclear power stations use uranium fuel rods to generate heat, "
            "which is then used to produce steam and drive turbines."
        ),
    },
]


def seed(engine):
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

        assignment_map = AssignmentMap(moodle_assign_id=9001, snapshot_id=snapshot.id)
        session.add(assignment_map)
        session.commit()
        session.refresh(assignment_map)

        for index, data in enumerate(STUDENT_SUBMISSIONS, start=1):
            submission = Submission(
                assignment_map_id=assignment_map.id,
                moodle_submission_id=5000 + index,
                student_internal_id=data["student_internal_id"],
                submitted_at=data["submitted_at"],
            )
            session.add(submission)
            session.commit()
            session.refresh(submission)

            session.add(
                SubmissionFile(
                    submission_id=submission.id,
                    contenthash=f"devseed-{index:03d}",
                    filename="assignment.docx",
                    extract_status="success",
                    extracted_text=data["extracted_text"],
                )
            )
        session.commit()

        criteria_count = len(
            session.exec(
                select(Criterion).where(Criterion.snapshot_id == snapshot.id)
            ).all()
        )
        submission_count = len(
            session.exec(
                select(Submission).where(
                    Submission.assignment_map_id == assignment_map.id
                )
            ).all()
        )

    return {"criteria_count": criteria_count, "submission_count": submission_count}


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()

    engine = get_engine()
    summary = seed(engine)

    print(f"Seeded database at {DB_PATH}")
    print(f"Criteria: {summary['criteria_count']}")
    print(f"Submissions: {summary['submission_count']}")


if __name__ == "__main__":
    main()
