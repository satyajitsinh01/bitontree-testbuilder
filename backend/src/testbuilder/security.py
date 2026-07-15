import hashlib
import secrets
import string
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import get_settings
from .models.base import now_utc

_hasher = PasswordHasher()  # argon2id defaults


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, Exception):
        return False


def generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    # guarantee at least one of each class
    core = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
    ]
    core += [secrets.choice(alphabet) for _ in range(length - len(core))]
    secrets.SystemRandom().shuffle(core)
    return "".join(core)


def create_access_token(
    subject_type: str,
    subject_id: str,
    *,
    org_id: str,
    roles: list[str] | None = None,
    assignment_id: str | None = None,
    not_after: datetime | None = None,
) -> str:
    """subject_type: 'user' (admin) or 'assignment' (candidate).

    Candidate tokens are capped at the assignment window end (FR-026) via not_after.
    """
    settings = get_settings()
    exp = now_utc() + timedelta(minutes=settings.access_token_minutes)
    if not_after is not None and not_after < exp:
        exp = not_after
    payload = {
        "sub": subject_id,
        "typ": subject_type,
        "org": org_id,
        "exp": exp,
        "iat": now_utc(),
    }
    if roles is not None:
        payload["roles"] = roles
    if assignment_id is not None:
        payload["asg"] = assignment_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, leeway_seconds: int = 0) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        leeway=leeway_seconds,
    )


def new_refresh_token() -> tuple[str, str]:
    """Return (plaintext, sha256_hash). Only the hash is stored."""
    plain = secrets.token_urlsafe(48)
    return plain, hashlib.sha256(plain.encode()).hexdigest()


def hash_refresh_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()
