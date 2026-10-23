"""Korea/China-Katalog aus PriceCharting-Sets: Set-Liste, Karten, Bilder, Preise."""

from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    Card,
    CardSet,
    CardSource,
    CollectionItem,
    Folder,
    PriceCheck,
    PricePoint,
    Role,
    User,
)
from app.providers.apify import ApifyClient
from app.providers.fx import EcbRates
from app.services.pricecharting_catalog import (
    JP_VINTAGE,
    PriceChartingCatalog,
    japanese_name,
    metric_name,
    parse_consoles,
    parse_product,
    replaced_by_pricecharting,
    set_name,
)

NOW = datetime(2026, 10, 21, 21, 0, tzinfo=UTC)
CATEGORY = """<ul>
<li><a href="/console/pokemon-korean-electric-breaker">Pokemon Korean Electric Breaker</a></li>
<li><a href="/console/pokemon-chinese-gem-pack">Pokemon Chinese Gem Pack</a></li>
<li><a href="/console/pokemon-japanese-paradigm-trigger">Pokemon Japanese Paradigm Trigger</a></li>
<li><a href="/console/pokemon-korean-electric-breaker">doppelt</a></li>
</ul>"""
ECB = "<Cube time='2026-10-21'><Cube currency='USD' rate='1.25'/></Cube>"
GEM_PACK = {
    "collectionUrl": "https://www.pricecharting.com/console/pokemon-chinese-gem-pack",
    "collectionName": "Pokemon Chinese Gem Pack",
    "priceColumns": {"used": "Ungraded", "cib": "Grade 9", "new": "PSA 10"},
    "productCount": 3,
    "products": [
        {
            "productId": 8927090,
            "productName": "Captain Pikachu #709",
            "url": "https://www.pricecharting.com/game/pokemon-chinese-gem-pack/captain-pikachu-709",
            "imageUrl": "https://storage.googleapis.com/images.pricecharting.com/abc/1600.jpg",
            "prices": {"used": 202.5, "cib": 223, "new": None},
        },
        {
            "productId": 8710188,
            "productName": "Pikachu [Full Art] #708",
            "imageUrl": None,
            "prices": {"used": None, "cib": None, "new": None},
        },
        {"productId": 1, "productName": "Gem Pack Booster Box", "prices": {"used": 99}},
    ],
}


def transport(calls: list[str], *, blocked: bool = False) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.host}{request.url.path}")
        if request.url.host == "www.pricecharting.com":
            return httpx.Response(403) if blocked else httpx.Response(200, text=CATEGORY)
        if request.url.host == "www.ecb.europa.eu":
            return httpx.Response(200, text=ECB)
        path = request.url.path
        if path.endswith("/users/me/limits"):
            body: Any = {
                "data": {"current": {"monthlyUsageUsd": 1}, "limits": {"maxMonthlyUsageUsd": 8}}
            }
        elif "cheerio-scraper" in path:
            body = {"data": {"id": "c", "status": "SUCCEEDED", "defaultDatasetId": "links"}}
        elif path.endswith("/datasets/links/items"):
            hrefs = [
                "/console/pokemon-korean-electric-breaker",
                "https://www.pricecharting.com/console/pokemon-chinese-gem-pack",
                "/console/pokemon-japanese-paradigm-trigger",
            ]
            body = [{"links": hrefs}]
        elif path.endswith("/runs"):
            collections = json.loads(request.content)["collections"]
            assert collections == [
                "https://www.pricecharting.com/console/pokemon-korean-electric-breaker",
                "https://www.pricecharting.com/console/pokemon-chinese-gem-pack",
            ]
            body = {
                "data": {
                    "id": "r",
                    "status": "SUCCEEDED",
                    "defaultDatasetId": "d",
                    "usageTotalUsd": 0.02,
                }
            }
        elif path.endswith("/datasets/d/items"):
            body = [GEM_PACK]
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=json.dumps(body).encode())

    return httpx.MockTransport(handler)


def catalog(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    calls: list[str],
    *,
    blocked: bool = False,
) -> PriceChartingCatalog:
    mock = transport(calls, blocked=blocked)
    return PriceChartingCatalog(
        factory,
        settings,
        EcbRates(user_agent="t", transport=mock, clock=lambda: NOW),
        lambda: ApifyClient("token", user_agent="t", transport=mock),
        transport=mock,
        clock=lambda: NOW,
    )


def test_parsing_helpers() -> None:
    consoles = parse_consoles(CATEGORY, ["ko", "zh-cn"])
    assert [(c.slug, c.language) for c in consoles] == [
        ("pokemon-korean-electric-breaker", "ko"),
        ("pokemon-chinese-gem-pack", "zh-cn"),
    ]
    assert parse_product({"productName": "Pikachu [Full Art] #708"}) == (
        "Pikachu [Full Art]",
        "708",
    )
    assert parse_product({"productName": "Gem Pack Booster Box"}) is None
    assert (metric_name("Ungraded"), metric_name("Grade 9.5"), metric_name("PSA 10")) == (
        "ungraded",
        "grade_9_5",
        "psa_10",
    )
    assert metric_name("Box Only") is None
    assert set_name({"collectionName": "Prices for Pokemon Korean Electric Breaker"}) == (
        "Electric Breaker"
    )


async def test_dry_run_only_lists_sets(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    calls: list[str] = []
    report = await catalog(session_factory, settings, calls).run(dry_run=True)

    assert len(report.consoles) == 2
    assert calls == ["GET www.pricecharting.com/category/pokemon-cards"]  # nichts bezahlt


async def test_import_creates_sets_cards_and_prices(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    calls: list[str] = []
    service = catalog(session_factory, settings, calls)

    report = await service.run()

    assert (report.sets, report.cards, report.priced, report.skipped_products) == (1, 2, 1, 1)
    assert report.cost_usd == 0.02
    async with session_factory() as session:
        card_set = await session.scalar(
            select(CardSet).where(CardSet.external_id == "pc-pokemon-chinese-gem-pack")
        )
        assert card_set is not None
        assert (card_set.language, card_set.name) == ("zh-cn", "Gem Pack")
        card = await session.scalar(select(Card).where(Card.external_id == "pc-8927090"))
        assert card is not None
        assert (card.name, card.number, card.number_norm, card.source) == (
            "Captain Pikachu",
            "709",
            "709",
            CardSource.PRICECHARTING,
        )
        assert card.image_url is not None and card.image_url.endswith("/1600.jpg")
        prices = {
            (p.variant, p.metric): p.value
            for p in await session.scalars(select(PricePoint).where(PricePoint.card_id == card.id))
        }
        assert prices == {
            ("normal", "ungraded"): Decimal("162.00"),
            ("graded", "grade_9"): Decimal("178.40"),
        }
        check = await session.get(PriceCheck, (card.id, "pricecharting"))
        assert check is not None and check.ok  # kein Einzelabruf mehr nötig

    again = await service.run()  # erneut: aktualisiert, keine Dubletten
    assert again.cards == 2
    async with session_factory() as session:
        cards = (await session.scalars(select(Card).where(Card.language == "zh-cn"))).all()
        assert len(cards) == 2


async def test_set_list_via_apify_when_server_is_blocked(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    calls: list[str] = []
    report = await catalog(session_factory, settings, calls, blocked=True).run(dry_run=True)

    assert [(c.slug, c.language) for c in report.consoles] == [
        ("pokemon-korean-electric-breaker", "ko"),
        ("pokemon-chinese-gem-pack", "zh-cn"),
    ]
    assert any("cheerio-scraper" in call for call in calls)


# ------------------------------------------------------- Japanische Vintage-Sets

EXPANSION_PACK = {
    "collectionUrl": "https://www.pricecharting.com/console/pokemon-japanese-expansion-pack",
    "collectionName": "Pokemon Japanese Expansion Pack",
    "priceColumns": {"used": "Ungraded"},
    "productCount": 5,
    "products": [
        {"productId": 11, "productName": "Charizard #6", "imageUrl": "https://img/6.jpg",
         "prices": {"used": 250}},
        {"productId": 12, "productName": "Charizard [No Rarity] #6", "imageUrl": "https://img/n.jpg",
         "prices": {"used": 900}},
        {"productId": 13, "productName": "Bill #74", "imageUrl": "https://img/b.jpg",
         "prices": {"used": 2}},
        {"productId": 15, "productName": "Moo-Moo Milk", "imageUrl": "https://img/m.jpg",
         "prices": {"used": 3}},
        {"productId": 14, "productName": "Expansion Pack Booster", "prices": {"used": 99}},
    ],
}  # fmt: skip


def vintage_transport(requested: list[list[str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "www.ecb.europa.eu":
            return httpx.Response(200, text=ECB)
        if path.endswith("/users/me/limits"):
            body: Any = {
                "data": {"current": {"monthlyUsageUsd": 1}, "limits": {"maxMonthlyUsageUsd": 8}}
            }
        elif path.endswith("/runs"):
            requested.append(json.loads(request.content)["collections"])
            body = {"data": {"id": "r", "status": "SUCCEEDED", "defaultDatasetId": "d"}}
        elif path.endswith("/datasets/d/items"):
            body = [EXPANSION_PACK] if len(requested) == 1 else []
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=json.dumps(body).encode())

    return httpx.MockTransport(handler)


async def _tcgdex_base_set(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    """TCGdex-Fassung mit fehlerhaften Namen; eine Karte liegt in einer Sammlung."""
    async with factory() as session:
        card_set = CardSet(
            external_id="PMCG1",
            language="ja",
            name="拡張パック",
            series_name="PMCG",
            release_date=date(1996, 10, 20),
        )
        session.add(card_set)
        await session.flush()
        cards = [
            Card(external_id=f"PMCG1-{n}", language="ja", set_id=card_set.id, number=n,
                 number_norm=n, name=name)
            for n, name in (("4", "リザードン"), ("74", "マサキ"), ("19", "奇妙な"))
        ]  # fmt: skip
        user = User(email="v@example.com", display_name="V", password_hash="x", role=Role.USER)
        session.add_all([*cards, user])
        await session.flush()
        folder = Folder(user_id=user.id, name="Ordner")
        session.add(folder)
        await session.flush()
        session.add(CollectionItem(user_id=user.id, folder_id=folder.id, card_id=cards[0].id))
        await session.commit()
        return cards[0].id


async def test_jp_vintage_replaces_broken_tcgdex_set(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    kept_id = await _tcgdex_base_set(session_factory)
    requested: list[list[str]] = []
    mock = vintage_transport(requested)
    service = PriceChartingCatalog(
        session_factory,
        settings,
        EcbRates(user_agent="t", transport=mock, clock=lambda: NOW),
        lambda: ApifyClient("token", user_agent="t", transport=mock),
        transport=mock,
        clock=lambda: NOW,
    )

    preview = await service.run_vintage(dry_run=True)
    assert requested == []  # Probelauf kostet nichts
    first = preview.replacements[0]
    assert (first.tcgdex_id, first.removed, first.kept) == ("PMCG1", 2, 1)

    report = await service.run_vintage()

    assert len(requested) == math.ceil(len(JP_VINTAGE) / 10)
    assert (report.sets, report.cards, report.skipped_products) == (1, 4, 1)  # Booster nicht
    assert "pokemon-japanese-jungle" in report.missing  # TCGdex-Set bliebe dann bestehen
    assert [(r.tcgdex_id, r.removed, r.kept, r.set_removed) for r in report.replacements] == [
        ("PMCG1", 2, 1, False)
    ]
    async with session_factory() as session:
        new_set = await session.scalar(
            select(CardSet).where(CardSet.external_id == "pc-pokemon-japanese-expansion-pack")
        )
        assert new_set is not None
        assert (new_set.name, str(new_set.release_date)) == ("拡張パック", "1996-10-20")
        names = sorted(
            (await session.scalars(select(Card.name).where(Card.set_id == new_set.id))).all()
        )
        assert names == ["Bill", "Moo-Moo Milk", "リザードン", "リザードン [No Rarity]"]
        remaining = (
            await session.scalars(select(Card.id).where(Card.external_id.like("PMCG1-%")))
        ).all()
        assert remaining == [kept_id]  # in einer Sammlung → bleibt
        assert await replaced_by_pricecharting(session, "ja", "PMCG1")
        assert not await replaced_by_pricecharting(session, "ja", "PMCG2")
        assert not await replaced_by_pricecharting(session, "en", "PMCG1")


def test_japanese_names_from_pokedex() -> None:
    assert japanese_name("Charizard") == "リザードン"
    assert japanese_name("Dark Charizard [1st Edition]") == "わるいリザードン [1st Edition]"
    assert japanese_name("Brock's Onix") == "タケシのイワーク"
    assert japanese_name("Bill") == "Bill"  # Trainer bleibt englisch
