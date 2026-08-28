"""T1.3/T1.4: import real Moodle course/assignment/submission data into the
local project database, and extract text from any pending submission file.

Read-only against Moodle end to end for `sync_course` — only calls
core_course_get_courses / mod_assign_get_assignments /
core_course_get_contents (fallback discovery only) / mod_assign_get_submissions
/ core_enrol_get_enrolled_users. No write wsfunction is ever called.
`extract_pending_files` calls no wsfunction at all (file download is a plain
file GET, not a Web Service call).

Idempotent: re-running `sync_course` with the same courseid never creates
duplicate Unit/AssignmentMap/Submission rows — each is looked up by its
Moodle id before insert.

Terminal-output rule for callers: never print MOODLE_TOKEN, a student name,
an email, a raw userid, or extracted submission text. Student names ARE
stored in Submission.student_display_name for the portal to show a teacher —
that is a database write, not a print.

This module holds the logic shared by scripts/import_moodle_data.py,
scripts/extract_submission_files.py, and the portal pages — it is the
canonical place for Moodle-sync orchestration, kept separate from the raw
Moodle Web Services calls in app/extractor/sync.py.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, select

from app.db import get_engine
from app.extractor import moodle_db
from app.extractor.file_fetcher import FileFetchError, download_file, extract_text
from app.extractor.moodle_client import MoodleCallError, default_client, lms_client
from app.extractor.moodle_db import MoodleDBError
from app.extractor.sync import (
    fetch_assignments,
    fetch_courses,
    fetch_grading_definition,
    fetch_submissions,
    fetch_user_names,
)
from app.models import AssignmentMap, CriteriaSnapshot, Criterion, Submission, SubmissionFile, Unit

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "sample_data"


def course_key(courseid: int, client) -> str:
    """A Moodle courseid is only unique WITHIN one Moodle site — two
    separate instances (elearning.abchorizon.com and lms.abchorizon.com)
    can and do reuse the same id for unrelated courses (confirmed live:
    courseid=526 is "Research Methods and Investigating Psychology" on
    elearning, but "EnergyEvAi" on lms). Stored as Unit.zoho_unit_id, so it
    must be namespaced per site to avoid two unrelated courses colliding
    into the same Unit row. elearning keeps the old bare numeric form
    (str(courseid)) for backward compatibility with already-synced data.
    """
    if client is lms_client:
        return f"lms:{courseid}"
    return str(courseid)


def client_and_courseid_for_key(zoho_unit_id: str):
    """Reverses course_key(): given a stored Unit.zoho_unit_id, returns
    (client, courseid) so callers know which Moodle site + numeric id to
    use — Unit.zoho_unit_id is namespaced (see course_key()), so it is no
    longer safe to just int() it directly, as older code did.
    """
    if zoho_unit_id.startswith("lms:"):
        return lms_client, int(zoho_unit_id.split(":", 1)[1])
    return default_client, int(zoho_unit_id)


# Real BTEC criteria text (P/M/D) is not obtainable from any Moodle Web
# Service API — only via direct SQL access to Moodle's gradingform_btec_*
# tables (app/extractor/moodle_db.py) or a future Zoho integration. These
# JSON fixtures are the FALLBACK for when SQL access is not configured:
# resolve_criteria() prefers the live database whenever it is reachable.
#
# A fixture is a hand-maintained transcription, so it can silently drift out
# of date if a teacher edits the criteria in Moodle — which is exactly why
# SQL is preferred rather than merely offered. Until a course appears either
# here or in a reachable database, sync_course() must refuse to grade it
# rather than silently reusing another subject's criteria.
# Keyed by course_key() (namespaced — see above), not a bare courseid.
CRITERIA_FILE_BY_COURSE_KEY = {
    "373": "sustainable-energy-assessment-criteria.json",  # elearning.abchorizon.com: 2526T2 L3 U28 Sustainable Energy
    "lms:526": "sustainable-energy-assessment-criteria.json",  # lms.abchorizon.com: EnergyEvAi (safe test course, same subject)
}


def may_have_criteria(courseid: int, client=None) -> bool:
    """Cheap, no-I/O guess at whether a course's criteria are obtainable.

    Exists for the course-search list in portal/pages/1_Units.py, which
    renders up to 30 courses at once: actually resolving criteria costs an
    assignment discovery, a definition lookup and a SQL query PER COURSE, so
    calling resolve_criteria() there would make the page unusable.

    Deliberately optimistic when SQL is configured — it cannot know whether
    a given course has a btec definition without paying that cost, so it
    says "maybe" and lets sync_course() give the definitive answer on click
    (which already reports criteria_available=False gracefully). The cost of
    guessing wrong is one wasted click, versus hiding a course that is
    genuinely gradeable.
    """
    client = client or default_client
    if course_key(courseid, client) in CRITERIA_FILE_BY_COURSE_KEY:
        return True
    return moodle_db.is_configured()


def resolve_criteria(courseid: int, client=None) -> tuple[list[dict], str]:
    """The best available BTEC criteria for a course, and where they came from.

    Returns (criteria, source) where source is one of:
      "moodle_sql:def=<id>" — live from Moodle's own tables (authoritative)
      "fixture:<filename>"  — hand-maintained JSON transcription
      "none"                — nothing available; caller must refuse to grade

    Both shapes carry the same keys (criterion_code / criterion_text / level),
    so the caller needs no branch on source.

    SQL is tried first and per-assignment, because a BTEC definition belongs
    to an assignment (cmid), not to a course. The first assignment with a
    ready 'btec' definition and non-empty criteria wins — a course normally
    has exactly one such assignment.

    A configured-but-unreachable database falls through to the fixture
    rather than raising: a broken SSH tunnel should degrade the data source,
    not break the whole sync.
    """
    client = client or default_client
    key = course_key(courseid, client)

    if moodle_db.is_configured():
        try:
            for assignment in discover_assignments(courseid, client=client):
                cmid = assignment.get("cmid")
                if cmid is None:
                    continue
                definition = fetch_grading_definition(cmid, client=client)
                if definition is None or not definition["is_ready"]:
                    continue
                criteria = moodle_db.fetch_criteria(definition["definition_id"])
                if criteria:
                    return criteria, f"moodle_sql:def={definition['definition_id']}"
        except (MoodleDBError, MoodleCallError):
            # Fall through to the fixture. Deliberately broad on the DB side:
            # a wrong prefix, a missing GRANT and a dead tunnel all mean the
            # same thing here — the live source is unusable right now.
            pass

    criteria_filename = CRITERIA_FILE_BY_COURSE_KEY.get(key)
    if criteria_filename is not None:
        payload = json.loads(
            (SAMPLE_DATA_DIR / criteria_filename).read_text(encoding="utf-8")
        )
        return payload["criteria"], f"fixture:{criteria_filename}"

    return [], "none"

# Only these statuses mean the student actually interacted with the
# assignment. "new" is Moodle's placeholder row for an enrolled student who
# never submitted anything — importing those would clutter the portal with
# empty "submissions" that have no content and no files.
SUBMITTED_STATUSES = {"submitted", "reopened"}


def discover_assignments(courseid: int, client=None) -> list[dict]:
    """mod_assign_get_assignments is scoped to courses the token's account is
    enrolled in, and can return nothing for a course that is otherwise
    visible via core_course_get_courses (observed empirically on this exact
    token/site). Fall back to core_course_get_contents, which is not scoped
    the same way, to discover assign module instances directly.
    """
    client = client or default_client
    try:
        assignments = fetch_assignments([courseid], client=client)
    except MoodleCallError:
        assignments = []
    if assignments:
        return assignments

    try:
        contents = client.call("core_course_get_contents", courseid=courseid)
    except MoodleCallError:
        return []

    discovered = []
    for section in contents:
        for module in section.get("modules", []):
            if module.get("modname") == "assign":
                discovered.append(
                    {
                        "id": module.get("instance"),
                        "cmid": module.get("id"),
                        "course": courseid,
                        "duedate": None,
                    }
                )
    return discovered


def file_contenthash(file_info: dict) -> str:
    """No real content hash is available from mod_assign_get_submissions
    (only filename/fileurl/filesize) since we do not download file content
    in this phase. Derive a stable identifier from fileurl instead.
    """
    basis = file_info.get("fileurl") or file_info.get("filename") or ""
    if not basis:
        return "unknown"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def get_or_create_unit(
    session: Session, courseid: int, course: dict, client=None
) -> tuple[Unit, bool]:
    client = client or default_client
    zoho_unit_id = course_key(courseid, client)
    unit = session.exec(select(Unit).where(Unit.zoho_unit_id == zoho_unit_id)).first()
    if unit:
        return unit, False
    unit = Unit(
        zoho_unit_id=zoho_unit_id,
        name=course.get("fullname") or course.get("shortname") or zoho_unit_id,
    )
    session.add(unit)
    session.commit()
    session.refresh(unit)
    return unit, True


def get_or_create_snapshot(
    session: Session, unit: Unit, courseid: int, client=None
) -> tuple[CriteriaSnapshot | None, bool, str]:
    """Returns (snapshot, was_created, source).

    (None, False, "none") means no criteria could be found for this course
    from any source — callers must not fall back to a different course's
    criteria, so they must refuse to grade it.

    `source` is resolve_criteria()'s provenance string. It matters
    operationally: an evaluation built on "fixture:..." rests on a
    hand-maintained transcription that may have drifted from what the
    teacher actually configured in Moodle, whereas "moodle_sql:def=..." is
    read from Moodle's own tables. Callers surface it so nobody has to guess
    which one a given grading run used.

    An EXISTING snapshot is returned as-is with source "existing" — its
    criteria are intentionally frozen (see the snapshot principle in
    docs/TECHNICAL_DOCUMENTATION.md): past evaluations must stay
    interpretable against the exact criteria text they were graded on, so
    reaching a live database must never retroactively rewrite them.
    """
    client = client or default_client
    snapshot = session.exec(
        select(CriteriaSnapshot).where(CriteriaSnapshot.unit_id == unit.id)
    ).first()
    if snapshot:
        return snapshot, False, "existing"

    criteria, source = resolve_criteria(courseid, client=client)
    if not criteria:
        return None, False, source

    snapshot = CriteriaSnapshot(unit_id=unit.id)
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)

    for item in criteria:
        session.add(
            Criterion(
                snapshot_id=snapshot.id,
                code=item["criterion_code"],
                descriptor=item["criterion_text"],
            )
        )
    session.commit()
    return snapshot, True, source


def get_or_create_assignment_map(
    session: Session, moodle_assign_id: int, snapshot: CriteriaSnapshot
) -> tuple[AssignmentMap, bool]:
    """NOTE (known, currently non-manifesting limitation): unlike
    Unit.zoho_unit_id (see course_key()), moodle_assign_id is a plain int
    with a single-site uniqueness constraint — it is not namespaced per
    Moodle instance. Two different sites could theoretically reuse the same
    assignment instance id for unrelated assignments. Not fixed here because
    it would need a schema migration and does not currently occur (checked:
    elearning's synced ids are 333+, lms's test ids are 77-79 — no overlap).
    Revisit with a composite (site, moodle_assign_id) key if it ever does.
    """
    assignment_map = session.exec(
        select(AssignmentMap).where(AssignmentMap.moodle_assign_id == moodle_assign_id)
    ).first()
    if assignment_map:
        return assignment_map, False
    assignment_map = AssignmentMap(
        moodle_assign_id=moodle_assign_id, snapshot_id=snapshot.id
    )
    session.add(assignment_map)
    session.commit()
    session.refresh(assignment_map)
    return assignment_map, True


def sync_course(courseid: int, client=None) -> dict:
    """Fetches this Moodle course's real assignments/submissions and
    upserts Unit/AssignmentMap/Submission/SubmissionFile rows in the local
    database. Safe to call repeatedly (idempotent). Returns counters.

    client defaults to the elearning.abchorizon.com instance
    (default_client) — pass app.extractor.moodle_client.lms_client
    explicitly to sync a course from lms.abchorizon.com instead.
    """
    client = client or default_client
    engine = get_engine()
    SQLModel.metadata.create_all(engine)

    counters = {
        "unit_created": 0,
        "unit_existing": 0,
        "criteria_available": True,
        # Provenance of the criteria this sync used — "moodle_sql:def=<id>",
        # "fixture:<file>", "existing" or "none". Surfaced so a grading run
        # is never silently based on a stale hand-written transcription.
        "criteria_source": "none",
        "criteria_created": 0,
        "assignments_created": 0,
        "assignments_existing": 0,
        "submissions_created": 0,
        "submissions_existing": 0,
        "submissions_skipped_not_submitted": 0,
        "files_created": 0,
        "files_backfilled": 0,
    }

    courses = fetch_courses(client=client)
    course = next((c for c in courses if c["id"] == courseid), None)
    if course is None:
        raise MoodleCallError(f"لم يُعثر على مادة بمعرّف courseid={courseid} بين المواد المتاحة.")

    with Session(engine) as session:
        unit, was_created = get_or_create_unit(session, courseid, course, client=client)
        counters["unit_created" if was_created else "unit_existing"] += 1

        snapshot, snapshot_created, criteria_source = get_or_create_snapshot(
            session, unit, courseid, client=client
        )
        counters["criteria_source"] = criteria_source
        if snapshot is None:
            # No criteria for this course from the database OR a fixture (see
            # resolve_criteria) — stop here rather than mapping assignments
            # to no snapshot or to the wrong one.
            counters["criteria_available"] = False
            return counters

        if snapshot_created:
            criteria_count = len(
                session.exec(
                    select(Criterion).where(Criterion.snapshot_id == snapshot.id)
                ).all()
            )
            counters["criteria_created"] = criteria_count

        assignments = discover_assignments(courseid, client=client)

        for assignment in assignments:
            moodle_assign_id = assignment.get("id")
            if moodle_assign_id is None:
                continue

            assignment_map, assign_created = get_or_create_assignment_map(
                session, moodle_assign_id, snapshot
            )
            counters["assignments_created" if assign_created else "assignments_existing"] += 1

            try:
                submissions = fetch_submissions([moodle_assign_id], client=client)
            except MoodleCallError:
                continue

            real_submissions = [
                s for s in submissions if s.get("status") in SUBMITTED_STATUSES
            ]
            counters["submissions_skipped_not_submitted"] += len(submissions) - len(
                real_submissions
            )

            user_ids = sorted(
                {s["userid"] for s in real_submissions if s.get("userid") is not None}
            )
            try:
                names = fetch_user_names(courseid, user_ids, client=client) if user_ids else {}
            except MoodleCallError:
                names = {}
            anon = {uid: f"S-{i + 1:03d}" for i, uid in enumerate(user_ids)}

            for sub in real_submissions:
                userid = sub.get("userid")
                if userid is None:
                    continue

                existing = session.exec(
                    select(Submission).where(
                        Submission.moodle_submission_id == sub["id"]
                    )
                ).first()
                if existing:
                    counters["submissions_existing"] += 1
                    # Backfill fileurl on files imported before that column
                    # existed (older SubmissionFile rows have fileurl=None).
                    for file_info in sub.get("files", []):
                        filename = file_info.get("filename") or "unknown"
                        matching_file = session.exec(
                            select(SubmissionFile).where(
                                SubmissionFile.submission_id == existing.id,
                                SubmissionFile.filename == filename,
                            )
                        ).first()
                        if (
                            matching_file
                            and matching_file.fileurl is None
                            and file_info.get("fileurl")
                        ):
                            matching_file.fileurl = file_info["fileurl"]
                            session.add(matching_file)
                            counters["files_backfilled"] += 1
                    session.commit()
                    continue

                submitted_at = (
                    datetime.utcfromtimestamp(sub["timemodified"])
                    if sub.get("timemodified")
                    else datetime.utcnow()
                )

                new_submission = Submission(
                    assignment_map_id=assignment_map.id,
                    moodle_submission_id=sub["id"],
                    student_internal_id=anon.get(userid, f"S-{userid}"),
                    submitted_at=submitted_at,
                    moodle_userid=userid,
                    student_display_name=names.get(userid),
                )
                session.add(new_submission)
                session.commit()
                session.refresh(new_submission)
                counters["submissions_created"] += 1

                for file_info in sub.get("files", []):
                    session.add(
                        SubmissionFile(
                            submission_id=new_submission.id,
                            contenthash=file_contenthash(file_info),
                            filename=file_info.get("filename") or "unknown",
                            extract_status="pending",
                            fileurl=file_info.get("fileurl"),
                        )
                    )
                    counters["files_created"] += 1
                if sub.get("files"):
                    session.commit()

    return counters


def extract_pending_files(token: str = None, assignment_map_id: int = None) -> tuple[dict, dict]:
    """Downloads every matching SubmissionFile row with
    extract_status="pending" and extracts its text. Returns (counters,
    failure_reasons_by_type).

    token defaults to the elearning MOODLE_TOKEN — pass
    app.extractor.moodle_client.LMS_MOODLE_TOKEN when the pending files were
    synced from lms.abchorizon.com, since a fileurl only serves content to a
    token from its own site.

    assignment_map_id, if given, scopes the query to that one assignment's
    submissions only. Pass it whenever mixing sources (e.g. right after a
    lms_client sync) — the default (None) processes every pending file
    project-wide with one token, which is only correct when every pending
    file actually belongs to the same Moodle site.
    """
    engine = get_engine()
    counters = {"success": 0, "failed": 0}
    failure_reasons = {}

    with Session(engine) as session:
        query = select(SubmissionFile).where(SubmissionFile.extract_status == "pending")
        if assignment_map_id is not None:
            query = query.join(Submission).where(
                Submission.assignment_map_id == assignment_map_id
            )
        pending = session.exec(query).all()

        for submission_file in pending:
            try:
                if not submission_file.fileurl:
                    raise FileFetchError("no fileurl stored for this file")

                file_bytes = download_file(submission_file.fileurl, token=token)
                text = extract_text(file_bytes, submission_file.filename)

                submission_file.extracted_text = text
                submission_file.extract_status = "success"
                counters["success"] += 1

            except Exception as exc:
                reason = type(exc).__name__
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                submission_file.extract_status = "extract_failed"
                counters["failed"] += 1

            session.add(submission_file)
            session.commit()

    return counters, failure_reasons
