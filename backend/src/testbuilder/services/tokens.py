from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import RefreshToken
from ..models.base import new_id, now_utc
from ..security import hash_refresh_token, new_refresh_token


async def issue_refresh(
    db: AsyncSession,
    *,
    subject_type: str,
    subject_id: str,
    family_id: str | None = None,
    not_after: datetime | None = None,
) -> str:
    settings = get_settings()
    plain, token_hash = new_refresh_token()
    expires = now_utc() + timedelta(days=settings.refresh_token_days)
    if not_after is not None and not_after < expires:
        expires = not_after
    db.add(
        RefreshToken(
            subject_type=subject_type,
            subject_id=subject_id,
            token_hash=token_hash,
            family_id=family_id or new_id(),
            expires_at=expires,
        )
    )
    return plain


async def rotate_refresh(db: AsyncSession, plain: str) -> RefreshToken | None:
    """Rotate a refresh token. Reuse of an already-rotated token revokes the
    whole family (FR-025). Returns the old row when rotation is allowed."""
    token_hash = hash_refresh_token(plain)
    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.revoked_at is not None:
        # reuse detected -> kill the family
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == row.family_id)
            .values(revoked_at=now_utc())
        )
        return None
    if row.expires_at < now_utc():
        return None
    row.revoked_at = now_utc()
    return row


async def revoke_family(db: AsyncSession, family_id: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id)
        .values(revoked_at=now_utc())
    )
