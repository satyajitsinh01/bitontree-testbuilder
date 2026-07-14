from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import Assessment, Candidate, TestAssignment
from ...models.base import now_utc
from ...security import create_access_token, verify_password
from ...services.sessions import get_active_session, is_session_live, window_state
from ...services.tokens import issue_refresh, rotate_refresh

router = APIRouter(prefix="/auth/candidate", tags=["candidate-auth"])

REFRESH_COOKIE = "tb_candidate_refresh"


class CandidateLoginIn(BaseModel):
    username: str
    password: str


async def find_assignment_by_email(
    db: AsyncSession, email: str, password: str
) -> TestAssignment | None:
    """Email + password login: the per-assignment password disambiguates when the
    same email is invited to several assessments (FR-014)."""
    candidates = (
        (
            await db.execute(
                select(Candidate).where(Candidate.email == email.strip().lower())
            )
        )
        .scalars()
        .all()
    )
    if not candidates:
        return None
    assignments = (
        (
            await db.execute(
                select(TestAssignment).where(
                    TestAssignment.candidate_id.in_([c.id for c in candidates]),
                    TestAssignment.status != "removed",
                )
            )
        )
        .scalars()
        .all()
    )
    matches = [a for a in assignments if verify_password(password, a.password_hash)]
    if not matches:
        return None
    now = now_utc()
    # prefer an open window, then the next upcoming one, then most recent
    open_now = [a for a in matches if a.window_start_at <= now < a.window_end_at]
    if open_now:
        return open_now[0]
    upcoming = sorted(
        (a for a in matches if a.window_start_at > now), key=lambda a: a.window_start_at
    )
    if upcoming:
        return upcoming[0]
    return sorted(matches, key=lambda a: a.window_end_at)[-1]


async def build_candidate_login_response(
    db: AsyncSession, assignment: TestAssignment, response: Response
) -> dict:
    """Shared gating + token issuance for both login shapes. Raises HTTPException
    with candidate-facing codes/messages when access must be denied."""
    if assignment.credentials_expired:
        raise HTTPException(401, "invalid_credentials")
    if assignment.status == "completed":
        # submitted assessments permanently invalidate the credentials
        assignment.credentials_expired = True
        await db.commit()
        raise HTTPException(
            403,
            {
                "code": "already_submitted",
                "message": "You have already submitted this assessment. "
                "Your credentials are no longer valid.",
            },
        )
    if assignment.window_end_at < now_utc():
        assignment.credentials_expired = True  # FR-017 lazy expiry
        await db.commit()
        raise HTTPException(
            403, {"code": "window_expired", "message": "Assessment window has expired."}
        )
    if window_state(assignment) == "not_started":
        raise HTTPException(
            403,
            {
                "code": "window_not_started",
                "message": "Your test will start soon.",
                "starts_at": assignment.window_start_at.isoformat(),
                "server_now": now_utc().isoformat(),
            },
        )
    active = await get_active_session(db, assignment.id)
    if active is not None and is_session_live(active):
        # FR-023: exactly one live device. A stale heartbeat (crash/network loss)
        # lets the same credentials resume instead of locking the candidate out.
        raise HTTPException(
            409,
            {
                "code": "session_active",
                "message": "This assessment is already active on another device.",
            },
        )
    candidate = (
        await db.execute(select(Candidate).where(Candidate.id == assignment.candidate_id))
    ).scalar_one()
    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == assignment.assessment_id))
    ).scalar_one()
    access = create_access_token(
        "assignment",
        assignment.id,
        org_id=assignment.org_id,
        not_after=assignment.window_end_at,  # FR-026
    )
    refresh = await issue_refresh(
        db,
        subject_type="assignment",
        subject_id=assignment.id,
        not_after=assignment.window_end_at,
    )
    await db.commit()
    response.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True, secure=True, samesite="strict",
        path="/api/v1/auth",
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "assignment_summary": {
            "assignment_id": assignment.id,
            "candidate_name": candidate.full_name,
            "assessment_title": assessment.title,
            "window_start_at": assignment.window_start_at.isoformat(),
            "window_end_at": assignment.window_end_at.isoformat(),
            "server_now": now_utc().isoformat(),
            "has_active_session": active is not None,
            "status": assignment.status,
        },
    }


@router.post("/login")
async def candidate_login(
    body: CandidateLoginIn, response: Response, db: AsyncSession = Depends(get_db)
):
    """Legacy username-based login; the unified /auth/login (email + password) is
    what the UI uses."""
    assignment = (
        await db.execute(
            select(TestAssignment).where(TestAssignment.username == body.username.strip())
        )
    ).scalar_one_or_none()
    if (
        assignment is None
        or assignment.status == "removed"
        or not verify_password(body.password, assignment.password_hash)
    ):
        raise HTTPException(401, "invalid_credentials")
    data = await build_candidate_login_response(db, assignment, response)
    return {"data": data, "error": None}


class RefreshIn(BaseModel):
    refresh_token: str | None = None


@router.post("/refresh")
async def candidate_refresh(
    request: Request,
    response: Response,
    body: RefreshIn | None = None,
    db: AsyncSession = Depends(get_db),
):
    plain = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not plain:
        raise HTTPException(401, "missing_refresh_token")
    old = await rotate_refresh(db, plain)
    if old is None or old.subject_type != "assignment":
        await db.commit()
        raise HTTPException(401, "invalid_refresh_token")
    assignment = (
        await db.execute(select(TestAssignment).where(TestAssignment.id == old.subject_id))
    ).scalar_one_or_none()
    if assignment is None or assignment.window_end_at < now_utc():
        await db.commit()
        raise HTTPException(401, "credentials_expired")
    access = create_access_token(
        "assignment", assignment.id, org_id=assignment.org_id,
        not_after=assignment.window_end_at,
    )
    refresh = await issue_refresh(
        db,
        subject_type="assignment",
        subject_id=assignment.id,
        family_id=old.family_id,
        not_after=assignment.window_end_at,
    )
    await db.commit()
    response.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True, secure=True, samesite="strict",
        path="/api/v1/auth",
    )
    return {"data": {"access_token": access, "refresh_token": refresh}, "error": None}
