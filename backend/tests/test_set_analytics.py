"""Set-Analyse aus dem Cardmarket-Preisführer – Werte von Hand nachgerechnet."""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, CmPrice
from tests.conftest import RegisterUser

API = "/api/v1"


async def test_set_value_change_stability_and_movers(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    # Nummer, Varianten, Preisführer (trend, avg1, avg30, trend-holo)
    specs = [
        ("1", {"normal": True, "reverse": True}, {"trend": 110, "avg1": 112, "avg30": 100, "trend-holo": 20}),  # noqa: E501
        ("2", {"holo": True}, {"trend": 45, "avg1": 46, "avg30": 50}),
        ("3", {"normal": True}, {"trend": 0.5, "avg1": 0.9, "avg30": 0.2}),  # unter 1 €: kein Mover
        ("4", {"normal": True}, {"trend": 10, "avg1": 10, "avg30": 10}),
        ("5", None, None),  # kein Preis
    ]  # fmt: skip
    async with session_factory() as session:
        card_set = CardSet(external_id="sv9", language="de", name="Reisegefährten")
        session.add(card_set)
        await session.flush()
        for index, (number, variants, metrics) in enumerate(specs):
            session.add(
                Card(
                    external_id=f"sv9-{number}",
                    language="de",
                    set_id=card_set.id,
                    number=number,
                    number_norm=number,
                    name=f"Karte {number}",
                    variants=variants,
                    cardmarket_product_override=900 + index,
                )
            )
            if metrics:
                session.add(
                    CmPrice(id_product=900 + index, metrics=metrics, updated_at=datetime.now(UTC))
                )
        await session.commit()
        set_id = card_set.id

    data = (
        await client.get(f"{API}/collection/sets/{set_id}/analytics", headers=alice.headers)
    ).json()
    assert (data["cards_total"], data["cards_priced"]) == (5, 4)
    assert data["set_value"] == "165.50"  # 110 + 45 + 0,5 + 10
    assert data["master_value"] == "185.50"  # + Reverse von Karte 1
    # (165,5 − 160,2) / 160,2
    assert round(data["change"], 4) == round(5.3 / 160.2, 4)
    # Schwankung (ab 1 €): |112−100|/100 = 0,12; |46−50|/50 = 0,08; 0 → Median 0,08 → normal
    assert round(data["volatility"], 4) == 0.08
    assert data["stability"] == "normal"
    assert [m["card"]["number"] for m in data["gainers"]] == ["1"]  # +10 %
    assert [m["card"]["number"] for m in data["losers"]] == ["2"]  # −10 %
    assert [c["card"]["number"] for c in data["top_cards"]] == ["1", "2", "4", "3"]

    unknown = await client.get(
        f"{API}/collection/sets/00000000-0000-0000-0000-000000000000/analytics",
        headers=alice.headers,
    )
    assert unknown.status_code == 404
