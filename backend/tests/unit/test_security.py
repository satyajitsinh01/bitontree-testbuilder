from datetime import timedelta

import jwt
import pytest

from testbuilder.models.base import now_utc
from testbuilder.security import (
    create_access_token,
    decode_token,
    generate_password,
    hash_password,
    verify_password,
)


def test_argon2_roundtrip():
    hashed = hash_password("s3cret-Passw0rd")
    assert hashed.startswith("$argon2")
    assert verify_password("s3cret-Passw0rd", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_garbage_hash_is_false():
    assert not verify_password("anything", "not-a-hash")


def test_generated_password_strength():
    for _ in range(20):
        password = generate_password(12)
        assert len(password) == 12
        assert any(c.islower() for c in password)
        assert any(c.isupper() for c in password)
        assert any(c.isdigit() for c in password)


def test_access_token_roundtrip_and_claims():
    token = create_access_token("user", "u1", org_id="o1", roles=["hr_admin"])
    payload = decode_token(token)
    assert payload["sub"] == "u1"
    assert payload["typ"] == "user"
    assert payload["roles"] == ["hr_admin"]


def test_candidate_token_capped_at_window_end():
    """FR-026: token exp never exceeds the assessment window end."""
    import calendar

    window_end = now_utc() + timedelta(minutes=3)
    token = create_access_token("assignment", "a1", org_id="o1", not_after=window_end)
    payload = decode_token(token)
    window_end_ts = calendar.timegm(window_end.utctimetuple())
    assert payload["exp"] <= window_end_ts + 1


def test_tampered_token_rejected():
    token = create_access_token("user", "u1", org_id="o1")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token[:-4] + "AAAA")
