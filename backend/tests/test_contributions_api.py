"""Eigene Karten und Produkte: anlegen (alle), bearbeiten/löschen (nur Admins)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import Account, RegisterUser
from tests.pricing_helpers import make_card

API = "/api/v1"


async def test_user_creates_missing_card_visible_to_everyone(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    body = {
        "name": "鲤鱼王",
        "number": "165",
        "language": "zh-cn",
        "set_name": "30th Celebration CN",
    }

    created = await client.post(f"{API}/cards", json=body, headers=alice.headers)
    assert created.status_code == 201
    card = created.json()
    assert (card["source"], card["external_id"], card["card_set"]["name"]) == (
        "user",
        None,
        "30th Celebration CN",
    )

    duplicate = await client.post(f"{API}/cards", json=body, headers=bob.headers)
    assert duplicate.status_code == 409

    hits = (
        await client.get(f"{API}/cards/search", params={"q": "鲤鱼王 165"}, headers=bob.headers)
    ).json()
    assert [h["card"]["id"] for h in hits] == [card["id"]]

    # Zweite Karte im selben (eigenen) Set nutzt das vorhandene Set
    second = (
        await client.post(
            f"{API}/cards",
            json={**body, "name": "皮卡丘", "number": "160", "set_name": "30th celebration cn"},
            headers=bob.headers,
        )
    ).json()
    assert second["card_set"]["id"] == card["card_set"]["id"]


async def test_card_in_existing_set_requires_matching_language(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    existing = await make_card(session_factory)  # Set in Deutsch

    wrong = await client.post(
        f"{API}/cards",
        json={"name": "X", "number": "1", "language": "ja", "set_id": str(existing.set_id)},
        headers=alice.headers,
    )
    no_set = await client.post(
        f"{API}/cards", json={"name": "X", "number": "1", "language": "de"}, headers=alice.headers
    )

    assert wrong.status_code == 400
    assert no_set.status_code == 400


async def test_only_admins_edit_or_delete_user_cards(
    client: AsyncClient,
    admin: Account,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    card = (
        await client.post(
            f"{API}/cards",
            json={"name": "Schigy", "number": "007", "language": "ja", "set_name": "Intro Pack"},
            headers=alice.headers,
        )
    ).json()

    assert (
        await client.patch(
            f"{API}/admin/cards/{card['id']}", json={"name": "x"}, headers=alice.headers
        )
    ).status_code == 403
    fixed = await client.patch(
        f"{API}/admin/cards/{card['id']}", json={"name": "Schiggy"}, headers=admin.headers
    )
    assert fixed.json()["name"] == "Schiggy"

    tcgdex_card = await make_card(session_factory)
    protected = await client.patch(
        f"{API}/admin/cards/{tcgdex_card.id}", json={"name": "x"}, headers=admin.headers
    )
    assert protected.status_code == 400

    # In einer Sammlung → nicht löschbar; danach entfernt → löschbar
    item = (
        await client.post(
            f"{API}/collection/items", json={"card_id": card["id"]}, headers=alice.headers
        )
    ).json()
    in_use = await client.delete(f"{API}/admin/cards/{card['id']}", headers=admin.headers)
    assert in_use.status_code == 409
    await client.delete(f"{API}/collection/items/{item['id']}", headers=alice.headers)
    assert (
        await client.delete(f"{API}/admin/cards/{card['id']}", headers=admin.headers)
    ).status_code == 204


async def test_products_create_search_and_admin_delete(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    alice = await register_user("alice@example.com")
    body = {
        "kind": "elite_trainer_box",
        "language": "de",
        "name": "Schwarze Blitze Top-Trainer-Box",
    }

    created = await client.post(f"{API}/products", json=body, headers=alice.headers)
    assert created.status_code == 201
    assert (
        await client.post(f"{API}/products", json=body, headers=alice.headers)
    ).status_code == 409

    found = (
        await client.get(f"{API}/products", params={"q": "blitze"}, headers=alice.headers)
    ).json()
    assert [p["name"] for p in found] == ["Schwarze Blitze Top-Trainer-Box"]
    assert (
        await client.get(
            f"{API}/products", params={"q": "blitze", "language": "en"}, headers=alice.headers
        )
    ).json() == []

    product_id = created.json()["id"]
    assert (
        await client.delete(f"{API}/admin/products/{product_id}", headers=alice.headers)
    ).status_code == 403
    renamed = await client.patch(
        f"{API}/admin/products/{product_id}",
        json={"name": "Schwarze Blitze ETB"},
        headers=admin.headers,
    )
    assert renamed.json()["name"] == "Schwarze Blitze ETB"
    assert (
        await client.delete(f"{API}/admin/products/{product_id}", headers=admin.headers)
    ).status_code == 204


async def test_invalid_product_input(client: AsyncClient, register_user: RegisterUser) -> None:
    alice = await register_user("alice@example.com")

    for body in (
        {"kind": "zauberkiste", "language": "de", "name": "X"},
        {"kind": "booster", "language": "xx", "name": "X"},
        {"kind": "booster", "language": "de", "name": "  "},
        {"kind": "booster", "language": "de", "name": "X", "image_url": "javascript:alert(1)"},
    ):
        response = await client.post(f"{API}/products", json=body, headers=alice.headers)
        assert response.status_code == 422, body
