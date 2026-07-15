from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import TestAssignment, User, UserRole
from ..models.base import now_utc
from ..security import decode_token

bearer = HTTPBearer(auto_error=False)


@dataclass
class AdminContext:
    user: User
    roles: set[str]
    org_id: str
    request_id: str | None
    ip: str | None


@dataclass
class CandidateContext:
    assignment: TestAssignment
    org_id: str


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    rid = request.headers.get("x-request-id")
    ip = request.client.host if request.client else None
    return rid, ip


async def _payload_or_401(
    creds: HTTPAuthorizationCredentials | None, *, leeway_seconds: int = 0
) -> dict:
    if creds is None:
        raise HTTPException(401, "unauthenticated")
    try:
        return decode_token(creds.credentials, leeway_seconds=leeway_seconds)
    except Exception:
        raise HTTPException(401, "invalid_token") from None


async def get_admin(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> AdminContext:
    payload = await _payload_or_401(creds)
    if payload.get("typ") != "user":
        raise HTTPException(403, "forbidden_role")
    user = (
        await db.execute(select(User).where(User.id == payload["sub"]))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(401, "unauthenticated")
    roles = {
        r.role
        for r in (
            await db.execute(select(UserRole).where(UserRole.user_id == user.id))
        ).scalars()
    }
    rid, ip = _client_meta(request)
    return AdminContext(user=user, roles=roles, org_id=user.org_id, request_id=rid, ip=ip)


def require_roles(*allowed: str):
    """Permissions are the union of held roles (FR-002); any listed role grants access."""

    async def checker(ctx: AdminContext = Depends(get_admin)) -> AdminContext:
        if not ctx.roles.intersection(allowed):
            raise HTTPException(403, "forbidden_role")
        return ctx

    return checker


async def get_candidate(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> CandidateContext:
    payload = await _payload_or_401(creds)
    if payload.get("typ") != "assignment":
        raise HTTPException(403, "forbidden_role")
    assignment = (
        await db.execute(select(TestAssignment).where(TestAssignment.id == payload["sub"]))
    ).scalar_one_or_none()
    if assignment is None or assignment.status == "removed":
        raise HTTPException(401, "unauthenticated")
    if assignment.window_end_at < now_utc():
        raise HTTPException(401, "credentials_expired")
    return CandidateContext(assignment=assignment, org_id=assignment.org_id)


async def get_candidate_for_state(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> CandidateContext:
    """Allow a short post-window grace only to finalize and render submitted state."""
    payload = await _payload_or_401(creds, leeway_seconds=300)
    if payload.get("typ") != "assignment":
        raise HTTPException(403, "forbidden_role")
    assignment = (
        await db.execute(select(TestAssignment).where(TestAssignment.id == payload["sub"]))
    ).scalar_one_or_none()
    if assignment is None or assignment.status == "removed":
        raise HTTPException(401, "unauthenticated")
    return CandidateContext(assignment=assignment, org_id=assignment.org_id)
