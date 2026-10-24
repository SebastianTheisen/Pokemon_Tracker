"""Showcase (freigegebene Ordner) und Tausch-Rechner."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card
from tests.conftest import Account, RegisterUser
from tests.pricing_helpers import FakeProvider, cardmarket, make_card

API = "/api/v1"


async def _add(client: AsyncClient, user: Account, **body: Any) -> dict[str, Any]:
    response = await client.post(f"{API}/collection/items", json=body, headers=user.headers)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def _share(client: AsyncClient, user: Account, name: str) -> str:
    folder = (await client.post(f"{API}/folders", json={"name": name}, headers=user.headers)).json()
    shared = await client.patch(
        f"{API}/folders/{folder['id']}", json={"shared": True}, headers=user.headers
    )
    assert shared.json()["shared"] is True
    folder_id: str = folder["id"]
    return folder_id


async def _cards(factory: async_sessionmaker[AsyncSession]) -> tuple[Card, Card]:
    return (
        await make_card(factory),
        await make_card(factory, external_id="S12-110", name="Lugia V", number="110"),
    )


async def test_showcase_shows_only_shared_folders_without_private_data(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    nachtara, lugia = await _cards(session_factory)
    price_provider.quotes = [cardmarket("trend", "100")]
    trade_binder = await _share(client, alice, "Tauschordner")
    shown = await _add(
        client,
        alice,
        card_id=str(nachtara.id),
        folder_id=trade_binder,
        quantity=2,
        purchase_price="40",
        note="geheim",
        custom_price="120",
    )
    hidden = await _add(client, alice, card_id=str(lugia.id))  # Standardordner: privat

    friends = (await client.get(f"{API}/friends", headers=bob.headers)).json()
    assert [(f["display_name"], f["folders"], f["items"]) for f in friends] == [
        (friends[0]["display_name"], 1, 2)
    ]
    assert friends[0]["user_id"] == str(alice.user_id)
    assert (await client.get(f"{API}/friends", headers=alice.headers)).json() == []  # nicht sich

    showcase = (await client.get(f"{API}/friends/{alice.user_id}", headers=bob.headers)).json()
    assert [f["name"] for f in showcase["folders"]] == ["Tauschordner"]
    assert [i["id"] for i in showcase["items"]] == [shown["id"]]
    item = showcase["items"][0]
    assert (item["purchase_price"], item["note"], item["custom_price"], item["value_at_add"]) == (
        None,
        None,
        None,
        None,
    )
    assert (item["value"]["profit"], item["value"]["cost"], item["value"]["change"]) == (
        None,
        None,
        None,
    )
    assert item["value"]["total_value"] == "240.00"  # Wert wie beim Besitzer (Eigenpreis 120)
    assert hidden["id"] not in str(showcase)

    private_folder = (await client.get(f"{API}/folders", headers=alice.headers)).json()[0]["id"]
    blocked = await client.get(
        f"{API}/friends/{alice.user_id}",
        params={"folder_id": private_folder},
        headers=bob.headers,
    )
    assert blocked.status_code == 404
    nothing_shared = await client.get(f"{API}/friends/{bob.user_id}", headers=alice.headers)
    assert nothing_shared.status_code == 404

    # Freigabe zurücknehmen → sofort unsichtbar
    await client.patch(
        f"{API}/folders/{trade_binder}", json={"shared": False}, headers=alice.headers
    )
    assert (await client.get(f"{API}/friends", headers=bob.headers)).json() == []


async def test_trade_evaluate_save_and_list(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    nachtara, lugia = await _cards(session_factory)
    price_provider.quotes = [cardmarket("trend", "100")]
    mine = await _add(client, alice, card_id=str(nachtara.id), condition="LP")  # 55 €
    binder = await _share(client, bob, "Tausch")
    theirs = await _add(client, bob, card_id=str(lugia.id), folder_id=binder, purchase_price="1")
    bob_private = await _add(client, bob, card_id=str(lugia.id))

    body = {
        "lines": [
            {"side": "give", "item_id": mine["id"]},
            {"side": "get", "item_id": theirs["id"]},  # aus Bobs Showcase: 100 €
            {"side": "get", "card_id": str(nachtara.id), "variant": "normal", "quantity": 2},
        ]
    }
    value = (await client.post(f"{API}/trades/evaluate", json=body, headers=alice.headers)).json()
    assert [(line["side"], line["unit_value"], line["total"]) for line in value["lines"]] == [
        ("give", "55.00", "55.00"),
        ("get", "100.00", "100.00"),
        ("get", "100.00", "200.00"),
    ]
    assert (value["give_value"], value["get_value"], value["difference"]) == (
        "55.00",
        "300.00",
        "245.00",
    )
    assert value["lines"][0]["label"] == "Nachtara VMAX (Drachenwandel 215) · LP"

    private = await client.post(
        f"{API}/trades/evaluate",
        json={"lines": [{"side": "get", "item_id": bob_private["id"]}]},
        headers=alice.headers,
    )
    assert private.status_code == 404  # nicht freigegeben

    saved = await client.post(
        f"{API}/trades", json={**body, "partner": "Bob", "note": "Börse"}, headers=alice.headers
    )
    assert saved.status_code == 201, saved.text
    trade = saved.json()
    assert (trade["partner"], trade["give_value"], trade["get_value"]) == ("Bob", "55.00", "300.00")

    listed = (await client.get(f"{API}/trades", headers=alice.headers)).json()
    assert [t["id"] for t in listed] == [trade["id"]]
    assert listed[0]["now"]["difference"] == "245.00"
    assert (await client.get(f"{API}/trades", headers=bob.headers)).json() == []

    foreign = await client.delete(f"{API}/trades/{trade['id']}", headers=bob.headers)
    assert foreign.status_code == 404
    gone = await client.delete(f"{API}/trades/{trade['id']}", headers=alice.headers)
    assert gone.status_code == 204


async def test_trade_line_needs_exactly_one_source(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    nachtara, _ = await _cards(session_factory)
    both = await client.post(
        f"{API}/trades/evaluate",
        json={
            "lines": [{"side": "get", "card_id": str(nachtara.id), "product_id": str(nachtara.id)}]
        },
        headers=alice.headers,
    )
    assert both.status_code == 422
    empty = await client.post(f"{API}/trades", json={"lines": []}, headers=alice.headers)
    assert empty.status_code == 400
