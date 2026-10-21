"""eBay.de-Verkäufe über Apify: Suchbegriff, Umwandlung, Zwischenspeicher, Kostenbremse, API.

Apify wird mit ``httpx.MockTransport`` simuliert – kein Test geht ins Netz oder kostet Geld.
Antworten wie im Spike (``docs/phase5/apify_runs_e.md``, Dienst ``epicscrapers``).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.models import AuditLog, Card, CardSet, EbayFetch
from app.services.ebay_auto import build_search, rows_from_items
from app.services.ebay_sold import SoldRow
from tests.conftest import RegisterUser
from tests.pricing_helpers import FakeProvider

API = "/api/v1"
SOLD: list[dict[str, Any]] = [
    {
        "title": "Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch",
        "soldPrice": 25.51,
        "currency": "EUR",
        "soldDateText": "Verkauft 18. Okt 2026",
        "url": "https://www.ebay.de/itm/407297300047",
    },
    {
        "title": "Pokémon TCG Glurak ex 183/165 Deutsch Holo 151 KP 330",
        "soldPrice": 39,
        "currency": "EUR",
        "soldAt": "2026-10-18T10:00:00Z",
        "url": "https://www.ebay.de/itm/407280793398",
    },
    {
        "title": "POKEMON KARTEN 151 DEUTSCH | Alle Karten Auswahl - NEAR MINT",
        "soldPrice": 1.29,
        "currency": "EUR",
        "soldDateText": "Verkauft 17. Okt 2026",
        "url": "https://www.ebay.de/itm/1",
    },
]


@dataclass
class FakeApify:
    """Simuliertes Apify: zählt Läufe, Verbrauch und Ergebnis sind einstellbar."""

    used_usd: float = 0.5
    limit_usd: float = 8.0
    items: list[dict[str, Any]] = field(default_factory=lambda: list(SOLD))
    status: str = "SUCCEEDED"
    runs: list[dict[str, Any]] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer apify_api_test"
        path = request.url.path
        if path.endswith("/users/me/limits"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "current": {"monthlyUsageUsd": self.used_usd},
                        "limits": {"maxMonthlyUsageUsd": self.limit_usd},
                        "monthlyUsageCycle": {"endAt": "2026-11-19T23:59:59.999Z"},
                    }
                },
            )
        if path.endswith("/runs") and request.method == "POST":
            self.runs.append(
                {"actor": path.split("/")[-2], "input": json.loads(request.content)}
                | dict(request.url.params)
            )
            return httpx.Response(
                201,
                json={
                    "data": {
                        "id": f"run{len(self.runs)}",
                        "status": self.status,
                        "statusMessage": "kaputt" if self.status != "SUCCEEDED" else "",
                        "defaultDatasetId": "ds1",
                        "usageTotalUsd": 0.07005,
                    }
                },
            )
        if path.endswith("/datasets/ds1/items"):
            return httpx.Response(200, json=self.items)
        return httpx.Response(404, json={"error": {"message": "unbekannt"}})


@pytest.fixture
def apify() -> FakeApify:
    return FakeApify()


@pytest.fixture
async def apify_client(
    settings: Settings, engine: AsyncEngine, apify: FakeApify
) -> AsyncIterator[AsyncClient]:
    """App mit eingerichtetem Apify (Token in den Einstellungen, simulierte Antworten)."""
    configured = settings.model_copy(update={"apify_token": SecretStr("apify_api_test")})
    app = create_app(
        configured,
        engine=engine,
        price_providers=[FakeProvider()],
        apify_transport=httpx.MockTransport(apify.handler),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client,
    ):
        yield http_client


async def _card(
    factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "Glurak ex",
    number: str = "183",
    language: str = "de",
    official: int | None = 165,
) -> Card:
    async with factory() as session:
        card_set = CardSet(
            external_id=f"sv03.5-{language}-{number}",
            language=language,
            name="151",
            card_count_official=official,
        )
        session.add(card_set)
        await session.flush()
        card = Card(
            external_id=f"sv03.5-{number}-{language}",
            language=language,
            set_id=card_set.id,
            number=number,
            number_norm=number.lstrip("0") or "0",
            name=name,
        )
        session.add(card)
        await session.commit()
        await session.refresh(card, ["card_set"])
        return card


# --------------------------------------------------------------------- Suche


async def test_search_for_raw_graded_and_japanese_cards(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw = await _card(session_factory)
    japanese = await _card(
        session_factory, name="リザードンex", number="006", language="ja", official=165
    )
    promo = await _card(session_factory, name="Pikachu", number="SVP085", official=None)

    assert build_search(raw, None).query == "Glurak ex 183/165 -PSA -BGS -CGC -SGC -TAG -Beckett"
    assert build_search(raw, "PSA 10").query == "Glurak ex 183/165 PSA 10"
    assert build_search(raw, "BGS 10 BL").keywords == "Glurak ex 183/165 BGS 10 Black Label"
    assert build_search(japanese, None).keywords == "Glurak ex 006/165 japanese"
    assert build_search(promo, None).keywords == "Pikachu SVP085"
    assert build_search(raw, None).page_url.startswith(
        "https://www.ebay.de/sch/i.html?_nkw=Glurak+ex+183%2F165+-PSA"
    )
    assert "LH_Sold=1" in build_search(raw, None).page_url


def test_rows_from_items_of_different_services() -> None:
    rows = rows_from_items(
        [
            *SOLD[:2],
            # caffein.dev: Preis als Text, Datum als „endedAt“
            {
                "title": "Glurak",
                "soldPrice": "153.00",
                "soldCurrency": "EUR",
                "endedAt": "2026-10-12",
            },
            {"title": "US-Verkauf", "price": 12, "currency": "USD"},
            {"title": "ohne Preis"},
            {"soldPrice": 3},
        ]
    )

    assert rows == [
        SoldRow(SOLD[0]["title"], "25,51 €", "Verkauft 18. Okt 2026", SOLD[0]["url"]),
        SoldRow(SOLD[1]["title"], "39,00 €", "18.10.2026", SOLD[1]["url"]),
        SoldRow("Glurak", "153,00 €", "12.10.2026", ""),
        SoldRow("US-Verkauf", "12.00 USD", "", ""),
    ]


# ----------------------------------------------------------------------- API


async def test_fetch_then_cached_then_forced_and_saved(
    apify_client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    apify: FakeApify,
) -> None:
    user = await register_user("max@example.com")
    card = await _card(session_factory)
    url = f"{API}/cards/{card.id}/ebay-sold/fetch"

    first = await apify_client.post(url, json={}, headers=user.headers)

    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["cached"], body["cost_usd"], body["used_usd"], body["budget_usd"]) == (
        False,
        "0.07005",
        0.5,
        7.0,
    )
    assert body["query"] == "Glurak ex 183/165 -PSA -BGS -CGC -SGC -TAG -Beckett"
    assert [row["price"] for row in body["rows"]] == ["25,51 €", "39,00 €", "1,29 €"]
    run = apify.runs[0]
    assert run["actor"] == "epicscrapers~ebay-sold-listings-api"
    assert run["input"] == {
        "keywords": ["Glurak ex 183/165"],
        "excludeKeywords": ["PSA", "BGS", "CGC", "SGC", "TAG", "Beckett"],
        "site": "ebay.de",
        "maxItems": 20,
        "days": 90,
    }
    assert (run["maxTotalChargeUsd"], run["timeout"]) == ("0.15", "120")

    # Zweiter Tipp: gemerkt, kein neuer (bezahlter) Lauf.
    again = (await apify_client.post(url, json={}, headers=user.headers)).json()
    assert (again["cached"], again["rows"], len(apify.runs)) == (True, body["rows"], 1)
    forced = (await apify_client.post(url, json={"force": True}, headers=user.headers)).json()
    assert (forced["cached"], len(apify.runs)) == (False, 2)
    # Slab: eigene Suche, eigener Lauf.
    await apify_client.post(url, json={"grading": "PSA 10"}, headers=user.headers)
    assert apify.runs[2]["input"]["keywords"] == ["Glurak ex 183/165 PSA 10"]
    assert apify.runs[2]["input"]["excludeKeywords"] == []

    # Speichern wie beim Lesezeichen: passende Verkäufe sind vorgeschlagen.
    saved = await apify_client.post(
        f"{API}/cards/{card.id}/ebay-sold",
        json={"page_url": body["page_url"], "rows": body["rows"], "save": True},
        headers=user.headers,
    )
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert [sale["suggested"] for sale in result["sales"]] == [True, True, False]
    assert result["groups"][0]["median"] == "32.26"
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(EbayFetch)) == 3
        audit = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "apify.ebay_fetch")
        )
        assert audit == 3


async def test_budget_brake_stops_before_running(
    apify_client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    apify: FakeApify,
) -> None:
    user = await register_user("max@example.com")
    card = await _card(session_factory)
    apify.used_usd = 6.9  # + 0,15 Deckel > 7 $ Budget

    response = await apify_client.post(
        f"{API}/cards/{card.id}/ebay-sold/fetch", json={}, headers=user.headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "budget_exhausted"
    assert "6.90 $ von 7.00 $" in response.json()["error"]["message"]
    assert apify.runs == []
    # Apify-Limit kleiner als das eigene Budget → das Apify-Limit zählt.
    apify.used_usd, apify.limit_usd = 4.9, 5.0
    status = (await apify_client.get(f"{API}/apify/status", headers=user.headers)).json()
    assert (status["budget_usd"], status["remaining_usd"]) == (5.0, pytest.approx(0.1))


async def test_failed_run_and_invalid_grading(
    apify_client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    apify: FakeApify,
) -> None:
    user = await register_user("max@example.com")
    card = await _card(session_factory)
    apify.status = "FAILED"
    url = f"{API}/cards/{card.id}/ebay-sold/fetch"

    failed = await apify_client.post(url, json={}, headers=user.headers)
    invalid = await apify_client.post(url, json={"grading": "PSA zehn"}, headers=user.headers)

    assert failed.status_code == 502
    assert "kaputt" in failed.json()["error"]["message"]
    assert invalid.status_code == 422
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(EbayFetch)) == 0


async def test_without_token_bookmarklet_remains(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    card = await _card(session_factory)

    status = (await client.get(f"{API}/apify/status", headers=user.headers)).json()
    response = await client.post(
        f"{API}/cards/{card.id}/ebay-sold/fetch", json={}, headers=user.headers
    )

    assert status == {
        "configured": False,
        "used_usd": None,
        "limit_usd": None,
        "budget_usd": None,
        "remaining_usd": None,
        "cycle_end": None,
    }
    assert response.status_code == 400
    assert "Lesezeichen" in response.json()["error"]["message"]
    assert (await client.get(f"{API}/apify/status")).status_code == 401
