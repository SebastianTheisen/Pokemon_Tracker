"""Sammlung über die API – inkl. Abnahmetest mit von Hand berechneten Werten.

Abnahme Phase 3 (Plan): „Werte, Aufteilung und Kurve stimmen mit manuell berechneten
Testdaten überein.“
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import collection as collection_api
from app.core.config import Settings
from app.models import AuditLog, Card, FolderSnapshot, PortfolioSnapshot
from app.services.price_health import SourceHealth
from app.services.pricing import PriceService, tracked_card_ids
from app.worker import refresh_tracked_prices
from tests.conftest import Account, RegisterUser
from tests.pricing_helpers import UPDATED, FakeProvider, cardmarket, make_card

API = "/api/v1"


async def _product(client: AsyncClient, user: Account, kind: str, name: str) -> str:
    response = await client.post(
        f"{API}/products",
        json={"kind": kind, "language": "de", "name": name},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    product_id: str = response.json()["id"]
    return product_id


async def _add(client: AsyncClient, user: Account, **body: Any) -> dict[str, Any]:
    response = await client.post(f"{API}/collection/items", json=body, headers=user.headers)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


@pytest.fixture
async def cards(session_factory: async_sessionmaker[AsyncSession]) -> tuple[Card, Card]:
    card_a = await make_card(session_factory)  # Nachtara VMAX, eigenes Set
    card_b = await make_card(session_factory, external_id="S12-110", name="ルギアV", number="110")
    return card_a, card_b


# ----------------------------------------------------------- Abnahmetest


async def test_values_split_and_curve_match_hand_calculation(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    alice = await register_user("alice@example.com")
    card_a, card_b = cards
    price_provider.quotes = [cardmarket("trend", "100")]  # NM-Basis 100 € (für jede Karte)
    display = await _product(client, alice, "display", "Drachenwandel Display")
    booster = await _product(client, alice, "booster", "Drachenwandel Booster")

    await _add(client, alice, card_id=str(card_a.id), condition="NM", quantity=2)  # 2 × 100
    await _add(client, alice, card_id=str(card_a.id), condition="LP")  # 100 × 0,55 = 55
    await _add(
        client, alice, card_id=str(card_b.id), grading_company="PSA", grade="10", custom_price="500"
    )
    await _add(
        client, alice, card_id=str(card_b.id), grading_company="CGC", grade="9.5"
    )  # ohne Wert
    await _add(client, alice, product_id=display, quantity=2, custom_price="150")  # 2 × 150
    await _add(client, alice, product_id=booster)  # ohne Wert

    summary = (await client.get(f"{API}/collection/summary", headers=alice.headers)).json()

    # Von Hand: 200 + 55 + 500 + 300 = 1055; geschätzt: 200 + 55 = 255
    assert summary["total_value"] == "1055.00"
    assert summary["estimated_value"] == "255.00"
    assert summary["raw"] == {"value": "255.00", "positions": 2, "items": 3}
    assert summary["graded"] == {"value": "500.00", "positions": 2, "items": 2}
    assert summary["sealed"] == {"value": "300.00", "positions": 2, "items": 3}
    assert (summary["positions"], summary["items"], summary["cards"], summary["sets"]) == (
        6,
        8,
        5,
        2,
    )
    assert summary["unvalued_positions"] == 2
    assert summary["change_since_added"] == "0.00"
    assert summary["top_item"]["value"]["unit_value"] == "500.00"
    assert summary["biggest_gain"] is None

    # Preis steigt auf 120 €: tägliche Runde holt neue Preise und speichert den Tageswert.
    price_provider.quotes = [cardmarket("trend", "120", updated=UPDATED + timedelta(days=1))]
    health = SourceHealth(threshold=3, pause=timedelta(minutes=60))
    round_summary = await refresh_tracked_prices(
        session_factory, settings, [price_provider], health
    )
    assert round_summary.snapshots == 1

    summary = (await client.get(f"{API}/collection/summary", headers=alice.headers)).json()
    # Von Hand: NM 2 × 120 = 240, LP 120 × 0,55 = 66 → roh 306; gesamt 306 + 500 + 300 = 1106
    assert summary["total_value"] == "1106.00"
    assert summary["raw"]["value"] == "306.00"
    # Veränderung seit Hinzufügen: 2 × (120 − 100) + (66 − 55) = 51 – Zukäufe zählen nicht
    assert summary["change_since_added"] == "51.00"
    assert summary["biggest_gain"]["value"]["change"] == "40.00"

    history = (await client.get(f"{API}/collection/history", headers=alice.headers)).json()
    assert history["points"][-1]["total_value"] == "1106.00"
    assert history["points"][-1]["is_live"] is True
    assert sum(m["delta_quantity"] for m in history["markers"]) == 8  # 2+1+1+1+2+1 Stück

    async with session_factory() as session:
        snapshot = await session.scalar(select(PortfolioSnapshot))
    assert snapshot is not None
    assert (snapshot.total_value, snapshot.raw_value) == (Decimal("1106.00"), Decimal("306.00"))
    assert (snapshot.graded_value, snapshot.sealed_value) == (Decimal("500.00"), Decimal("300.00"))


async def test_buying_more_does_not_count_as_gain(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "100")]
    item = await _add(client, alice, card_id=str(cards[0].id))

    await client.patch(
        f"{API}/collection/items/{item['id']}", json={"quantity": 5}, headers=alice.headers
    )

    summary = (await client.get(f"{API}/collection/summary", headers=alice.headers)).json()
    assert summary["total_value"] == "500.00"
    assert summary["change_since_added"] == "0.00"


# --------------------------------------------------------- Positionen & Ordner


async def test_profit_against_purchase_price_per_item_folder_and_total(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
) -> None:
    """Gewinn = Wert − Kaufpreis × Menge; nur Positionen mit Kaufpreis und Wert zählen."""
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "100")]  # NM 100 € je Karte
    binder = (
        await client.post(f"{API}/folders", json={"name": "Binder"}, headers=alice.headers)
    ).json()
    winner = await _add(
        client, alice, card_id=str(cards[0].id), quantity=2, purchase_price="60"
    )  # 200 − 120 = +80
    loser = await _add(
        client, alice, card_id=str(cards[1].id), purchase_price="130", folder_id=binder["id"]
    )  # 100 − 130 = −30
    await _add(client, alice, card_id=str(cards[1].id))  # ohne Kaufpreis
    tin = await _product(client, alice, "tin", "Tin")
    await _add(client, alice, product_id=tin, purchase_price="25")  # Kaufpreis, aber kein Wert

    assert winner["value"]["cost"] == "120.00"
    assert winner["value"]["profit"] == "80.00"
    assert loser["value"]["profit"] == "-30.00"

    summary = (await client.get(f"{API}/dashboard", headers=alice.headers)).json()
    assert summary["invested"] == "275.00"  # 120 + 130 + 25
    assert summary["profit_cost"] == "250.00"  # ohne Tin (kein Wert)
    assert summary["profit"] == "50.00"
    assert summary["profit_percent"] == "20.0"
    assert summary["profit_positions"] == 2
    assert summary["best_profit"]["id"] == winner["id"]
    assert summary["worst_profit"]["id"] == loser["id"]

    in_binder = (
        await client.get(
            f"{API}/dashboard", params={"folder_id": binder["id"]}, headers=alice.headers
        )
    ).json()
    assert (in_binder["total_value"], in_binder["profit"]) == ("100.00", "-30.00")
    assert in_binder["best_profit"] is None

    folders = (await client.get(f"{API}/collection/folders", headers=alice.headers)).json()
    assert [
        (f["folder"]["name"], f["total_value"], f["invested"], f["profit"], f["profit_percent"])
        for f in folders
    ] == [
        ("Sammlung", "300.00", "145.00", "80.00", "66.7"),
        ("Binder", "100.00", "130.00", "-30.00", "-23.1"),
    ]

    by_profit = (
        await client.get(
            f"{API}/collection/items", params={"sort": "profit_desc"}, headers=alice.headers
        )
    ).json()
    assert [i["value"]["profit"] for i in by_profit["items"]] == ["80.00", "-30.00", None, None]
    worst_first = (
        await client.get(
            f"{API}/collection/items", params={"sort": "profit_asc"}, headers=alice.headers
        )
    ).json()
    assert [i["value"]["profit"] for i in worst_first["items"]][:2] == ["-30.00", "80.00"]


async def test_folder_summary_of_foreign_folder_is_not_found(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    folder_id = (await client.get(f"{API}/folders", headers=alice.headers)).json()[0]["id"]
    response = await client.get(
        f"{API}/dashboard", params={"folder_id": folder_id}, headers=bob.headers
    )
    assert response.status_code == 404


async def test_item_crud_and_custom_price(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "100")]
    item = await _add(
        client, alice, card_id=str(cards[0].id), purchase_price="80", note="  Tausch mit Max  "
    )
    assert item["condition"] == "NM"
    assert item["note"] == "Tausch mit Max"
    assert item["value_at_add"] == "100.00"
    assert item["value"]["kind"] == "estimated"

    changed = await client.patch(
        f"{API}/collection/items/{item['id']}",
        json={"custom_price": "250", "condition": "EX"},
        headers=alice.headers,
    )
    assert changed.json()["value"] == {
        "kind": "manual", "unit_value": "250.00", "total_value": "250.00",
        "source": "manual", "basis": None, "change": "150.00",
        "cost": "80.00", "profit": "170.00",
    }  # fmt: skip

    cleared = await client.patch(
        f"{API}/collection/items/{item['id']}", json={"custom_price": None}, headers=alice.headers
    )
    assert cleared.json()["value"]["unit_value"] == "85.00"  # EX = 100 × 0,85

    assert (
        await client.delete(f"{API}/collection/items/{item['id']}", headers=alice.headers)
    ).status_code == 204
    assert (
        await client.get(f"{API}/collection/items/{item['id']}", headers=alice.headers)
    ).status_code == 404


async def test_item_validation(
    client: AsyncClient, register_user: RegisterUser, cards: tuple[Card, Card]
) -> None:
    alice = await register_user("alice@example.com")
    product = await _product(client, alice, "booster", "Booster")
    card_id = str(cards[0].id)
    cases: list[tuple[dict[str, Any], int]] = [
        ({"card_id": card_id, "product_id": product}, 400),
        ({}, 400),
        ({"product_id": product, "grading_company": "PSA", "grade": "10"}, 400),
        ({"card_id": card_id, "grading_company": "PSA"}, 400),
        ({"card_id": card_id, "condition": "XX"}, 422),
        ({"card_id": card_id, "quantity": 0}, 422),
        ({"card_id": card_id, "variant": "gold"}, 422),
        ({"card_id": card_id, "purchase_price": "-1"}, 422),
        ({"card_id": card_id, "grading_company": "PSA", "grade": "elf"}, 422),
    ]
    for body, expected in cases:
        response = await client.post(f"{API}/collection/items", json=body, headers=alice.headers)
        assert response.status_code == expected, (body, response.text)


async def test_bulk_move_copy_delete(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "100")]
    binder = (
        await client.post(f"{API}/folders", json={"name": "Binder"}, headers=alice.headers)
    ).json()
    first = await _add(client, alice, card_id=str(cards[0].id), purchase_price="80", note="A")
    second = await _add(client, alice, card_id=str(cards[1].id), quantity=2)
    third = await _add(client, alice, card_id=str(cards[1].id))

    async def bulk(**body: Any) -> Any:
        return await client.post(f"{API}/collection/items/bulk", json=body, headers=alice.headers)

    moved = await bulk(item_ids=[first["id"], second["id"]], action="move", folder_id=binder["id"])
    assert moved.json() == {"count": 2}
    in_binder = (
        await client.get(
            f"{API}/collection/items", params={"folder_id": binder["id"]}, headers=alice.headers
        )
    ).json()
    assert {i["id"] for i in in_binder["items"]} == {first["id"], second["id"]}

    default_id = (await client.get(f"{API}/folders", headers=alice.headers)).json()[0]["id"]
    copied = await bulk(item_ids=[first["id"]], action="copy", folder_id=default_id)
    assert copied.json() == {"count": 1}
    in_default = (
        await client.get(
            f"{API}/collection/items", params={"folder_id": default_id}, headers=alice.headers
        )
    ).json()["items"]
    copy = next(i for i in in_default if i["id"] != third["id"])
    assert (copy["card"]["id"], copy["purchase_price"], copy["note"]) == (
        str(cards[0].id),
        "80.00",
        "A",
    )
    summary = (await client.get(f"{API}/dashboard", headers=alice.headers)).json()
    assert summary["items"] == 5  # 1 + 2 + 1 + Kopie 1

    assert (await bulk(item_ids=[first["id"]], action="move")).status_code == 400
    deleted = await bulk(item_ids=[second["id"], third["id"]], action="delete")
    assert deleted.json() == {"count": 2}
    summary = (await client.get(f"{API}/dashboard", headers=alice.headers)).json()
    assert summary["items"] == 2


async def test_bulk_rejects_foreign_items_completely(
    client: AsyncClient, register_user: RegisterUser, cards: tuple[Card, Card]
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    mine = await _add(client, bob, card_id=str(cards[0].id))
    foreign = await _add(client, alice, card_id=str(cards[0].id))
    response = await client.post(
        f"{API}/collection/items/bulk",
        json={"item_ids": [mine["id"], foreign["id"]], "action": "delete"},
        headers=bob.headers,
    )
    assert response.status_code == 404
    still = await client.get(f"{API}/collection/items/{mine['id']}", headers=bob.headers)
    assert still.status_code == 200  # nichts gelöscht


async def test_folder_curve_from_daily_snapshots(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "100")]
    binder = (
        await client.post(f"{API}/folders", json={"name": "Binder"}, headers=alice.headers)
    ).json()
    await _add(client, alice, card_id=str(cards[0].id))
    await _add(client, alice, card_id=str(cards[1].id), folder_id=binder["id"], purchase_price="70")

    health = SourceHealth(threshold=3, pause=timedelta(minutes=60))
    await refresh_tracked_prices(session_factory, settings, [price_provider], health)
    async with session_factory() as session:
        rows = (await session.scalars(select(FolderSnapshot))).all()
        assert sorted((r.total_value, r.invested, r.item_count) for r in rows) == [
            (Decimal("100.00"), Decimal("0.00"), 1),
            (Decimal("100.00"), Decimal("70.00"), 1),
        ]
        yesterday = rows[0].day - timedelta(days=1)
        session.add(
            FolderSnapshot(
                folder_id=binder["id"],
                day=yesterday,
                total_value=Decimal("90.00"),
                estimated_value=Decimal("90.00"),
                invested=Decimal("70.00"),
                item_count=1,
            )
        )
        await session.commit()

    history = (
        await client.get(
            f"{API}/collection/history", params={"folder_id": binder["id"]}, headers=alice.headers
        )
    ).json()
    assert [(p["total_value"], p["is_live"]) for p in history["points"]] == [
        ("90.00", False),
        ("100.00", True),
    ]
    assert history["markers"] == []


async def test_filter_by_condition_value_range_and_purchase(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "100")]
    near_mint = await _add(client, alice, card_id=str(cards[0].id), purchase_price="50")  # 100
    played = await _add(client, alice, card_id=str(cards[0].id), condition="LP")  # 55
    slab = await _add(
        client,
        alice,
        card_id=str(cards[1].id),
        grading_company="PSA",
        grade="10",
        custom_price="500",
    )
    await _add(client, alice, product_id=await _product(client, alice, "tin", "Tin"))  # ohne Wert

    async def ids(**params: Any) -> list[str]:
        page = (
            await client.get(
                f"{API}/collection/items",
                params={"sort": "value_desc", **params},
                headers=alice.headers,
            )
        ).json()
        return [i["id"] for i in page["items"]]

    assert await ids(condition="LP") == [played["id"]]
    assert await ids(min_value="60") == [slab["id"], near_mint["id"]]
    assert await ids(max_value="100") == [near_mint["id"], played["id"]]
    assert await ids(min_value="56", max_value="499.99") == [near_mint["id"]]
    assert await ids(with_purchase="true") == [near_mint["id"]]
    assert len(await ids(with_purchase="false")) == 3
    bad = await client.get(
        f"{API}/collection/items", params={"condition": "XX"}, headers=alice.headers
    )
    assert bad.status_code == 422


async def test_folders_lifecycle(
    client: AsyncClient, register_user: RegisterUser, cards: tuple[Card, Card]
) -> None:
    alice = await register_user("alice@example.com")
    folders = (await client.get(f"{API}/folders", headers=alice.headers)).json()
    assert [f["name"] for f in folders] == ["Sammlung"]
    default_id = folders[0]["id"]

    second = (
        await client.post(f"{API}/folders", json={"name": "Sammlung 2"}, headers=alice.headers)
    ).json()
    duplicate = await client.post(
        f"{API}/folders", json={"name": "sammlung 2"}, headers=alice.headers
    )
    assert duplicate.status_code == 409
    item = await _add(client, alice, card_id=str(cards[0].id), folder_id=second["id"])

    not_empty = await client.delete(f"{API}/folders/{second['id']}", headers=alice.headers)
    assert not_empty.json()["error"]["code"] == "folder_not_empty"
    moved = await client.delete(
        f"{API}/folders/{second['id']}", params={"move_to": default_id}, headers=alice.headers
    )
    assert moved.status_code == 204
    item_now = (
        await client.get(f"{API}/collection/items/{item['id']}", headers=alice.headers)
    ).json()
    assert item_now["folder_id"] == default_id

    last = await client.delete(f"{API}/folders/{default_id}", headers=alice.headers)
    assert last.status_code == 400

    renamed = await client.patch(
        f"{API}/folders/{default_id}", json={"name": "Binder"}, headers=alice.headers
    )
    assert renamed.json()["name"] == "Binder"


async def test_list_filter_sort_sets_and_export(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "10.50")]
    await _add(client, alice, card_id=str(cards[0].id), quantity=3)
    await _add(client, alice, card_id=str(cards[1].id), custom_price="99.90")
    await _add(client, alice, product_id=await _product(client, alice, "tin", "Tin"))

    by_value = (
        await client.get(
            f"{API}/collection/items", params={"sort": "value_desc"}, headers=alice.headers
        )
    ).json()
    assert [i["value"]["total_value"] for i in by_value["items"]] == ["99.90", "31.50", None]
    sealed = (
        await client.get(
            f"{API}/collection/items", params={"kind": "sealed"}, headers=alice.headers
        )
    ).json()
    assert sealed["total"] == 1
    found = (
        await client.get(f"{API}/collection/items", params={"q": "nachtara"}, headers=alice.headers)
    ).json()
    assert [i["card"]["name"] for i in found["items"]] == ["Nachtara VMAX"]

    sets = (await client.get(f"{API}/collection/sets", headers=alice.headers)).json()
    assert [(s["card_set"]["name"], s["owned_cards"], s["value"]) for s in sets] == [
        ("Drachenwandel", 1, "99.90"),
        ("Drachenwandel", 1, "31.50"),
    ]

    export = await client.get(f"{API}/collection/export.csv", headers=alice.headers)
    assert export.headers["content-type"] == "text/csv; charset=utf-8"
    assert export.text.startswith("﻿Ordner;Art;Name;")
    assert (
        "Sammlung;Karte;Nachtara VMAX;Drachenwandel;215;de;normal;NM;;;3;;;10,50;31,50;;Schätzung;"
        in export.text
    )
    assert ";Versiegelt;Tin;" in export.text


# ----------------------------------------------------------------- Merkliste


async def test_wishlist(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
) -> None:
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "100")]
    await client.get(f"{API}/cards/{cards[0].id}/prices", headers=alice.headers)  # Preis vorhanden

    first = await client.post(
        f"{API}/wishlist", json={"card_id": str(cards[0].id)}, headers=alice.headers
    )
    again = await client.post(
        f"{API}/wishlist", json={"card_id": str(cards[0].id)}, headers=alice.headers
    )
    assert first.json()["id"] == again.json()["id"]  # doppelt merken → derselbe Eintrag

    entries = (await client.get(f"{API}/wishlist", headers=alice.headers)).json()
    assert [(e["card"]["name"], e["nm_value"], e["nm_value_kind"]) for e in entries] == [
        ("Nachtara VMAX", "100.00", "estimated")
    ]
    removed = await client.delete(f"{API}/wishlist/{entries[0]['id']}", headers=alice.headers)
    assert removed.status_code == 204
    assert (await client.get(f"{API}/wishlist", headers=alice.headers)).json() == []


# ------------------------------------------------- Mandantentrennung & Admin


async def test_users_cannot_touch_each_others_collections(
    client: AsyncClient, register_user: RegisterUser, cards: tuple[Card, Card]
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    item = await _add(client, alice, card_id=str(cards[0].id))
    alice_folder = (await client.get(f"{API}/folders", headers=alice.headers)).json()[0]["id"]
    wish = (
        await client.post(
            f"{API}/wishlist", json={"card_id": str(cards[0].id)}, headers=alice.headers
        )
    ).json()

    attacks = [
        ("GET", f"/collection/items/{item['id']}", None),
        ("PATCH", f"/collection/items/{item['id']}", {"quantity": 99}),
        ("DELETE", f"/collection/items/{item['id']}", None),
        ("PATCH", f"/folders/{alice_folder}", {"name": "gehackt"}),
        ("DELETE", f"/folders/{alice_folder}", None),
        ("POST", "/collection/items", {"card_id": str(cards[0].id), "folder_id": alice_folder}),
        ("DELETE", f"/wishlist/{wish['id']}", None),
    ]
    for method, path, body in attacks:
        response = await client.request(method, API + path, json=body, headers=bob.headers)
        assert response.status_code == 404, (method, path, response.status_code)

    assert (await client.get(f"{API}/collection/items", headers=bob.headers)).json()["total"] == 0
    assert (await client.get(f"{API}/wishlist", headers=bob.headers)).json() == []
    still = (await client.get(f"{API}/collection/items/{item['id']}", headers=alice.headers)).json()
    assert still["quantity"] == 1


@pytest.mark.parametrize(
    "path",
    ["/folders", "/collection/items", "/collection/summary", "/collection/sets",
     "/collection/history", "/collection/export.csv", "/wishlist", "/dashboard", "/products"],
)  # fmt: skip
async def test_collection_endpoints_require_login(client: AsyncClient, path: str) -> None:
    assert (await client.get(API + path)).status_code == 401


async def test_admin_can_read_but_users_cannot(
    client: AsyncClient,
    admin: Account,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    await _add(client, alice, card_id=str(cards[0].id), custom_price="42")

    summary = await client.get(
        f"{API}/admin/users/{alice.user_id}/collection/summary", headers=admin.headers
    )
    items = await client.get(
        f"{API}/admin/users/{alice.user_id}/collection/items", headers=admin.headers
    )
    assert summary.json()["total_value"] == "42.00"
    assert items.json()["total"] == 1

    forbidden = await client.get(
        f"{API}/admin/users/{alice.user_id}/collection/items", headers=bob.headers
    )
    assert forbidden.status_code == 403
    async with session_factory() as session:
        views = (
            await session.scalars(
                select(AuditLog).where(AuditLog.action == "admin.collection_viewed")
            )
        ).all()
    assert {(v.actor_id, v.target_user_id, v.details["view"]) for v in views} == {
        (admin.user_id, alice.user_id, "summary"),
        (admin.user_id, alice.user_id, "items"),
    }


async def test_daily_refresh_tracks_collection_and_wishlist_cards(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    alice = await register_user("alice@example.com")
    raw = await make_card(session_factory, external_id="raw-1", number="1")
    graded = await make_card(session_factory, external_id="graded-2", number="2")
    wished = await make_card(session_factory, external_id="wish-3", number="3")
    await _add(client, alice, card_id=str(raw.id))
    await _add(client, alice, card_id=str(graded.id), grading_company="PSA", grade="9")
    await client.post(f"{API}/wishlist", json={"card_id": str(wished.id)}, headers=alice.headers)

    async with session_factory() as session:
        tracked = set(await tracked_card_ids(session, settings, datetime.now(UTC)))

    # Slabs zählen mit: ihre Notenpreise (PriceCharting) brauchen die tägliche Runde.
    assert {raw.id, graded.id, wished.id} <= tracked


async def test_patch_rejects_nulls_and_grade_on_raw_cards(
    client: AsyncClient, register_user: RegisterUser, cards: tuple[Card, Card]
) -> None:
    alice = await register_user("alice@example.com")
    raw = await _add(client, alice, card_id=str(cards[0].id))
    graded = await _add(client, alice, card_id=str(cards[1].id), grading_company="PSA", grade="9")

    for body in ({"quantity": None}, {"variant": None}, {"condition": None}, {"grade": "10"}):
        response = await client.patch(
            f"{API}/collection/items/{raw['id']}", json=body, headers=alice.headers
        )
        assert response.status_code == 400, body
    no_grade = await client.patch(
        f"{API}/collection/items/{graded['id']}", json={"grade": None}, headers=alice.headers
    )
    assert no_grade.status_code == 400
    regraded = await client.patch(
        f"{API}/collection/items/{graded['id']}", json={"grade": "9.5"}, headers=alice.headers
    )
    assert regraded.json()["grade"] == "9.5"


async def test_switch_raw_card_to_slab_and_back(
    client: AsyncClient, register_user: RegisterUser, cards: tuple[Card, Card]
) -> None:
    alice = await register_user("alice@example.com")
    item = await _add(client, alice, card_id=str(cards[0].id))
    url = f"{API}/collection/items/{item['id']}"

    missing_grade = await client.patch(url, json={"grading_company": "BGS"}, headers=alice.headers)
    assert missing_grade.status_code == 400

    slab = await client.patch(
        url, json={"grading_company": "BGS", "grade": "10 BL"}, headers=alice.headers
    )
    assert slab.status_code == 200, slab.text
    body = slab.json()
    assert (body["kind"], body["grading_company"], body["grade"], body["condition"]) == (
        "graded",
        "BGS",
        "10 BL",
        None,
    )
    tag = await client.patch(url, json={"grading_company": "TAG"}, headers=alice.headers)
    assert tag.json()["grading_company"] == "TAG"  # Note bleibt

    raw = await client.patch(
        url, json={"grading_company": None, "condition": "EX"}, headers=alice.headers
    )
    assert (raw.json()["kind"], raw.json()["grade"], raw.json()["condition"]) == (
        "raw",
        None,
        "EX",
    )


async def test_csv_export_neutralizes_formulas(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    alice = await register_user("alice@example.com")
    evil = (
        await client.post(
            f"{API}/products",
            json={"kind": "other", "language": "de", "name": '=HYPERLINK("http://x","klick")'},
            headers=alice.headers,
        )
    ).json()
    await _add(client, alice, product_id=evil["id"], note="+49 Notiz")

    export = (await client.get(f"{API}/collection/export.csv", headers=alice.headers)).text
    header, row = list(csv.reader(io.StringIO(export.lstrip("\ufeff")), delimiter=";"))

    assert row[header.index("Name")] == '\'=HYPERLINK("http://x","klick")'
    assert row[header.index("Notiz")] == "'+49 Notiz"


async def test_owned_cards_by_folder_and_version(
    client: AsyncClient, register_user: RegisterUser, cards: tuple[Card, Card]
) -> None:
    """„Schon in deiner Sammlung“: Anzahl je Ordner und Fassung, nur eigene Positionen."""
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    binder = (
        await client.post(f"{API}/folders", json={"name": "Binder"}, headers=alice.headers)
    ).json()
    card_a, card_b = cards
    await _add(client, alice, card_id=str(card_a.id), quantity=2)
    await _add(client, alice, card_id=str(card_a.id))  # gleicher Ordner und Fassung → 3
    await _add(client, alice, card_id=str(card_a.id), variant="reverse", folder_id=binder["id"])
    await _add(client, alice, card_id=str(card_a.id), grading_company="PSA", grade="10")
    await _add(client, bob, card_id=str(card_b.id))

    owned = (
        await client.get(
            f"{API}/collection/owned",
            params=[("card_id", str(card_a.id)), ("card_id", str(card_b.id))],
            headers=alice.headers,
        )
    ).json()
    assert {
        (o["folder_name"], o["variant"], o["grading_company"], o["grade"], o["quantity"])
        for o in owned
    } == {
        ("Binder", "reverse", None, None, 1),
        ("Sammlung", "normal", "PSA", "10", 1),
        ("Sammlung", "normal", None, None, 3),
    }
    assert {o["card_id"] for o in owned} == {str(card_a.id)}  # Bobs Karte zählt nicht


async def test_owned_shows_collection_value_and_slab_switch_fetches_grade_prices(
    client: AsyncClient,
    register_user: RegisterUser,
    cards: tuple[Card, Card],
    price_provider: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rohkarte → Slab: der Wert ist der Notenpreis (nicht der Rohpreis), und die Notenpreise
    werden gleich im Hintergrund geholt statt erst in der Tagesrunde."""
    alice = await register_user("alice@example.com")
    price_provider.quotes = [cardmarket("trend", "100")]
    card = cards[0]
    item = await _add(client, alice, card_id=str(card.id))

    async def owned() -> list[dict[str, Any]]:
        response = await client.get(
            f"{API}/collection/owned", params={"card_id": str(card.id)}, headers=alice.headers
        )
        data: list[dict[str, Any]] = response.json()
        return data

    raw = (await owned())[0]
    assert (raw["unit_value"], raw["value_kind"], raw["condition"]) == ("100.00", "estimated", "NM")

    refreshed: list[str] = []
    original = PriceService.refresh

    async def recording_refresh(self: PriceService, target: Card, **kwargs: Any) -> Any:
        refreshed.append(str(target.id))
        return await original(self, target, **kwargs)

    monkeypatch.setattr(collection_api.PriceService, "refresh", recording_refresh)
    switched = await client.patch(
        f"{API}/collection/items/{item['id']}",
        json={"grading_company": "PSA", "grade": "10"},
        headers=alice.headers,
    )
    assert switched.json()["value"]["unit_value"] is None  # kein Rohpreis für den Slab
    assert refreshed == [str(card.id)]  # Notenpreise werden gleich geholt

    slab = (await owned())[0]
    assert (slab["grading_company"], slab["grade"], slab["unit_value"]) == ("PSA", "10", None)
