from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import User, UserRole
from ...models.identity import ROLES
from ...security import generate_password, hash_password
from ...services.audit import write_audit
from ..deps import AdminContext, require_roles

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    roles: list[str]
    password: str | None = None

    @field_validator("roles")
    @classmethod
    def roles_valid(cls, v: list[str]) -> list[str]:
        bad = set(v) - set(ROLES)
        if bad:
            raise ValueError(f"unknown roles: {sorted(bad)}")
        if not v:
            raise ValueError("at least one role required")
        return v


class UserPatch(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    roles: list[str] | None = None

    @field_validator("roles")
    @classmethod
    def roles_valid(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and set(v) - set(ROLES):
            raise ValueError("unknown roles")
        return v


async def _user_out(db: AsyncSession, user: User) -> dict:
    roles = (
        (await db.execute(select(UserRole).where(UserRole.user_id == user.id))).scalars().all()
    )
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "roles": sorted(r.role for r in roles),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.get("")
async def list_users(
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    users = (
        (await db.execute(select(User).where(User.org_id == ctx.org_id))).scalars().all()
    )
    return {"data": {"items": [await _user_out(db, u) for u in users]}, "error": None}


@router.post("", status_code=201)
async def create_user(
    body: UserCreate,
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    email = body.email.lower()
    exists = (
        await db.execute(select(User).where(User.org_id == ctx.org_id, User.email == email))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "email_already_exists")
    password = body.password or generate_password()
    user = User(
        org_id=ctx.org_id,
        email=email,
        full_name=body.full_name,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    for role in set(body.roles):
        db.add(UserRole(user_id=user.id, role=role))
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        after={"email": email, "roles": body.roles},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    out = await _user_out(db, user)
    out["initial_password"] = None if body.password else password  # one-time reveal
    return {"data": out, "error": None}


@router.patch("/{user_id}")
async def patch_user(
    user_id: str,
    body: UserPatch,
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    user = (
        await db.execute(select(User).where(User.id == user_id, User.org_id == ctx.org_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "not_found")
    before = await _user_out(db, user)
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.roles is not None:
        existing = (
            (await db.execute(select(UserRole).where(UserRole.user_id == user.id)))
            .scalars()
            .all()
        )
        for r in existing:
            await db.delete(r)
        for role in set(body.roles):
            db.add(UserRole(user_id=user.id, role=role))
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="user.updated",
        entity_type="user",
        entity_id=user.id,
        before=before,
        after=body.model_dump(exclude_none=True),
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": await _user_out(db, user), "error": None}
