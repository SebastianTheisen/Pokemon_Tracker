"""Fehlende Kartenbilder von PriceCharting (Set-Zuordnung über den Namen, Karten je Nummer)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, PricePoint
from app.providers.apify import ApifyClient
from app.providers.fx import EcbRates
from app.services.pricecharting_catalog import PriceChartingCatalog
from app.services.pricecharting_images import (
    choose_slug,
    guessed_slug,
    import_pricecharting_images,
)

NOW = datetime(2026, 10, 23, tzinfo=UTC)
SLUGS = [
    "pokemon-mcdonalds-2023",
    "pokemon-mcdonalds-2024",
    "pokemon-japanese-vmax-climax",
    "pokemon-vmax-climax-promo",
    "pokemon-my-first-battle",
]


def test_choose_slug() -> None:
    assert choose_slug("McDonald's Collection 2023", "en", SLUGS) == "pokemon-mcdonalds-2023"
    assert choose_slug("VMAX Climax", "ja", SLUGS) == "pokemon-japanese-vmax-climax"
    assert choose_slug("My First Battle", "en", SLUGS) == "pokemon-my-first-battle"
    assert choose_slug("Base Set", "en", SLUGS) is None
    assert choose_slug("Miracle Twin", "ja", ["pokemon-japanese-miracle-twins"]) == (
        "pokemon-japanese-miracle-twins"
    )
    assert guessed_slug("Jet-Black Spirit") == "pokemon-japanese-jet-black-spirit"


MCDONALDS = {
    "collectionUrl": "https://www.pricecharting.com/console/pokemon-mcdonalds-2023",
    "products": [
        {"productId": 1, "productName": "Pikachu #1", "imageUrl": "https://img/pika.jpg"},
        {"productId": 2, "productName": "Charmander #2", "imageUrl": "https://img/char.jpg"},
        {"productId": 3, "productName": "Sprigatito #3", "imageUrl": "https://img/spri.jpg"},
        {"productId": 4, "productName": "Happy Meal Box", "imageUrl": "https://img/box.jpg"},
    ],
}


def transport(collections: list[list[str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/users/me/limits"):
            body: Any = {
                "data": {"current": {"monthlyUsageUsd": 1}, "limits": {"maxMonthlyUsageUsd": 8}}
            }
        elif "cheerio-scraper" in path:
            body = {"data": {"id": "c", "status": "SUCCEEDED", "defaultDatasetId": "links"}}
        elif path.endswith("/datasets/links/items"):
            body = [{"links": [f"/console/{slug}" for slug in SLUGS]}]
        elif path.endswith("/runs"):
            collections.append(json.loads(request.content)["collections"])
            body = {"data": {"id": "r", "status": "SUCCEEDED", "defaultDatasetId": "d",
                             "usageTotalUsd": 0.01}}  # fmt: skip
        elif path.endswith("/datasets/d/items"):
            body = [MCDONALDS]
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=json.dumps(body).encode())

    return httpx.MockTransport(handler)


async def test_missing_images_are_filled(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    async with session_factory() as session:
        for language, name in (("en", "McDonald's Collection 2023"), ("de", "McDonald's 2023")):
            card_set = CardSet(external_id="2023sv", language=language, name=name)
            session.add(card_set)
            await session.flush()
            names = ("Pikachu", "Charmander", "Sprigatito", "Fuecoco") if language == "en" else (
                "Pikachu", "Glumanda", "Felori", "Krokel")  # fmt: skip
            session.add_all(
                Card(external_id=f"2023sv-{n}", language=language, set_id=card_set.id,
                     number=str(n), number_norm=str(n), name=name)
                for n, name in enumerate(names, start=1)
            )  # fmt: skip
        await session.commit()
    collections: list[list[str]] = []
    mock = transport(collections)
    catalog = PriceChartingCatalog(
        session_factory,
        settings,
        EcbRates(user_agent="t", transport=mock, clock=lambda: NOW),
        lambda: ApifyClient("token", user_agent="t", transport=mock),
        transport=mock,
        clock=lambda: NOW,
    )

    preview = await import_pricecharting_images(session_factory, catalog, dry_run=True)
    assert preview.mapping == {"en/2023sv McDonald's Collection 2023": "pokemon-mcdonalds-2023"}
    assert collections == []  # Probelauf lädt keine Set-Seiten

    report = await import_pricecharting_images(session_factory, catalog)

    assert (report.images_set, report.fallbacks) == (3, 3)
    async with session_factory() as session:
        images = {
            (c.language, c.number): (c.image_url, c.image_source, c.image_language)
            for c in (await session.scalars(select(Card))).all()
        }
    assert images[("en", "1")] == ("https://img/pika.jpg", "pricecharting", None)
    assert images[("de", "2")] == ("https://img/char.jpg", "fallback", "en")  # englisches Bild
    assert images[("en", "4")] == (None, None, None)  # nicht bei PriceCharting


EEVEE_HEROES = {
    "collectionUrl": "https://www.pricecharting.com/console/pokemon-japanese-eevee-heroes",
    "priceColumns": {"used": "Ungraded"},
    "products": [
        {"productId": 11, "productName": "Eevee #1", "imageUrl": "https://img/1.jpg"},
        {"productId": 12, "productName": "Umbreon V #46", "imageUrl": "https://img/46.jpg"},
        {"productId": 13, "productName": "Umbreon VMAX #95", "imageUrl": "https://img/95.jpg",
         "prices": {"used": 1250}},
        {"productId": 14, "productName": "Eevee Heroes Booster Box", "imageUrl": "https://img/b"},
    ],
}  # fmt: skip


async def test_missing_japanese_cards_are_added(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Secret Rares über der offiziellen Set-Größe (S6a 095) fehlen bei TCGdex und in der
    offiziellen Datenbank – PriceCharting führt sie."""
    async with session_factory() as session:
        card_set = CardSet(external_id="S6a", language="ja", name="イーブイヒーローズ")
        session.add(card_set)
        await session.flush()
        session.add_all(
            Card(external_id=f"S6a-{n}", language="ja", set_id=card_set.id, number=n,
                 number_norm=n.lstrip("0"), name=name, image_url=f"https://x/{n}")
            for n, name in (("001", "イーブイ"), ("046", "ブラッキーV"))
        )  # fmt: skip
        await session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "www.ecb.europa.eu":
            return httpx.Response(200, text="<Cube currency='USD' rate='1.25'/>")
        if path.endswith("/users/me/limits"):
            body: Any = {
                "data": {"current": {"monthlyUsageUsd": 1}, "limits": {"maxMonthlyUsageUsd": 8}}
            }
        elif "cheerio-scraper" in path:
            body = {"data": {"id": "c", "status": "SUCCEEDED", "defaultDatasetId": "links"}}
        elif path.endswith("/datasets/links/items"):
            body = [{"links": ["/console/pokemon-base-set"]}]  # Eevee Heroes fehlt dort
        elif path.endswith("/runs"):
            assert json.loads(request.content)["collections"] == [
                "https://www.pricecharting.com/console/pokemon-japanese-eevee-heroes"
            ]
            body = {"data": {"id": "r", "status": "SUCCEEDED", "defaultDatasetId": "d"}}
        elif path.endswith("/datasets/d/items"):
            body = [EEVEE_HEROES]
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=json.dumps(body).encode())

    mock = httpx.MockTransport(handler)
    catalog = PriceChartingCatalog(
        session_factory,
        settings,
        EcbRates(user_agent="t", transport=mock, clock=lambda: NOW),
        lambda: ApifyClient("token", user_agent="t", transport=mock),
        transport=mock,
        clock=lambda: NOW,
    )

    report = await import_pricecharting_images(session_factory, catalog, gaps=True)

    assert report.cards_added == {"ja/S6a イーブイヒーローズ": 1}, report
    async with session_factory() as session:
        umbreon = await session.scalar(select(Card).where(Card.number == "095"))
        assert umbreon is not None
        assert (umbreon.name, umbreon.number_norm, umbreon.image_url) == (
            "ブラッキーVMAX",
            "95",
            "https://img/95.jpg",
        )
        price = await session.scalar(
            select(PricePoint.value).where(PricePoint.card_id == umbreon.id)
        )
        assert str(price) == "1000.00"  # 1250 $ / 1,25
