from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import (
    Assessment,
    Candidate,
    EmailMessage,
    ExamSession,
    ImportBatch,
    TestAssignment,
)
from ...models.base import now_utc
from ...services.audit import write_audit
from ...services.credentials import generate_username, make_credentials
from ...services.emailer import send_invitation
from ...services.importer import CSV_TEMPLATE, parse_rows, validate_row
from ..deps import AdminContext, require_roles

router = APIRouter(tags=["assignments"])


def _validate_phone(value: str) -> str:
    from ...services.importer import INDIAN_MOBILE_RE, normalize_phone

    cleaned = normalize_phone(value.strip())
    if cleaned and not INDIAN_MOBILE_RE.match(cleaned):
        raise ValueError("phone must be a 10-digit Indian mobile (starts 6-9, +91 optional)")
    return cleaned


class AssignmentIn(BaseModel):
    full_name: str
    email: EmailStr
    phone: str = ""
    window_start_at: datetime
    window_end_at: datetime
    send_email: bool = True

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v: str) -> str:
        return _validate_phone(v)


class AssignmentPatch(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    window_start_at: datetime | None = None
    window_end_at: datetime | None = None
    send_email: bool | None = None

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v: str | None) -> str | None:
        return None if v is None else _validate_phone(v)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


async def _get_assessment(db: AsyncSession, org_id: str, assessment_id: str) -> Assessment:
    assessment = (
        await db.execute(
            select(Assessment).where(
                Assessment.id == assessment_id, Assessment.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(404, "not_found")
    return assessment


async def _get_or_create_candidate(
    db: AsyncSession, org_id: str, full_name: str, email: str, phone: str
) -> Candidate:
    email = email.lower()
    candidate = (
        await db.execute(
            select(Candidate).where(Candidate.org_id == org_id, Candidate.email == email)
        )
    ).scalar_one_or_none()
    if candidate is None:
        candidate = Candidate(org_id=org_id, full_name=full_name, email=email, phone=phone)
        db.add(candidate)
        await db.flush()
    else:
        candidate.full_name = full_name or candidate.full_name
        candidate.phone = phone or candidate.phone
    return candidate


async def _create_assignment(
    db: AsyncSession,
    *,
    org_id: str,
    assessment: Assessment,
    candidate: Candidate,
    start_at: datetime,
    end_at: datetime,
    send_email: bool,
    batch_id: str | None = None,
) -> tuple[TestAssignment, str]:
    """Returns (assignment, plaintext_password). Raises 409 on duplicate (FR-013)."""
    duplicate = (
        await db.execute(
            select(TestAssignment).where(
                TestAssignment.assessment_id == assessment.id,
                TestAssignment.candidate_id == candidate.id,
                TestAssignment.status != "removed",
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(409, "duplicate_email_in_assessment")
    password, password_hash = make_credentials()
    assignment = TestAssignment(
        org_id=org_id,
        assessment_id=assessment.id,
        candidate_id=candidate.id,
        window_start_at=_naive(start_at),
        window_end_at=_naive(end_at),
        username=await generate_username(db, assessment.title),
        password_hash=password_hash,
        send_email=send_email,
        status="invited" if send_email else "not_started",
        import_batch_id=batch_id,
    )
    db.add(assignment)
    await db.flush()
    return assignment, password


def _assignment_out(assignment: TestAssignment, candidate: Candidate) -> dict:
    return {
        "id": assignment.id,
        "candidate": {
            "id": candidate.id,
            "full_name": candidate.full_name,
            "email": candidate.email,
            "phone": candidate.phone,
        },
        "window_start_at": assignment.window_start_at.isoformat(),
        "window_end_at": assignment.window_end_at.isoformat(),
        "status": assignment.status,
        "username": assignment.username,
        "credentials_expired": assignment.credentials_expired
        or assignment.window_end_at < now_utc(),
        "send_email": assignment.send_email,
    }


@router.get("/assessments/{assessment_id}/assignments")
async def list_assignments(
    assessment_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    ctx: AdminContext = Depends(require_roles("hr_admin", "evaluator", "test_creator")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await _get_assessment(db, ctx.org_id, assessment_id)
    base = (
        select(TestAssignment, Candidate)
        .join(Candidate, Candidate.id == TestAssignment.candidate_id)
        .where(
            TestAssignment.assessment_id == assessment.id,
            TestAssignment.status != "removed",
        )
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(TestAssignment.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return {
        "data": {
            "items": [_assignment_out(a, c) for a, c in rows],
            "total": total,
            "page": page,
            "size": size,
        },
        "error": None,
    }


@router.post("/assessments/{assessment_id}/assignments", status_code=201)
async def add_assignment(
    assessment_id: str,
    body: AssignmentIn,
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await _get_assessment(db, ctx.org_id, assessment_id)
    if _naive(body.window_end_at) <= _naive(body.window_start_at):
        raise HTTPException(422, {"code": "invalid_window", "details": ["end must be after start"]})
    candidate = await _get_or_create_candidate(
        db, ctx.org_id, body.full_name, body.email, body.phone
    )
    assignment, password = await _create_assignment(
        db,
        org_id=ctx.org_id,
        assessment=assessment,
        candidate=candidate,
        start_at=body.window_start_at,
        end_at=body.window_end_at,
        send_email=body.send_email,
    )
    if body.send_email:
        await send_invitation(
            db,
            org_id=ctx.org_id,
            assignment=assignment,
            candidate=candidate,
            assessment_title=assessment.title,
            password=password,
        )
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="assignment.created",
        entity_type="assignment",
        entity_id=assignment.id,
        after={"email": candidate.email, "window": [
            assignment.window_start_at.isoformat(), assignment.window_end_at.isoformat()
        ]},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    out = _assignment_out(assignment, candidate)
    out["initial_password"] = password  # one-time reveal (research R6)
    return {"data": out, "error": None}


@router.get("/import-batches/template", response_class=PlainTextResponse)
async def import_template(
    ctx: AdminContext = Depends(require_roles("hr_admin")),
):
    return CSV_TEMPLATE


@router.post("/assessments/{assessment_id}/assignments/import", status_code=202)
async def import_assignments(
    assessment_id: str,
    file: UploadFile = File(...),
    send_email: bool = Query(False),
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await _get_assessment(db, ctx.org_id, assessment_id)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(422, "file_too_large")
    batch = ImportBatch(
        assessment_id=assessment.id, uploaded_by=ctx.user.id, file_ref=file.filename or ""
    )
    db.add(batch)
    await db.flush()
    try:
        rows = parse_rows(file.filename or "upload.csv", content)
    except Exception:
        batch.status = "failed"
        batch.errors = [{"row": 0, "error": "could not parse file"}]
        await db.commit()
        return {"data": {"batch_id": batch.id, "status": "failed"}, "error": None}

    now = now_utc()
    errors: list[dict] = []
    imported = 0
    seen_emails: set[str] = set()
    for index, raw in enumerate(rows, start=2):  # header = row 1
        clean, error = validate_row(raw, now)
        if error:
            errors.append({"row": index, "error": error})
            continue
        if clean["email"] in seen_emails:
            errors.append({"row": index, "error": f"duplicate email in file: {clean['email']}"})
            continue
        seen_emails.add(clean["email"])
        candidate = await _get_or_create_candidate(
            db, ctx.org_id, clean["name"], clean["email"], clean["phone"]
        )
        try:
            assignment, password = await _create_assignment(
                db,
                org_id=ctx.org_id,
                assessment=assessment,
                candidate=candidate,
                start_at=clean["start_at"],
                end_at=clean["end_at"],
                send_email=send_email,
                batch_id=batch.id,
            )
        except HTTPException:
            errors.append(
                {"row": index, "error": f"duplicate email in this assessment: {clean['email']}"}
            )
            continue
        if send_email:
            await send_invitation(
                db,
                org_id=ctx.org_id,
                assignment=assignment,
                candidate=candidate,
                assessment_title=assessment.title,
                password=password,
            )
        imported += 1
    batch.total_rows = len(rows)
    batch.imported_rows = imported
    batch.failed_rows = len(errors)
    batch.errors = errors
    batch.status = "completed"
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="assignment.bulk_imported",
        entity_type="assessment",
        entity_id=assessment.id,
        after={"imported": imported, "failed": len(errors)},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {
        "data": {
            "batch_id": batch.id,
            "status": "completed",
            "total_rows": batch.total_rows,
            "imported_rows": imported,
            "failed_rows": len(errors),
        },
        "error": None,
    }


@router.get("/import-batches/{batch_id}")
async def get_batch(
    batch_id: str,
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    batch = (
        await db.execute(select(ImportBatch).where(ImportBatch.id == batch_id))
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(404, "not_found")
    assessment = await _get_assessment(db, ctx.org_id, batch.assessment_id)
    return {
        "data": {
            "id": batch.id,
            "assessment_id": assessment.id,
            "status": batch.status,
            "total_rows": batch.total_rows,
            "imported_rows": batch.imported_rows,
            "failed_rows": batch.failed_rows,
            "errors": batch.errors,
        },
        "error": None,
    }


async def _get_assignment(
    db: AsyncSession, org_id: str, assignment_id: str
) -> tuple[TestAssignment, Candidate, Assessment]:
    row = (
        await db.execute(
            select(TestAssignment, Candidate, Assessment)
            .join(Candidate, Candidate.id == TestAssignment.candidate_id)
            .join(Assessment, Assessment.id == TestAssignment.assessment_id)
            .where(TestAssignment.id == assignment_id, TestAssignment.org_id == org_id)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "not_found")
    return row


@router.patch("/assignments/{assignment_id}")
async def patch_assignment(
    assignment_id: str,
    body: AssignmentPatch,
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assignment, candidate, assessment = await _get_assignment(db, ctx.org_id, assignment_id)
    before = _assignment_out(assignment, candidate)
    if body.window_start_at is not None:
        assignment.window_start_at = _naive(body.window_start_at)
    if body.window_end_at is not None:
        assignment.window_end_at = _naive(body.window_end_at)
    if assignment.window_end_at <= assignment.window_start_at:
        raise HTTPException(422, {"code": "invalid_window", "details": ["end must be after start"]})
    if body.full_name is not None:
        candidate.full_name = body.full_name
    if body.phone is not None:
        candidate.phone = body.phone
    if body.send_email is not None:
        assignment.send_email = body.send_email
    if assignment.window_end_at > now_utc():
        assignment.credentials_expired = False  # reschedule revives credentials
        if assignment.status == "expired":
            assignment.status = "not_started"
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="assignment.timing_changed"
        if (body.window_start_at or body.window_end_at)
        else "assignment.updated",
        entity_type="assignment",
        entity_id=assignment.id,
        before=before,
        after=_assignment_out(assignment, candidate),
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": _assignment_out(assignment, candidate), "error": None}


@router.delete("/assignments/{assignment_id}")
async def remove_assignment(
    assignment_id: str,
    confirm: bool = Query(False),
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assignment, candidate, _ = await _get_assignment(db, ctx.org_id, assignment_id)
    if assignment.status == "in_progress" and not confirm:
        raise HTTPException(409, "confirm_required_in_progress")
    assignment.status = "removed"
    assignment.credentials_expired = True  # FR-017
    await db.execute(
        update(ExamSession)
        .where(ExamSession.assignment_id == assignment.id, ExamSession.status == "active")
        .values(status="terminated")
    )
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="assignment.removed",
        entity_type="assignment",
        entity_id=assignment.id,
        before={"email": candidate.email},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": {"removed": True}, "error": None}


@router.post("/assignments/{assignment_id}/resend-invitation")
async def resend_invitation(
    assignment_id: str,
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assignment, candidate, assessment = await _get_assignment(db, ctx.org_id, assignment_id)
    if assignment.status == "removed":
        raise HTTPException(409, "assignment_removed")
    # regenerate password so the resent mail contains working credentials
    password, password_hash = make_credentials()
    assignment.password_hash = password_hash
    await send_invitation(
        db,
        org_id=ctx.org_id,
        assignment=assignment,
        candidate=candidate,
        assessment_title=assessment.title,
        password=password,
        kind="resend",
    )
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="invitation.resent",
        entity_type="assignment",
        entity_id=assignment.id,
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": {"sent": True}, "error": None}


class RecoverySessionIn(BaseModel):
    window_start_at: datetime | None = None
    window_end_at: datetime | None = None


@router.post("/assignments/{assignment_id}/sessions", status_code=201)
async def create_recovery_session(
    assignment_id: str,
    body: RecoverySessionIn,
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    """FR-024: admin creates a fresh session after a technical problem, optionally
    adjusting the candidate's window. The previous active session is terminated."""
    assignment, candidate, assessment = await _get_assignment(db, ctx.org_id, assignment_id)
    if body.window_start_at is not None:
        assignment.window_start_at = _naive(body.window_start_at)
    if body.window_end_at is not None:
        assignment.window_end_at = _naive(body.window_end_at)
    if assignment.window_end_at <= assignment.window_start_at:
        raise HTTPException(422, {"code": "invalid_window", "details": ["end must be after start"]})
    assignment.credentials_expired = False
    terminated = (
        await db.execute(
            update(ExamSession)
            .where(
                ExamSession.assignment_id == assignment.id,
                ExamSession.status == "active",
            )
            .values(status="terminated")
        )
    ).rowcount
    if assignment.status in ("completed", "expired", "in_progress"):
        assignment.status = "not_started"
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="session.reset",
        entity_type="assignment",
        entity_id=assignment.id,
        after={
            "terminated_sessions": terminated,
            "window": [
                assignment.window_start_at.isoformat(),
                assignment.window_end_at.isoformat(),
            ],
        },
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {
        "data": {
            "assignment_id": assignment.id,
            "terminated_sessions": terminated,
            "window_start_at": assignment.window_start_at.isoformat(),
            "window_end_at": assignment.window_end_at.isoformat(),
        },
        "error": None,
    }


@router.get("/assignments/{assignment_id}/emails")
async def assignment_emails(
    assignment_id: str,
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    await _get_assignment(db, ctx.org_id, assignment_id)
    rows = (
        (
            await db.execute(
                select(EmailMessage)
                .where(EmailMessage.assignment_id == assignment_id)
                .order_by(EmailMessage.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "data": {
            "items": [
                {
                    "id": m.id,
                    "kind": m.kind,
                    "status": m.status,
                    "to_email": m.to_email,
                    "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                    "created_at": m.created_at.isoformat(),
                }
                for m in rows
            ]
        },
        "error": None,
    }
