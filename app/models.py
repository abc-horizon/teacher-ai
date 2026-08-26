from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class Unit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    zoho_unit_id: str = Field(unique=True, index=True)
    name: str


class CriteriaSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    unit_id: int = Field(foreign_key="unit.id")
    taken_at: datetime = Field(default_factory=datetime.utcnow)


class Criterion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("snapshot_id", "code"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="criteriasnapshot.id")
    code: str
    descriptor: str


class AssignmentMap(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    moodle_assign_id: int = Field(unique=True, index=True)
    snapshot_id: int = Field(foreign_key="criteriasnapshot.id")


class Submission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    assignment_map_id: int = Field(foreign_key="assignmentmap.id")
    moodle_submission_id: int = Field(index=True)
    student_internal_id: str
    submitted_at: datetime
    moodle_userid: Optional[int] = None
    student_display_name: Optional[str] = None


class SubmissionFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="submission.id")
    contenthash: str
    filename: str
    extract_status: str
    extracted_text: Optional[str] = None


class Evaluation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="submission.id")
    prompt_version: str
    model_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str


class CriterionResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    evaluation_id: int = Field(foreign_key="evaluation.id")
    criterion_id: int = Field(foreign_key="criterion.id")
    achieved: bool
    evidence_quote: str
    feedback_draft: str
    confidence: float
    teacher_override: bool = Field(default=False)
    teacher_final_feedback: Optional[str] = None
    is_evidence_verified: Optional[bool] = Field(default=None)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: str
    action: str
    entity_type: str
    entity_id: int
    details: Optional[str] = None
