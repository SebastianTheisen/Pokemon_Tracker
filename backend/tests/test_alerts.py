"""Preisalarme und Web-Push: Anlegen, Prüfen nach der Preisrunde, Geräte, Versand."""

from __future__ import annotations

import base64
import json
import os
from datetime import timedelta
from typing import Any

import http_ece
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, PriceAlert, PushSubscription
from app.services import push
from app.services.price_health import SourceHealth
from app.worker import refresh_tracked_prices
from tests.conftest import Account, RegisterUser
from tests.pricing_helpers import UPDATED, FakeProvider, cardmarket, make_card

API = "/api/v1"
ENDPOINT = "https://web.push.apple.com/QGuQyavXutnMH"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Device:
    """Simuliertes Gerät: echtes Schlüsselpaar, kann empfangene Nachrichten entschlüsseln."""

    def __init__(self, endpoint: str = ENDPOINT) -> None:
        self.endpoint = endpoint
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)

    def subscription(self) -> dict[str, Any]:
        public = self.key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": _b64(public), "auth": _b64(self.auth)},
        }

    def read(self, body: bytes) -> dict[str, Any]:
        plain = http_ece.decrypt(body, private_key=self.key, auth_secret=self.auth)
        data: dict[str, Any] = json.loads(plain)
        return data


@pytest.fixture
def push_settings(settings: Settings) -> Settings:
    settings.push_vapid_private_key = SecretStr(push.generate_private_key())
    settings.push_subject = "https://kartenkiste.example.test"
    return settings


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, push.PushMessage]]:
    """Statt Versand ins Netz: Endpunkt und Nachricht merken."""
    calls: list[tuple[str, push.PushMessage]] = []

    async def fake_send(
        _client: httpx.AsyncClient,
        _settings: Settings,
        subscription: PushSubscription,
        message: push.PushMessage,
    ) -> push.PushOutcome:
        calls.append((subscription.endpoint, message))
        return push.PushOutcome.SENT

    monkeypatch.setattr(push, "send", fake_send)
    return calls


async def _alert(client: AsyncClient, user: Account, **body: Any) -> httpx.Response:
    return await client.post(f"{API}/alerts", json=body, headers=user.headers)


# ------------------------------------------------------------------- Alarme


async def test_create_list_update_delete_alert(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    card = await make_card(session_factory)
    price_provider.quotes = [cardmarket("trend", "100")]
    await client.get(f"{API}/cards/{card.id}/prices", headers=alice.headers)  # Preis speichern

    created = await _alert(
        client, alice, card_id=str(card.id), direction="above", target="150", condition="LP"
    )
    assert created.status_code == 201, created.text
    alert = created.json()
    assert (alert["direction"], alert["target"], alert["condition"], alert["active"]) == (
        "above",
        "150.00",
        "LP",
        True,
    )
    assert alert["current_value"] == "55.00"  # LP = 100 × 0,55
    assert alert["card"]["id"] == str(card.id)

    changed = await client.patch(
        f"{API}/alerts/{alert['id']}", json={"target": "50"}, headers=alice.headers
    )
    assert changed.json()["target"] == "50.00"
    listed = (await client.get(f"{API}/alerts", headers=alice.headers)).json()
    assert [a["id"] for a in listed] == [alert["id"]]

    deleted = await client.delete(f"{API}/alerts/{alert['id']}", headers=alice.headers)
    assert deleted.status_code == 204
    assert (await client.get(f"{API}/alerts", headers=alice.headers)).json() == []


async def test_alert_validation_and_isolation(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    card = await make_card(session_factory)

    no_target = await _alert(client, alice, direction="below", target="10")
    assert no_target.status_code == 400
    zero = await _alert(client, alice, card_id=str(card.id), direction="below", target="0")
    assert zero.status_code == 422
    bad_condition = await _alert(
        client, alice, card_id=str(card.id), direction="below", target="5", condition="XX"
    )
    assert bad_condition.status_code == 422

    alert = (
        await _alert(client, alice, card_id=str(card.id), direction="below", target="5")
    ).json()
    foreign = await client.patch(
        f"{API}/alerts/{alert['id']}", json={"active": False}, headers=bob.headers
    )
    assert foreign.status_code == 404
    assert (await client.get(f"{API}/alerts", headers=bob.headers)).json() == []
    assert (await client.get(f"{API}/alerts")).status_code == 401


async def test_daily_round_fires_alert_once_and_rearm(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
    push_settings: Settings,
    sent: list[tuple[str, push.PushMessage]],
) -> None:
    alice = await register_user("alice@example.com")
    device = Device()
    subscribed = await client.post(
        f"{API}/push/subscriptions", json=device.subscription(), headers=alice.headers
    )
    assert subscribed.status_code == 201, subscribed.text
    card = await make_card(session_factory)  # Nachtara VMAX
    price_provider.quotes = [cardmarket("trend", "100")]
    above = (
        await _alert(client, alice, card_id=str(card.id), direction="above", target="110")
    ).json()
    below = (
        await _alert(client, alice, card_id=str(card.id), direction="below", target="80")
    ).json()

    health = SourceHealth(threshold=3, pause=timedelta(minutes=60))
    summary = await refresh_tracked_prices(session_factory, push_settings, [price_provider], health)
    assert summary.alerts_triggered == 0  # 100 € – keins erreicht
    assert sent == []

    price_provider.quotes = [cardmarket("trend", "120", updated=UPDATED + timedelta(days=1))]
    summary = await refresh_tracked_prices(session_factory, push_settings, [price_provider], health)
    assert summary.alerts_triggered == 1
    assert len(sent) == 1
    endpoint, message = sent[0]
    assert endpoint == ENDPOINT
    assert message.title == "Preisalarm: Nachtara VMAX"
    assert message.body == "Jetzt 120,00 € – gestiegen auf dein Ziel 110,00 €."
    assert message.url == f"/card/{card.id}"

    alerts = {a["id"]: a for a in (await client.get(f"{API}/alerts", headers=alice.headers)).json()}
    assert alerts[above["id"]]["active"] is False
    assert alerts[above["id"]]["triggered_value"] == "120.00"
    assert alerts[below["id"]]["active"] is True

    # Nächste Runde: Preis bleibt über dem Ziel – keine zweite Nachricht.
    await refresh_tracked_prices(session_factory, push_settings, [price_provider], health)
    assert len(sent) == 1

    rearmed = await client.patch(
        f"{API}/alerts/{above['id']}", json={"active": True}, headers=alice.headers
    )
    assert (rearmed.json()["active"], rearmed.json()["triggered_at"]) == (True, None)
    await refresh_tracked_prices(session_factory, push_settings, [price_provider], health)
    assert len(sent) == 2


async def test_alert_cards_are_tracked_by_the_daily_round(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
    settings: Settings,
) -> None:
    """Auch ohne Sammlung/Merkliste holt die Runde Preise für Karten mit aktivem Alarm."""
    alice = await register_user("alice@example.com")
    card = await make_card(session_factory)
    await _alert(client, alice, card_id=str(card.id), direction="below", target="5")
    price_provider.quotes = [cardmarket("trend", "100")]
    health = SourceHealth(threshold=3, pause=timedelta(minutes=60))
    summary = await refresh_tracked_prices(session_factory, settings, [price_provider], health)
    assert summary.cards == 1


# --------------------------------------------------------------------- Push


async def test_push_config_subscribe_test_and_unsubscribe(
    client: AsyncClient,
    register_user: RegisterUser,
    push_settings: Settings,
    sent: list[tuple[str, push.PushMessage]],
) -> None:
    alice = await register_user("alice@example.com")
    config = (await client.get(f"{API}/push/config", headers=alice.headers)).json()
    assert config["devices"] == 0
    assert len(base64.urlsafe_b64decode(config["public_key"] + "==")) == 65

    no_device = await client.post(f"{API}/push/test", headers=alice.headers)
    assert no_device.json()["error"]["code"] == "push_no_device"

    device = Device()
    for _ in range(2):  # erneutes Anmelden desselben Geräts ist harmlos
        response = await client.post(
            f"{API}/push/subscriptions", json=device.subscription(), headers=alice.headers
        )
        assert response.json()["devices"] == 1

    tested = await client.post(f"{API}/push/test", headers=alice.headers)
    assert tested.json() == {"sent": 1}
    assert sent[0][1].body == "Benachrichtigungen funktionieren 👍"

    removed = await client.delete(
        f"{API}/push/subscriptions", params={"endpoint": ENDPOINT}, headers=alice.headers
    )
    assert removed.status_code == 204
    config = (await client.get(f"{API}/push/config", headers=alice.headers)).json()
    assert config["devices"] == 0


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/x",  # kein https
        "https://localhost/push",
        "https://db:5432/push",
        "https://evilpush.apple.com.attacker.test/x",
        "https://fcm.googleapis.com:8443/fcm/send/x",
    ],
)
async def test_push_endpoint_must_be_known_service(
    client: AsyncClient, register_user: RegisterUser, endpoint: str
) -> None:
    """Schutz vor SSRF: Der Server schickt nur an bekannte Push-Dienste."""
    alice = await register_user("alice@example.com")
    response = await client.post(
        f"{API}/push/subscriptions", json=Device(endpoint).subscription(), headers=alice.headers
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "push_endpoint"


async def test_push_rejects_invalid_keys(client: AsyncClient, register_user: RegisterUser) -> None:
    alice = await register_user("alice@example.com")
    body = Device().subscription()
    body["keys"]["p256dh"] = _b64(b"x" * 40)
    response = await client.post(f"{API}/push/subscriptions", json=body, headers=alice.headers)
    assert response.json()["error"]["code"] == "push_keys"


async def test_push_test_without_server_key(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    alice = await register_user("alice@example.com")
    config = (await client.get(f"{API}/push/config", headers=alice.headers)).json()
    assert config["public_key"] is None
    response = await client.post(f"{API}/push/test", headers=alice.headers)
    assert response.json()["error"]["code"] == "push_off"


# -------------------------------------------------------------- Versand echt


async def test_send_encrypts_signs_and_drops_gone_devices(
    push_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    register_user: RegisterUser,
) -> None:
    """Echter Versandweg gegen einen Schein-Push-Dienst: Kopfzeilen, Verschlüsselung, 410."""
    alice = await register_user("alice@example.com")
    device = Device()
    await client.post(
        f"{API}/push/subscriptions", json=device.subscription(), headers=alice.headers
    )
    received: list[httpx.Request] = []
    status = {"code": 201}

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(status["code"])

    message = push.PushMessage(title="Preisalarm: Glurak", body="Jetzt 10,00 €", url="/x", tag="t")
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        session_factory() as session,
    ):
        owner_id = await session.scalar(select(PushSubscription.user_id))
        assert owner_id is not None
        assert await push.notify_user(session, http, push_settings, owner_id, message) == 1

        request = received[0]
        assert str(request.url) == ENDPOINT
        assert request.headers["content-encoding"] == "aes128gcm"
        assert request.headers["ttl"] == str(push.TTL_SECONDS)
        assert request.headers["authorization"].startswith("vapid t=")
        assert device.read(request.content) == {
            "title": "Preisalarm: Glurak",
            "body": "Jetzt 10,00 €",
            "url": "/x",
            "tag": "t",
        }

        status["code"] = 410  # Gerät hat Benachrichtigungen abgeschaltet
        assert await push.notify_user(session, http, push_settings, owner_id, message) == 0
        await session.commit()
        assert await session.scalar(select(PushSubscription)) is None


async def test_deleting_card_removes_alerts(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    card = await make_card(session_factory)
    await _alert(client, alice, card_id=str(card.id), direction="below", target="5")
    async with session_factory() as session:
        await session.delete(await session.get(Card, card.id))
        await session.commit()
        assert await session.scalar(select(PriceAlert)) is None
