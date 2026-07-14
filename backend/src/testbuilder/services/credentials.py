import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import TestAssignment
from ..security import generate_password, hash_password


async def generate_username(db: AsyncSession, assessment_title: str) -> str:
    """`{shortcode}-{seq}` e.g. BES-0173 (research R6)."""
    code = "".join(w[0] for w in assessment_title.split()[:3]).upper() or "TST"
    for _ in range(20):
        candidate = f"{code}-{secrets.randbelow(10000):04d}"
        exists = (
            await db.execute(
                select(TestAssignment).where(TestAssignment.username == candidate)
            )
        ).scalar_one_or_none()
        if exists is None:
            return candidate
    return f"{code}-{secrets.token_hex(4)}"


def make_credentials() -> tuple[str, str]:
    """Returns (plaintext_password, password_hash)."""
    password = generate_password(12)
    return password, hash_password(password)
