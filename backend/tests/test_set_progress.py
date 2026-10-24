"""Set-Fortschritt: Set und Master-Set (Reverse Holo), fehlende Karten, Merkliste."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet
from tests.conftest import RegisterUser
from tests.pricing_helpers import FakeProvider, cardmarket

API = "/api/v1"


async def _set_with_cards(factory: async_sessionmaker[AsyncSession]) -> tuple[CardSet, list[Card]]:
    """Set mit 4 Karten: 1 (normal+reverse), 2 (holo+reverse), 10 (nur holo), TG01 (unbekannt)."""
    async with factory() as session:
        card_set = CardSet(
            external_id="sv1", language="de", name="Karmesin & Purpur", card_count_official=3
        )
        session.add(card_set)
        await session.flush()
        specs: list[tuple[str, dict[str, bool] | None]] = [
            ("10", {"holo": True}),
            ("TG01", None),
            ("2", {"holo": True, "reverse": True}),
            ("1", {"normal": True, "reverse": True}),
        ]
        cards = [
            Card(
                external_id=f"sv1-{number}",
                language="de",
                set_id=card_set.id,
                number=number,
                number_norm=number,
                name=f"Karte {number}",
                variants=variants,
            )
            for number, variants in specs
        ]
        session.add_all(cards)
        await session.commit()
        for card in cards:
            await session.refresh(card, ["card_set"])
        return card_set, cards


async def test_progress_counts_set_and_master_and_missing_value(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    card_set, cards = await _set_with_cards(session_factory)
    by_number = {c.number: c for c in cards}
    price_provider.quotes = [cardmarket("trend", "10")]

    async def add(user: Any, number: str, **body: Any) -> None:
        response = await client.post(
            f"{API}/collection/items",
            json={"card_id": str(by_number[number].id), **body},
            headers=user.headers,
        )
        assert response.status_code == 201, response.text

    await add(alice, "1", variant="reverse")  # nur Reverse von 1
    await add(alice, "2", quantity=2)  # Hauptfassung von 2
    await add(alice, "2", variant="reverse", grading_company="PSA", grade="10")  # Slab zählt
    await add(bob, "10")  # fremde Sammlung zählt nicht

    progress = (
        await client.get(f"{API}/collection/sets/{card_set.id}", headers=alice.headers)
    ).json()
    assert [c["card"]["number"] for c in progress["cards"]] == ["1", "2", "10", "TG01"]
    assert (progress["cards_owned"], progress["cards_total"]) == (2, 4)
    # Master: 1 (2 Plätze) + 2 (2) + 10 (1) + TG01 (1) = 6; besessen: 1-reverse, 2, 2-reverse
    assert (progress["master_owned"], progress["master_total"]) == (3, 6)
    first = progress["cards"][0]
    assert (first["owned_normal"], first["owned_reverse"], first["reverse"]) == (0, 1, True)
    assert progress["cards"][1]["owned_normal"] == 2
    # Fehlende Plätze mit Preis (Preise gelten für alle – Karte 10 hat einen durch Bob):
    # 1 normal (10 €) + 10 (10 €); Reverse-Preise gibt es hier nicht, TG01 hat keinen Preis.
    assert progress["missing_value"] == "20.00"
    assert progress["missing_set_value"] == "10.00"  # nur Karte 10 fehlt ganz und hat Preis

    overview = (await client.get(f"{API}/collection/sets", headers=alice.headers)).json()
    entry = next(o for o in overview if o["card_set"]["id"] == str(card_set.id))
    assert (entry["cards_total"], entry["master_total"], entry["master_owned"]) == (4, 6, 3)


async def test_missing_cards_to_wishlist_in_bulk(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    card_set, cards = await _set_with_cards(session_factory)
    first, second = str(cards[0].id), str(cards[1].id)
    await client.post(f"{API}/wishlist", json={"card_id": first}, headers=alice.headers)

    added = await client.post(
        f"{API}/wishlist/bulk", json={"card_ids": [first, second, second]}, headers=alice.headers
    )
    assert added.json() == {"count": 1}  # first war schon da, second doppelt
    progress = (
        await client.get(f"{API}/collection/sets/{card_set.id}", headers=alice.headers)
    ).json()
    assert sum(c["on_wishlist"] for c in progress["cards"]) == 2

    unknown = await client.post(
        f"{API}/wishlist/bulk",
        json={"card_ids": ["00000000-0000-0000-0000-000000000000"]},
        headers=alice.headers,
    )
    assert unknown.status_code == 404


async def test_unknown_set_is_not_found(client: AsyncClient, register_user: RegisterUser) -> None:
    alice = await register_user("alice@example.com")
    response = await client.get(
        f"{API}/collection/sets/00000000-0000-0000-0000-000000000000", headers=alice.headers
    )
    assert response.status_code == 404
