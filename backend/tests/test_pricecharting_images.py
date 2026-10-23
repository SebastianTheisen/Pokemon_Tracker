"""Fehlende Kartenbilder von PriceCharting (Set-Zuordnung über den Namen, Karten je Nummer)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet
from app.providers.apify import ApifyClient
from app.providers.fx import EcbRates
from app.services.pricecharting_catalog import PriceChartingCatalog
from app.services.pricecharting_images import choose_slug, import_pricecharting_images

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
