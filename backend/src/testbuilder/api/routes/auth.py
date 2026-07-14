from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import User, UserRole
from ...models.base import now_utc
from ...security import create_access_token, verify_password
from ...services.tokens import issue_refresh, revoke_family, rotate_refresh

router = APIRouter(prefix="/auth/admin", tags=["auth"])
unified_router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "tb_refresh"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth",
    )


async def _roles_for(db: AsyncSession, user_id: str) -> list[str]:
    rows = await db.execute(select(UserRole).where(UserRole.user_id == user_id))
    return sorted(r.role for r in rows.scalars())


@router.post("/login")
async def admin_login(body: LoginIn, response: Response, db: AsyncSession = Depends(get_db)):
    user = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid_credentials")
    user.last_login_at = now_utc()
    roles = await _roles_for(db, user.id)
    access = create_access_token("user", user.id, org_id=user.org_id, roles=roles)
    refresh = await issue_refresh(db, subject_type="user", subject_id=user.id)
    await db.commit()
    _set_refresh_cookie(response, refresh)
    return {
        "data": {
            "access_token": access,
            "refresh_token": refresh,
            "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
            "roles": roles,
        },
        "error": None,
    }


@unified_router.post("/login")
async def unified_login(
    body: LoginIn, response: Response, db: AsyncSession = Depends(get_db)
):
    """Single sign-in for everyone (email + password). Admin accounts win when the
    email matches one; otherwise the per-assignment candidate password is checked."""
    email = body.email.lower()
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is not None and user.is_active and verify_password(body.password, user.password_hash):
        user.last_login_at = now_utc()
        roles = await _roles_for(db, user.id)
        access = create_access_token("user", user.id, org_id=user.org_id, roles=roles)
        refresh = await issue_refresh(db, subject_type="user", subject_id=user.id)
        await db.commit()
        _set_refresh_cookie(response, refresh)
        return {
            "data": {
                "kind": "admin",
                "access_token": access,
                "refresh_token": refresh,
                "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
                "roles": roles,
            },
            "error": None,
        }

    from .candidate_auth import build_candidate_login_response, find_assignment_by_email

    assignment = await find_assignment_by_email(db, email, body.password)
    if assignment is None:
        raise HTTPException(401, "invalid_credentials")
    data = await build_candidate_login_response(db, assignment, response)
    return {"data": {"kind": "candidate", **data}, "error": None}


class RefreshIn(BaseModel):
    refresh_token: str | None = None


@router.post("/refresh")
async def admin_refresh(
    request: Request,
    response: Response,
    body: RefreshIn | None = None,
    db: AsyncSession = Depends(get_db),
):
    plain = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not plain:
        raise HTTPException(401, "missing_refresh_token")
    old = await rotate_refresh(db, plain)
    if old is None or old.subject_type != "user":
        await db.commit()  # persist family revocation on reuse detection
        raise HTTPException(401, "invalid_refresh_token")
    user = (
        await db.execute(select(User).where(User.id == old.subject_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(401, "unauthenticated")
    roles = await _roles_for(db, user.id)
    access = create_access_token("user", user.id, org_id=user.org_id, roles=roles)
    refresh = await issue_refresh(
        db, subject_type="user", subject_id=user.id, family_id=old.family_id
    )
    await db.commit()
    _set_refresh_cookie(response, refresh)
    return {"data": {"access_token": access, "refresh_token": refresh}, "error": None}


@router.post("/logout")
async def admin_logout(
    request: Request, response: Response, body: RefreshIn | None = None,
    db: AsyncSession = Depends(get_db),
):
    plain = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if plain:
        old = await rotate_refresh(db, plain)
        if old is not None:
            await revoke_family(db, old.family_id)
        await db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return {"data": {"ok": True}, "error": None}
