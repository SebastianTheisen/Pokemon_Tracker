"""Unit-Tests für Passwörter, Tokens und Codes."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core import security

SECRET = "unit-test-secret-mit-ausreichender-laenge"


def test_password_hash_roundtrip() -> None:
    hashed = security.hash_password("geheimes-passwort")

    assert hashed.startswith("$argon2id$")
    assert security.verify_password("geheimes-passwort", hashed)
    assert not security.verify_password("falsches-passwort", hashed)


def test_verify_password_rejects_garbage_hash() -> None:
    assert not security.verify_password("egal", "kein-gueltiger-hash")


def test_human_code_format_and_normalization() -> None:
    code = security.generate_human_code()

    assert re.fullmatch(r"[A-Z2-9]{5}(-[A-Z2-9]{5}){3}", code)
    assert not set(code) & set("01OIL")
    assert security.normalize_human_code(f"  {code.lower()} ") == code


def test_hash_token_is_stable_and_not_plaintext() -> None:
    assert security.hash_token("abc") == security.hash_token("abc")
    assert security.hash_token("abc") != "abc"
    assert len(security.hash_token("abc")) == 64


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = security.create_access_token(
        user_id=user_id, role="admin", secret=SECRET, ttl=timedelta(minutes=5)
    )

    claims = security.decode_access_token(token, secret=SECRET)

    assert claims.user_id == user_id
    assert claims.role == "admin"


def test_expired_access_token_is_rejected() -> None:
    token = security.create_access_token(
        user_id=uuid.uuid4(),
        role="user",
        secret=SECRET,
        ttl=timedelta(minutes=5),
        now=datetime.now(UTC) - timedelta(hours=1),
    )

    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token, secret=SECRET)


def test_token_with_wrong_secret_is_rejected() -> None:
    token = security.create_access_token(
        user_id=uuid.uuid4(), role="user", secret=SECRET, ttl=timedelta(minutes=5)
    )

    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token, secret=SECRET + "x")


def test_token_of_other_type_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )

    with pytest.raises(security.InvalidTokenError, match="Token-Typ"):
        security.decode_access_token(token, secret=SECRET)


def test_unsigned_token_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
        key=None,
        algorithm="none",
    )

    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token, secret=SECRET)
