"""Sammlung zurücksetzen: löscht alles des Nutzers (Positionen, Ordner, Verlauf), nur mit
Bestätigung, fremde Sammlungen bleiben unberührt."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, CollectionEvent
from tests.conftest import Account, RegisterUser

API = "/api/v1"


async def _cards(factory: async_sessionmaker[AsyncSession]) -> list[Card]:
    async with factory() as session:
        card_set = CardSet(external_id="sv1", language="de", name="Karmesin & Purpur")
        session.add(card_set)
        await session.flush()
        cards = [
            Card(
                external_id=f"sv1-{n}",
                language="de",
                set_id=card_set.id,
                number=str(n),
                number_norm=str(n),
                name=f"Karte {n}",
            )
            for n in (1, 2)
        ]
        session.add_all(cards)
        await session.commit()
        return cards


async def _fill(client: AsyncClient, user: Account, cards: list[Card]) -> None:
    folder = await client.post(f"{API}/folders", json={"name": "Binder"}, headers=user.headers)
    assert folder.status_code == 201, folder.text
    for card, folder_id in ((cards[0], None), (cards[1], folder.json()["id"])):
        response = await client.post(
            f"{API}/collection/items",
            json={"card_id": str(card.id), "folder_id": folder_id},
            headers=user.headers,
        )
        assert response.status_code == 201, response.text
    wish = await client.post(
        f"{API}/wishlist", json={"card_id": str(cards[1].id)}, headers=user.headers
    )
    assert wish.status_code == 201, wish.text


async def test_reset_deletes_everything_of_the_user_only(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    cards = await _cards(session_factory)
    await _fill(client, alice, cards)
    await _fill(client, bob, cards)

    wrong = await client.post(
        f"{API}/collection/reset", json={"confirm": "ja"}, headers=alice.headers
    )
    assert wrong.status_code == 422  # ohne „LÖSCHEN“ passiert nichts

    reset = await client.post(
        f"{API}/collection/reset", json={"confirm": "LÖSCHEN"}, headers=alice.headers
    )
    assert reset.status_code == 200, reset.text
    assert reset.json() == {"items": 2, "folders": 2, "wishlist": 0}

    folders = (await client.get(f"{API}/folders", headers=alice.headers)).json()
    assert [f["name"] for f in folders] == ["Sammlung"]  # wieder nur der Standardordner
    items = (await client.get(f"{API}/collection/items", headers=alice.headers)).json()
    assert (items["items"] if isinstance(items, dict) else items) == []
    wishlist = (await client.get(f"{API}/wishlist", headers=alice.headers)).json()
    assert len(wishlist) == 1  # Merkliste bleibt ohne Haken
    async with session_factory() as session:
        events = await session.scalar(
            select(func.count())
            .select_from(CollectionEvent)
            .where(CollectionEvent.user_id == alice.user_id)
        )
    assert events == 0

    bob_items = (await client.get(f"{API}/collection/items", headers=bob.headers)).json()
    assert len(bob_items["items"] if isinstance(bob_items, dict) else bob_items) == 2

    with_wishlist = await client.post(
        f"{API}/collection/reset",
        json={"confirm": "LÖSCHEN", "include_wishlist": True},
        headers=alice.headers,
    )
    assert with_wishlist.json()["wishlist"] == 1
    assert (await client.get(f"{API}/wishlist", headers=alice.headers)).json() == []
