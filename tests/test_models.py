from datetime import datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

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


@pytest.fixture()
def engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_all_tables_create_without_error(engine):
    table_names = set(SQLModel.metadata.tables.keys())
    assert table_names == {
        "unit",
        "criteriasnapshot",
        "criterion",
        "assignmentmap",
        "submission",
        "submissionfile",
        "evaluation",
        "criterionresult",
        "auditlog",
    }


def test_unit_insert_and_read(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-1", name="Unit 1")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        fetched = session.exec(select(Unit).where(Unit.zoho_unit_id == "ZU-1")).one()
        assert fetched.id == unit.id
        assert fetched.name == "Unit 1"


def test_criteria_snapshot_insert_and_read(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-2", name="Unit 2")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        fetched = session.exec(
            select(CriteriaSnapshot).where(CriteriaSnapshot.id == snapshot.id)
        ).one()
        assert fetched.unit_id == unit.id
        assert isinstance(fetched.taken_at, datetime)


def test_criterion_insert_and_read(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-3", name="Unit 3")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        criterion = Criterion(
            snapshot_id=snapshot.id, code="P1", descriptor="Describe the basics"
        )
        session.add(criterion)
        session.commit()
        session.refresh(criterion)

        fetched = session.exec(
            select(Criterion).where(Criterion.id == criterion.id)
        ).one()
        assert fetched.code == "P1"
        assert fetched.snapshot_id == snapshot.id


def test_criterion_duplicate_code_in_same_snapshot_rejected(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-3b", name="Unit 3b")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        session.add(Criterion(snapshot_id=snapshot.id, code="P1", descriptor="First"))
        session.commit()

        session.add(
            Criterion(snapshot_id=snapshot.id, code="P1", descriptor="Duplicate")
        )
        with pytest.raises(Exception):
            session.commit()


def test_assignment_map_insert_and_read(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-4", name="Unit 4")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        assignment_map = AssignmentMap(moodle_assign_id=101, snapshot_id=snapshot.id)
        session.add(assignment_map)
        session.commit()
        session.refresh(assignment_map)

        fetched = session.exec(
            select(AssignmentMap).where(AssignmentMap.moodle_assign_id == 101)
        ).one()
        assert fetched.snapshot_id == snapshot.id


def test_submission_insert_and_read(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-5", name="Unit 5")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        assignment_map = AssignmentMap(moodle_assign_id=102, snapshot_id=snapshot.id)
        session.add(assignment_map)
        session.commit()
        session.refresh(assignment_map)

        submission = Submission(
            assignment_map_id=assignment_map.id,
            moodle_submission_id=201,
            student_internal_id="S-1042",
            submitted_at=datetime.utcnow(),
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)

        fetched = session.exec(
            select(Submission).where(Submission.id == submission.id)
        ).one()
        assert fetched.student_internal_id == "S-1042"
        assert fetched.assignment_map_id == assignment_map.id


def test_submission_file_insert_and_read(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-6", name="Unit 6")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        assignment_map = AssignmentMap(moodle_assign_id=103, snapshot_id=snapshot.id)
        session.add(assignment_map)
        session.commit()
        session.refresh(assignment_map)

        submission = Submission(
            assignment_map_id=assignment_map.id,
            moodle_submission_id=202,
            student_internal_id="S-1043",
            submitted_at=datetime.utcnow(),
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)

        submission_file = SubmissionFile(
            submission_id=submission.id,
            contenthash="abc123",
            filename="essay.docx",
            extract_status="pending",
            extracted_text=None,
        )
        session.add(submission_file)
        session.commit()
        session.refresh(submission_file)

        fetched = session.exec(
            select(SubmissionFile).where(SubmissionFile.id == submission_file.id)
        ).one()
        assert fetched.filename == "essay.docx"
        assert fetched.extract_status == "pending"
        assert fetched.extracted_text is None


def test_evaluation_insert_and_read(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-7", name="Unit 7")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        assignment_map = AssignmentMap(moodle_assign_id=104, snapshot_id=snapshot.id)
        session.add(assignment_map)
        session.commit()
        session.refresh(assignment_map)

        submission = Submission(
            assignment_map_id=assignment_map.id,
            moodle_submission_id=203,
            student_internal_id="S-1044",
            submitted_at=datetime.utcnow(),
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)

        evaluation = Evaluation(
            submission_id=submission.id,
            prompt_version="v1",
            model_id="gpt-test",
            status="draft",
        )
        session.add(evaluation)
        session.commit()
        session.refresh(evaluation)

        fetched = session.exec(
            select(Evaluation).where(Evaluation.id == evaluation.id)
        ).one()
        assert fetched.status == "draft"
        assert fetched.submission_id == submission.id


def test_criterion_result_insert_and_read(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-8", name="Unit 8")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        criterion = Criterion(
            snapshot_id=snapshot.id, code="M2", descriptor="Analyse in depth"
        )
        session.add(criterion)
        session.commit()
        session.refresh(criterion)

        assignment_map = AssignmentMap(moodle_assign_id=105, snapshot_id=snapshot.id)
        session.add(assignment_map)
        session.commit()
        session.refresh(assignment_map)

        submission = Submission(
            assignment_map_id=assignment_map.id,
            moodle_submission_id=204,
            student_internal_id="S-1045",
            submitted_at=datetime.utcnow(),
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)

        evaluation = Evaluation(
            submission_id=submission.id,
            prompt_version="v1",
            model_id="gpt-test",
            status="draft",
        )
        session.add(evaluation)
        session.commit()
        session.refresh(evaluation)

        criterion_result = CriterionResult(
            evaluation_id=evaluation.id,
            criterion_id=criterion.id,
            achieved=True,
            evidence_quote="See paragraph 2",
            feedback_draft="Good analysis",
            confidence=0.87,
        )
        session.add(criterion_result)
        session.commit()
        session.refresh(criterion_result)

        fetched = session.exec(
            select(CriterionResult).where(CriterionResult.id == criterion_result.id)
        ).one()
        assert fetched.achieved is True
        assert fetched.teacher_override is False
        assert fetched.teacher_final_feedback is None
        assert 0 <= fetched.confidence <= 1


def test_audit_log_insert_and_read(engine):
    with Session(engine) as session:
        audit_log = AuditLog(
            actor="teacher-1",
            action="approve_evaluation",
            entity_type="Evaluation",
            entity_id=1,
        )
        session.add(audit_log)
        session.commit()
        session.refresh(audit_log)

        fetched = session.exec(
            select(AuditLog).where(AuditLog.id == audit_log.id)
        ).one()
        assert fetched.action == "approve_evaluation"
        assert fetched.details is None
        assert isinstance(fetched.timestamp, datetime)


def test_snapshot_immutability(engine):
    with Session(engine) as session:
        unit = Unit(zoho_unit_id="ZU-9", name="Unit 9")
        session.add(unit)
        session.commit()
        session.refresh(unit)

        snapshot_1 = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot_1)
        session.commit()
        session.refresh(snapshot_1)

        criterion_1 = Criterion(
            snapshot_id=snapshot_1.id, code="P1", descriptor="Original descriptor"
        )
        session.add(criterion_1)
        session.commit()
        session.refresh(criterion_1)

        assignment_map = AssignmentMap(
            moodle_assign_id=999, snapshot_id=snapshot_1.id
        )
        session.add(assignment_map)
        session.commit()
        session.refresh(assignment_map)

        # A later snapshot of the same unit with a different criterion
        # must not affect the assignment already mapped to snapshot_1.
        snapshot_2 = CriteriaSnapshot(unit_id=unit.id)
        session.add(snapshot_2)
        session.commit()
        session.refresh(snapshot_2)

        criterion_2 = Criterion(
            snapshot_id=snapshot_2.id, code="P1", descriptor="Updated descriptor"
        )
        session.add(criterion_2)
        session.commit()
        session.refresh(criterion_2)

        session.refresh(assignment_map)
        assert assignment_map.snapshot_id == snapshot_1.id

        original_criterion = session.exec(
            select(Criterion).where(
                Criterion.snapshot_id == assignment_map.snapshot_id,
                Criterion.code == "P1",
            )
        ).one()
        assert original_criterion.id == criterion_1.id
        assert original_criterion.descriptor == "Original descriptor"
