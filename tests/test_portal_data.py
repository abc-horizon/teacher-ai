import re

from sqlmodel import Session, create_engine, select

from app.models import AssignmentMap, Criterion, Submission
from scripts.seed_dev_db import seed


def test_seed_creates_expected_data():
    engine = create_engine("sqlite://")
    seed(engine)

    with Session(engine) as session:
        criteria = session.exec(select(Criterion)).all()
        submissions = session.exec(select(Submission)).all()

    assert len(criteria) == 12
    assert len(submissions) == 3

    student_ids = {s.student_internal_id for s in submissions}
    assert student_ids == {"S-1001", "S-1002", "S-1003"}
    assert all(re.fullmatch(r"S-\d{4}", sid) for sid in student_ids)


def test_each_submission_linked_to_correct_assignment_map():
    engine = create_engine("sqlite://")
    seed(engine)

    with Session(engine) as session:
        assignment_maps = session.exec(select(AssignmentMap)).all()
        assert len(assignment_maps) == 1
        assignment_map = assignment_maps[0]

        submissions = session.exec(select(Submission)).all()
        assert len(submissions) == 3
        for submission in submissions:
            assert submission.assignment_map_id == assignment_map.id
