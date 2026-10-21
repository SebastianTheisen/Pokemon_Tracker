"""Bilder für versiegelte Produkte: Zuordnung über den Namen, Abgleich mit tcgcsv.com."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import CmProduct, Product, ProductKind
from app.services.cardmarket_catalog import run_catalog_import
from app.services.sealed_images import Matcher, TcgProduct, refresh_sealed_images, tokens
from tests.test_cardmarket_catalog import catalog_transport

CDN = "https://tcgplayer-cdn.tcgplayer.com/product"


def tcg(product_id: int, name: str, language: str = "en") -> TcgProduct:
    return TcgProduct(product_id, name, f"{CDN}/{product_id}_200w.jpg", language)


def test_tokens_unify_wording() -> None:
    assert tokens("Pokémon TCG: Next Destinies Booster Pack") == tokens("Next Destinies Booster")
    assert tokens("Surging Sparks Booster Box") == tokens("Surging Sparks Display")
    assert tokens("Prismatic Evolutions Elite Trainer Box") == {"prismatic", "evolutions", "etb"}
    assert tokens("Scarlet & Violet Booster Bundle") == {"scarlet", "violet", "bundle"}


def test_matcher_needs_same_kind_clear_lead_and_prefers_language() -> None:
    matcher = Matcher(
        [
            tcg(1, "Next Destinies Booster Pack"),
            tcg(2, "Next Destinies Booster Box"),
            tcg(3, "151 Booster Box"),
            tcg(4, "151 Booster Box", "ja"),
            tcg(5, "Paldea Evolved Booster Bundle"),
            tcg(6, "Paldea Evolved Booster Bundle"),  # gleicher Name, anderes Produkt
        ]
    )

    booster = matcher.best("Next Destinies Booster", ProductKind.BOOSTER, ["en", "ja"])
    display = matcher.best("Next Destinies Display", ProductKind.DISPLAY, ["en", "ja"])
    japanese = matcher.best("151 Display", ProductKind.DISPLAY, ["ja", "en"])

    assert (booster and booster.product_id, display and display.product_id) == (1, 2)
    assert japanese is not None and japanese.language == "ja"
    # Andere Art → kein Bild (ein Booster bekommt nie das Display-Bild).
    assert matcher.best("151 Booster", ProductKind.BOOSTER, ["en"]) is None
    # Zu unähnlich bzw. zweideutig → kein Bild.
    assert matcher.best("Base Set Display", ProductKind.DISPLAY, ["en"]) is None
    assert matcher.best("Paldea Evolved Bundle", ProductKind.BOOSTER_BUNDLE, ["en"]) is None


def tcgcsv_transport(fail: bool = False) -> httpx.MockTransport:
    """Simuliertes tcgcsv.com plus Cardmarket-Downloads (ein Transport für beide)."""
    catalog = catalog_transport()
    groups = {3: [{"groupId": 10}], 85: [{"groupId": 20}]}
    products: dict[int, list[dict[str, Any]]] = {
        10: [
            {
                "productId": 501,
                "name": "Prismatic Evolutions Elite Trainer Box",
                "imageUrl": f"{CDN}/501_200w.jpg",
                "extendedData": [],
            },
            {
                "productId": 502,
                "name": "Pikachu - 25/165",
                "imageUrl": f"{CDN}/502_200w.jpg",
                "extendedData": [{"name": "Number", "value": "025/165"}],
            },
        ],
        20: [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "tcgcsv.com":
            return catalog.handle_request(request)
        if fail:
            return httpx.Response(503)
        parts = request.url.path.strip("/").split("/")  # tcgplayer/{cat}/groups|{group}/products
        if parts[-1] == "groups":
            body: Any = {"results": groups[int(parts[1])]}
        else:
            body = {"results": products[int(parts[2])]}
        return httpx.Response(200, content=json.dumps(body).encode())

    return httpx.MockTransport(handler)


async def test_refresh_assigns_images_and_backfills_products(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    transport = tcgcsv_transport()
    assert await refresh_sealed_images(session_factory, settings, transport=transport) is None
    await run_catalog_import(session_factory, settings, tcgdex=None, transport=transport)
    async with session_factory() as session:
        session.add(
            Product(
                kind=ProductKind.ELITE_TRAINER_BOX,
                language="de",
                name="Prismatic Evolutions Elite Trainer Box",
                cardmarket_product_id=700001,
            )
        )
        await session.commit()
    now = datetime(2026, 10, 21, tzinfo=UTC)

    report = await refresh_sealed_images(
        session_factory, settings, transport=transport, clock=lambda: now
    )

    assert report is not None
    assert (report.tcg_products, report.sealed, report.matched, report.products_updated) == (
        1,
        2,
        1,
        1,
    )
    async with session_factory() as session:
        etb = await session.get_one(CmProduct, 700001)
        assert (etb.image_url, etb.tcgplayer_product_id) == (f"{CDN}/501_200w.jpg", 501)
        assert (await session.get_one(CmProduct, 700002)).image_url is None
        product = await session.scalar(
            select(Product).where(Product.cardmarket_product_id == 700001)
        )
        assert product is not None and product.image_url == f"{CDN}/501_200w.jpg"
    # Erst nach einer Woche wieder (außer erzwungen); Ausfall stört nicht.
    later = now + timedelta(days=1)
    assert await refresh_sealed_images(session_factory, settings, clock=lambda: later) is None
    failing = tcgcsv_transport(fail=True)
    assert (
        await refresh_sealed_images(session_factory, settings, force=True, transport=failing)
    ) is None
