"""Passwörter, Tokens und Zufallscodes.

* Passwörter: Argon2id (``argon2-cffi``), inkl. automatischem Rehash bei geänderten Parametern.
* Access-Tokens: kurzlebige JWTs (HS256), Inhalt nur Nutzer-ID, Rolle und Ablauf.
* Refresh-Tokens, Einladungs- und Reset-Codes: zufällige Geheimnisse, in der Datenbank
  ausschließlich als SHA-256-Hash gespeichert.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"  # noqa: S105 – Token-Typ, kein Passwort

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Erzeugt einen Argon2id-Hash."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Prüft ein Passwort gegen den gespeicherten Hash (zeitkonstant)."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """``True``, wenn der Hash mit veralteten Parametern erzeugt wurde."""
    return _password_hasher.check_needs_rehash(password_hash)


# Gültiger Dummy-Hash, damit ein Login mit unbekannter E-Mail genauso lange dauert
# wie einer mit falschem Passwort (verhindert das Ausspähen registrierter Adressen).
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def generate_secret(nbytes: int = 32) -> str:
    """Zufälliges, URL-sicheres Geheimnis (Standard: 256 Bit)."""
    return secrets.token_urlsafe(nbytes)


def generate_human_code() -> str:
    """Gut abtippbarer Code (z. B. für Einladungen): 4 Gruppen à 5 Zeichen, ~100 Bit.

    Ohne leicht verwechselbare Zeichen (0/O, 1/I/L).
    """
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(20))
    return "-".join(raw[i : i + 5] for i in range(0, 20, 5))


def hash_token(token: str) -> str:
    """SHA-256-Hash eines Geheimnisses (für die Speicherung in der Datenbank).

    Einladungscodes werden vorher normalisiert, damit Groß/Klein und Leerzeichen
    beim Abtippen keine Rolle spielen.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_human_code(code: str) -> str:
    """``" abcde-fghij "`` → ``"ABCDE-FGHIJ"``."""
    return "".join(code.split()).upper()


@dataclass(frozen=True)
class AccessTokenClaims:
    """Geprüfter Inhalt eines Access-Tokens."""

    user_id: uuid.UUID
    role: str
    expires_at: datetime


def create_access_token(
    *, user_id: uuid.UUID, role: str, secret: str, ttl: timedelta, now: datetime | None = None
) -> str:
    """Signiert ein kurzlebiges Access-Token."""
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "iat": issued_at,
        "exp": issued_at + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


class InvalidTokenError(Exception):
    """Token ist ungültig, abgelaufen oder vom falschen Typ."""


def decode_access_token(token: str, *, secret: str) -> AccessTokenClaims:
    """Prüft Signatur, Ablauf und Typ eines Access-Tokens."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("falscher Token-Typ")
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise InvalidTokenError("ungültige Nutzer-ID") from exc
    return AccessTokenClaims(
        user_id=user_id,
        role=str(payload.get("role", "")),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )
