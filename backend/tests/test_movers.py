"""Preisbewegungen der eigenen Sammlung (Cardmarket-Trend, Gewinner/Verlierer)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, PricePoint
from tests.conftest import RegisterUser
from tests.pricing_helpers import make_card

API = "/api/v1"


async def _trend(
    factory: async_sessionmaker[AsyncSession],
    card: Card,
    days_ago: int,
    value: str,
    *,
    variant: str = "normal",
) -> None:
    async with factory() as session:
        session.add(
            PricePoint(
                card_id=card.id,
                source="cardmarket",
                variant=variant,
                metric="trend",
                value=Decimal(value),
                currency="EUR",
                source_updated_at=datetime.now(UTC) - timedelta(days=days_ago),
            )
        )
        await session.commit()


async def _own(client: AsyncClient, headers: dict[str, str], card: Card, **extra: object) -> None:
    response = await client.post(
        f"{API}/collection/items", json={"card_id": str(card.id), **extra}, headers=headers
    )
    assert response.status_code == 201, response.text


async def test_gainers_and_losers_of_own_cards(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    other = await register_user("eva@example.com")
    riser = await make_card(session_factory, external_id="a-1", name="Glurak", number="1")
    faller = await make_card(session_factory, external_id="b-2", name="Turtok", number="2")
    cheap = await make_card(session_factory, external_id="c-3", name="Rattfratz", number="3")
    flat = await make_card(session_factory, external_id="d-4", name="Pikachu", number="4")
    fresh = await make_card(session_factory, external_id="e-5", name="Mew", number="5")
    for card, before, now in (
        (riser, "10.00", "15.00"),  # +50 %
        (faller, "20.00", "18.00"),  # −10 %
        (cheap, "0.50", "1.00"),  # unter 1 € → Rauschen
        (flat, "10.00", "10.20"),  # +2 % → Rauschen
    ):
        await _trend(session_factory, card, 10, before)
        await _trend(session_factory, card, 1, now)
    await _trend(session_factory, fresh, 1, "50.00")  # kein Wert vor dem Zeitraum
    await _trend(session_factory, riser, 10, "3.00", variant="reverse")  # nicht im Besitz
    await _trend(session_factory, riser, 1, "9.00", variant="reverse")
    for card in (riser, faller, cheap, flat, fresh):
        await _own(client, user.headers, card, quantity=2 if card is riser else 1)
    await _own(client, user.headers, faller, grading_company="PSA", grade="10")  # zählt nicht
    await _own(client, other.headers, faller, quantity=5)  # anderer Nutzer

    response = await client.get(f"{API}/collection/movers", headers=user.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["days"] == 7
    assert [(m["card"]["name"], m["change"], m["change_pct"]) for m in body["gainers"]] == [
        ("Glurak", "10.00", "50.0")
    ]
    assert [(m["card"]["name"], m["change"], m["quantity"]) for m in body["losers"]] == [
        ("Turtok", "-2.00", 1)
    ]
    assert body["gainers"][0]["before"] == "10.00"
    # Längerer Zeitraum: Werte vor 30 Tagen fehlen → keine Bewegung.
    month = (await client.get(f"{API}/collection/movers?days=30", headers=user.headers)).json()
    assert (month["gainers"], month["losers"]) == ([], [])
    assert (
        await client.get(f"{API}/collection/movers?days=0", headers=user.headers)
    ).status_code == 422
