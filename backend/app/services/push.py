"""Web-Push an die PWA – ohne Fremddienst außer den Push-Servern der Browser.

Ablauf (RFC 8030 / 8291 / 8292):

1. Die App holt den öffentlichen **VAPID-Schlüssel** (``GET /push/config``) und lässt den
   Browser ein Abo anlegen. Endpunkt + Schlüssel (``p256dh``, ``auth``) landen hier.
2. Zum Senden wird die Nachricht für genau dieses Gerät verschlüsselt (``aes128gcm``) und mit
   einer VAPID-Signatur an den Endpunkt geschickt (Apple, Google, Mozilla, Microsoft).
3. Antwortet der Push-Server mit 404/410, gibt es das Abo nicht mehr → es wird gelöscht.

**Schutz vor Missbrauch:** Der Server schickt Anfragen an die vom Browser gemeldete Adresse.
Damit niemand interne Adressen eintragen kann (SSRF), sind nur https-Endpunkte der bekannten
Push-Dienste erlaubt (:data:`PUSH_HOSTS`).
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit

import http_ece
import httpx
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import PushSubscription, User
from app.services.errors import InvalidInputError

log = structlog.get_logger(__name__)

PUSH_HOSTS = (
    "fcm.googleapis.com",  # Chrome, Android
    "push.apple.com",  # Safari, iPhone (web.push.apple.com)
    "push.services.mozilla.com",  # Firefox
    "notify.windows.com",  # Edge
)
"""Erlaubte Push-Dienste (Domain oder Subdomain davon)."""

TTL_SECONDS = 24 * 3600
"""So lange hält der Push-Dienst eine Nachricht für ein ausgeschaltetes Handy vor."""

MAX_SUBSCRIPTIONS_PER_USER = 10


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# --------------------------------------------------------------- Schlüssel


def generate_private_key() -> str:
    """Neuer VAPID-Schlüssel (P-256, roh, base64url) – für ``PT_PUSH_VAPID_PRIVATE_KEY``."""
    key = ec.generate_private_key(ec.SECP256R1())
    return _b64url_encode(key.private_numbers().private_value.to_bytes(32, "big"))


def vapid(settings: Settings) -> Vapid02 | None:
    """VAPID-Schlüssel aus den Einstellungen (``None``: Push nicht eingerichtet)."""
    if settings.push_vapid_private_key is None:
        return None
    return Vapid02.from_raw(settings.push_vapid_private_key.get_secret_value().encode())


def public_key(settings: Settings) -> str | None:
    """Öffentlicher Schlüssel für ``applicationServerKey`` im Browser (base64url, 65 Byte)."""
    keys = vapid(settings)
    if keys is None:
        return None
    raw = keys.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64url_encode(raw)


# ------------------------------------------------------------ Verschlüsseln


def encrypt(payload: bytes, p256dh: str, auth: str) -> bytes:
    """Nachricht für ein Gerät verschlüsseln (RFC 8291, ``aes128gcm``)."""
    return bytes(
        http_ece.encrypt(
            payload,
            salt=os.urandom(16),
            private_key=ec.generate_private_key(ec.SECP256R1()),  # je Nachricht neu
            dh=_b64url_decode(p256dh),
            auth_secret=_b64url_decode(auth),
            version="aes128gcm",
        )
    )


def check_endpoint(endpoint: str) -> None:
    """Nur https-Adressen der bekannten Push-Dienste (Schutz vor SSRF)."""
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    allowed = any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)
    if parts.scheme != "https" or not allowed or parts.port not in (None, 443):
        raise InvalidInputError("Unbekannter Push-Dienst.", code="push_endpoint")


# ------------------------------------------------------------------- Senden


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    url: str = "/"
    """Seite, die beim Antippen der Nachricht geöffnet wird."""
    tag: str | None = None
    """Gleicher ``tag`` ersetzt eine ältere Nachricht statt eine zweite zu zeigen."""

    def payload(self) -> bytes:
        data = {"title": self.title, "body": self.body, "url": self.url, "tag": self.tag}
        return json.dumps(data, ensure_ascii=False).encode()


class PushOutcome(StrEnum):
    SENT = "sent"
    GONE = "gone"  # Abo existiert nicht mehr → löschen
    FAILED = "failed"


async def send(
    client: httpx.AsyncClient,
    settings: Settings,
    subscription: PushSubscription,
    message: PushMessage,
) -> PushOutcome:
    keys = vapid(settings)
    if keys is None:
        return PushOutcome.FAILED
    parts = urlsplit(subscription.endpoint)
    claims: dict[str, str | int] = {
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int(time.time()) + 12 * 3600,
        "sub": settings.push_subject,
    }
    headers = {
        **keys.sign(claims),
        "TTL": str(TTL_SECONDS),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "Urgency": "normal",
    }
    if message.tag:
        headers["Topic"] = message.tag[:32]
    body = encrypt(message.payload(), subscription.p256dh, subscription.auth)
    try:
        response = await client.post(subscription.endpoint, content=body, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("push.send_error", error=type(exc).__name__)
        return PushOutcome.FAILED
    if response.status_code in (404, 410):
        return PushOutcome.GONE
    if response.is_success:
        return PushOutcome.SENT
    log.warning("push.rejected", status=response.status_code, body=response.text[:200])
    return PushOutcome.FAILED


async def notify_user(
    session: AsyncSession,
    client: httpx.AsyncClient,
    settings: Settings,
    user_id: uuid.UUID,
    message: PushMessage,
) -> int:
    """An alle Geräte eines Nutzers senden; abgelaufene Abos löschen. Gibt Zahl der Erfolge."""
    subscriptions = (
        await session.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).all()
    sent = 0
    for subscription in subscriptions:
        outcome = await send(client, settings, subscription, message)
        if outcome is PushOutcome.SENT:
            sent += 1
            subscription.last_success_at = datetime.now(UTC)
        elif outcome is PushOutcome.GONE:
            await session.delete(subscription)
    await session.flush()
    return sent


# ------------------------------------------------------------------ Abos


async def subscribe(
    session: AsyncSession,
    user: User,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> PushSubscription:
    """Gerät anmelden. Derselbe Endpunkt gehört danach dem angemeldeten Nutzer (Gerätewechsel)."""
    check_endpoint(endpoint)
    for key, size in ((p256dh, 65), (auth, 16)):
        try:
            if len(_b64url_decode(key)) != size:
                raise ValueError
        except ValueError:
            raise InvalidInputError("Ungültiger Push-Schlüssel.", code="push_keys") from None
    existing = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    if existing is None:
        count = len(
            (
                await session.scalars(
                    select(PushSubscription.id).where(PushSubscription.user_id == user.id)
                )
            ).all()
        )
        if count >= MAX_SUBSCRIPTIONS_PER_USER:
            raise InvalidInputError(
                "Zu viele Geräte angemeldet – bitte ein altes abmelden.", code="push_limit"
            )
        existing = PushSubscription(endpoint=endpoint, user_id=user.id, p256dh=p256dh, auth=auth)
        session.add(existing)
    existing.user_id = user.id
    existing.p256dh = p256dh
    existing.auth = auth
    existing.user_agent = (user_agent or "")[:255] or None
    await session.flush()
    return existing


async def unsubscribe(session: AsyncSession, user: User, endpoint: str) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint
        )
    )


async def device_count(session: AsyncSession, user: User) -> int:
    return len(
        (
            await session.scalars(
                select(PushSubscription.id).where(PushSubscription.user_id == user.id)
            )
        ).all()
    )
