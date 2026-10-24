"""Meldungen „Das fehlt“: melden, Admin wird benachrichtigt, abhaken."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.models import PushSubscription
from app.services import push
from tests.conftest import Account, RegisterUser
from tests.test_alerts import Device

API = "/api/v1"


async def test_report_notifies_admin_and_can_be_closed(
    client: AsyncClient,
    register_user: RegisterUser,
    admin: Account,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, push.PushMessage]] = []

    async def fake_send(
        _client: httpx.AsyncClient,
        _settings: Settings,
        subscription: PushSubscription,
        message: push.PushMessage,
    ) -> push.PushOutcome:
        sent.append((subscription.endpoint, message))
        return push.PushOutcome.SENT

    monkeypatch.setattr(push, "send", fake_send)
    device = Device()
    await client.post(
        f"{API}/push/subscriptions", json=device.subscription(), headers=admin.headers
    )
    alice = await register_user("alice@example.com")

    created = await client.post(
        f"{API}/reports",
        json={
            "kind": "sealed",
            "text": "  Mega Evolution ETB (japanisch) fehlt  ",
            "context": "etb",
        },
        headers=alice.headers,
    )
    assert created.status_code == 201, created.text
    report = created.json()
    assert (report["kind"], report["text"], report["done_at"]) == (
        "sealed",
        "Mega Evolution ETB (japanisch) fehlt",
        None,
    )
    assert len(sent) == 1
    assert sent[0][1].title.endswith(": Produkt fehlt")
    assert sent[0][1].url == "/admin/reports"

    mine = (await client.get(f"{API}/reports/mine", headers=alice.headers)).json()
    assert [r["id"] for r in mine] == [report["id"]]

    forbidden = await client.get(f"{API}/admin/reports", headers=alice.headers)
    assert forbidden.status_code == 403
    listed = (await client.get(f"{API}/admin/reports", headers=admin.headers)).json()
    assert [r["id"] for r in listed] == [report["id"]]

    done = await client.patch(
        f"{API}/admin/reports/{report['id']}", json={"done": True}, headers=admin.headers
    )
    assert done.json()["done_at"] is not None


async def test_report_validation(client: AsyncClient, register_user: RegisterUser) -> None:
    alice = await register_user("alice@example.com")
    short = await client.post(
        f"{API}/reports", json={"kind": "card", "text": " a "}, headers=alice.headers
    )
    assert short.status_code == 422
    bad_kind = await client.post(
        f"{API}/reports", json={"kind": "spam", "text": "Hallo Welt"}, headers=alice.headers
    )
    assert bad_kind.status_code == 422
