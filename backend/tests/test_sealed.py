"""Versiegelte Produkte mit Cardmarket-Preisen: Art, Suche, Anlegen aus dem Katalog, Wert."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import CardSet, CmExpansion, Product, ProductKind
from app.services.cardmarket_catalog import run_catalog_import
from app.services.sealed import kind_for, partial_set_queries, translate_query
from tests.conftest import RegisterUser
from tests.test_cardmarket_catalog import CHINESE_GLURAK, catalog_transport

API = "/api/v1"
ETB = 700001
BUNDLE = 700002


@pytest.fixture
async def imported(session_factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    summary = await run_catalog_import(
        session_factory, settings, tcgdex=None, transport=catalog_transport()
    )
    assert summary.error is None


@pytest.mark.parametrize(
    ("category", "name", "kind"),
    [
        (
            "Pokémon Elite Trainer Box",
            "Prismatic Evolutions Elite Trainer Box",
            "elite_trainer_box",
        ),
        ("Pokémon Display", "Surging Sparks Booster Box", "display"),
        ("Pokémon Booster", "Prismatic Evolutions Booster Bundle", "booster_bundle"),
        ("Pokémon Booster", "151 Booster", "booster"),
        ("Pokémon Tin", "Paldean Tin", "tin"),
        ("Pokémon Blister", "Sleeved Booster Blister", "blister"),
        (None, "Charizard ex Premium Collection", "collection_box"),
        (None, "Sammelkarte", "other"),
    ],
)
def test_kind_from_category_or_name(category: str | None, name: str, kind: str) -> None:
    assert kind_for(category, name) == ProductKind(kind)


async def test_sealed_import_keeps_expansions_from_singles(
    session_factory: async_sessionmaker[AsyncSession], imported: None
) -> None:
    async with session_factory() as session:
        # Versiegeltes bildet keine eigene Ausgabe (keine Metakarten).
        assert await session.get(CmExpansion, 6100) is None


async def test_search_create_and_value_in_collection(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    imported: None,
) -> None:
    user = await register_user("max@example.com")

    found = await client.get(
        f"{API}/cardmarket/sealed", params={"q": "prismatic elite"}, headers=user.headers
    )

    assert found.status_code == 200, found.text
    assert found.json() == [
        {
            "cardmarket_product_id": ETB,
            "name": "Prismatic Evolutions Elite Trainer Box",
            "category": "Pokémon Elite Trainer Box",
            "kind": "elite_trainer_box",
            "trend": "95.00",
            "low": "89.00",
            "value": "99.00",  # Median aus 95, 99, 110
            "url": f"https://www.cardmarket.com/de/Pokemon/Products?idProduct={ETB}",
            "image_url": None,
        }
    ]
    created = await client.post(
        f"{API}/products/from-cardmarket",
        json={"cardmarket_product_id": ETB, "language": "de"},
        headers=user.headers,
    )
    again = await client.post(
        f"{API}/products/from-cardmarket",
        json={"cardmarket_product_id": ETB, "language": "de"},
        headers=user.headers,
    )
    english = await client.post(
        f"{API}/products/from-cardmarket",
        json={"cardmarket_product_id": ETB, "language": "en"},
        headers=user.headers,
    )
    assert created.status_code == 200, created.text
    product = created.json()
    assert (product["kind"], product["cardmarket_product_id"]) == ("elite_trainer_box", ETB)
    assert again.json()["id"] == product["id"]
    assert english.json()["id"] != product["id"]

    item = await client.post(
        f"{API}/collection/items",
        json={"product_id": product["id"], "quantity": 2},
        headers=user.headers,
    )
    assert item.status_code == 201, item.text
    value = item.json()["value"]
    assert (value["kind"], value["unit_value"], value["total_value"], value["source"]) == (
        "external",
        "99.00",
        "198.00",
        "cardmarket",
    )
    assert item.json()["value_at_add"] == "99.00"


async def test_link_existing_product_and_reject_singles(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    imported: None,
) -> None:
    user = await register_user("max@example.com")
    old = await client.post(
        f"{API}/products",
        json={
            "kind": "booster_bundle",
            "language": "de",
            "name": "Prismatic Evolutions Booster Bundle",
        },
        headers=user.headers,
    )
    unpriced = await client.post(
        f"{API}/collection/items",
        json={"product_id": old.json()["id"], "quantity": 1},
        headers=user.headers,
    )

    linked = await client.post(
        f"{API}/products/from-cardmarket",
        json={"cardmarket_product_id": BUNDLE, "language": "de"},
        headers=user.headers,
    )
    single = await client.post(
        f"{API}/products/from-cardmarket",
        json={"cardmarket_product_id": CHINESE_GLURAK, "language": "de"},
        headers=user.headers,
    )
    missing = await client.post(
        f"{API}/products/from-cardmarket",
        json={"cardmarket_product_id": 1, "language": "de"},
        headers=user.headers,
    )

    assert unpriced.json()["value"]["kind"] == "none"  # ohne Verknüpfung kein Wert
    assert linked.json()["id"] == old.json()["id"]
    assert linked.json()["cardmarket_product_id"] == BUNDLE
    assert (single.status_code, missing.status_code) == (400, 404)
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Product)) == 1
    short = await client.get(f"{API}/cardmarket/sealed", params={"q": "x"}, headers=user.headers)
    assert short.status_code == 422


async def test_german_search_terms_and_set_names(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    imported: None,
) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                CardSet(external_id="sv08.5", language="de", name="Prismatische Entwicklungen"),
                CardSet(external_id="sv08.5", language="en", name="Prismatic Evolutions"),
            ]
        )
        await session.commit()
        assert await translate_query(session, "Prismatische Entwicklungen Top-Trainer-Box") == (
            "prismatic evolutions elite trainer box"
        )
        assert await translate_query(session, "Pokémon Sammelkoffer") == "pok collector chest"
        assert await translate_query(session, "Paldea Premium-Kollektion") == (
            "paldea premium collection"
        )
        assert await translate_query(session, "Mewtu 3er-Blister") == "mewtu 3 pack blister"
    user = await register_user("de@example.com")

    async def ids(query: str) -> list[int]:
        found = await client.get(
            f"{API}/cardmarket/sealed", params={"q": query}, headers=user.headers
        )
        assert found.status_code == 200, found.text
        return [offer["cardmarket_product_id"] for offer in found.json()]

    assert await ids("Prismatische Entwicklungen Top-Trainer-Box") == [ETB]
    assert await ids("prismatische ttb") == [ETB]  # angefangener Set-Name wird ergänzt
    assert {ETB, BUNDLE} <= set(await ids("Prismatische"))
    assert await ids("Prismatic Booster-Bundle") == [BUNDLE]
    # Englische Eingabe funktioniert weiter.
    assert await ids("prismatic elite") == [ETB]


def test_partial_german_set_names() -> None:
    names = [
        ("karmesin & purpur – 151", "scarlet & violet – 151"),
        ("prismatische entwicklungen", "prismatic evolutions"),
        ("erwachte legenden", "legends awakened"),
        ("karmesin & purpur", "scarlet & violet"),
    ]
    assert partial_set_queries("prismatische ttb", names) == [
        "prismatic evolutions elite trainer box"
    ]
    assert partial_set_queries("Erwachte", names) == ["legends awakened"]
    assert partial_set_queries("karmesin display", names) == [
        "scarlet & violet booster box",
        "scarlet & violet – 151 booster box",
    ]
    assert partial_set_queries("entwick", names) == ["prismatic evolutions"]  # Wortanfang reicht
    assert partial_set_queries("wick", names) == []  # nur am Wortanfang
    assert partial_set_queries("kar", names) == []  # zu kurz
