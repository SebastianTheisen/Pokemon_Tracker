"""Lücken im japanischen Katalog aus tcgcsv ergänzen (Rare Candy · Megalo Cannon 086/076)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CardSource
from app.services import japanese_gaps
from app.services.japanese_gaps import JapaneseGaps, catalog_codes, render_report


def product(pid: int, name: str, number: str) -> dict[str, Any]:
    return {
        "productId": pid,
        "name": name,
        "imageUrl": f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_200w.jpg",
        "extendedData": [
            {"name": "Number", "value": number},
            {"name": "Rarity", "value": "Ultra Rare"},
        ],
    }


GROUPS = [
    {"groupId": 1, "name": "BW9: Megalo Cannon", "abbreviation": "BW9"},
    {"groupId": 2, "name": "BW8: Spiral Force", "abbreviation": "BW8-Brn"},
    {"groupId": 3, "name": "Unbekannt", "abbreviation": "ZZ1"},
    # drei Decks auf dasselbe Katalog-Set, gleich gut → keines ergänzt
    {"groupId": 4, "name": "BK: Cobalion Deck", "abbreviation": "Bk"},
    {"groupId": 5, "name": "BK: Terrakion Deck", "abbreviation": "Bk"},
]
PRODUCTS = {
    1: [product(100 + n, f"Card {n}", f"{n:03d}/076") for n in range(1, 11)]
    + [
        product(186, "Rare Candy - 086/076", "086/076"),
        product(187, "Rare Candy", "086/076"),  # zweite Fassung, gleiche Nummer
        product(190, "Charizard", "001/076"),  # vorhanden – bleibt unverändert
        product(191, "Mew ex - 151", "151"),  # Ausreißer ohne Setgröße
        product(192, "DAR Basic Darkness Energy", "DAR"),  # Energie ohne Nummer
        {"productId": 199, "name": "Megalo Cannon Booster Box", "extendedData": []},
    ],
    # Kürzel passt, aber kaum gemeinsame Nummern → nicht ergänzen
    2: [product(200 + n, f"Other {n}", f"{n:03d}/051") for n in range(40, 52)],
    4: [product(400 + n, f"Deck {n}", f"{n:03d}/014") for n in range(1, 11)]
    + [product(413, "Cobalion", "013/014")],
    5: [product(500 + n, f"Deck {n}", f"{n:03d}/014") for n in range(1, 11)]
    + [product(513, "Terrakion", "013/014")],
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.method == "HEAD":  # große Fassung nur für Rare Candy
        return httpx.Response(200 if "186_" in path else 404)
    if path.endswith("/85/groups"):
        return httpx.Response(200, json={"results": GROUPS})
    group = int(path.split("/")[-2])
    return httpx.Response(200, json={"results": PRODUCTS.get(group, [])})


async def _catalog(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        for code, numbers in (
            ("BW9-B", range(1, 11)),
            ("BW8-Brn", range(1, 6)),
            ("Bk", range(1, 11)),
        ):
            card_set = CardSet(external_id=code, language="ja", name=code)
            session.add(card_set)
            await session.flush()
            session.add_all(
                Card(
                    external_id=f"official-{code}-{n}",
                    language="ja",
                    set_id=card_set.id,
                    number=f"{n:03d}",
                    number_norm=str(n),
                    name=f"カード{n}",
                )
                for n in numbers
            )
        empty = CardSet(external_id="XY11b", language="ja", name="冷酷の反逆者")
        session.add(empty)
        await session.commit()


def test_catalog_codes() -> None:
    assert catalog_codes("BW9-B", None) == {"bw9b", "bw9"}
    assert catalog_codes("XY11-Bb", None) == {"xy11bb"}


async def test_dry_run_then_apply(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await _catalog(session_factory)
    gaps = JapaneseGaps(session_factory, settings, transport=httpx.MockTransport(handler))

    dry = await gaps.run()
    assert dry.dry_run and dry.missing == 1
    ready = [gap for gap in dry.sets if gap.skipped is None]
    assert [(g.catalog_set, [c.number for c in g.missing]) for g in ready] == [("BW9-B", ["086"])]
    skipped = [gap for gap in dry.sets if gap.skipped]
    reasons = {g.abbreviation: g.skipped or "" for g in skipped}
    assert "nur" in reasons["BW8-Brn"]  # zu wenig gemeinsame Nummern
    assert reasons["Bk"].startswith("mehrere TCGplayer-Sets")  # Decks gleichauf
    assert "Rare Candy" in render_report(dry)
    assert dry.large_images == 1
    async with session_factory() as session:
        assert await session.scalar(select(Card).where(Card.number == "086")) is None

    applied = await gaps.run(apply=True)
    assert applied.added == 1
    assert applied.names == 10  # „カード1“ … bekommen „Card 1“ … (für Cardmarket)
    async with session_factory() as session:
        card = (await session.scalars(select(Card).where(Card.number == "086"))).one()
        assert (card.name, card.name_en, card.source) == (
            "Rare Candy",
            "Rare Candy",
            CardSource.TCGPLAYER,
        )
        assert card.number_norm == "86" and card.image_url is not None
        assert card.image_url.endswith("_in_1000x1000.jpg")
        assert card.card_set.external_id == "BW9-B"
        first = (await session.scalars(select(Card).where(Card.number == "001"))).all()
        bw9 = [c for c in first if c.card_set.external_id == "BW9-B"]
        assert [(c.name, c.name_en) for c in bw9] == [("カード1", "Card 1")]

    again = await gaps.run(apply=True)  # wiederholbar, nichts doppelt
    assert again.added == 0 and again.missing == 0


async def test_reports_unreachable_tcgcsv(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lauf 29.10.: tcgcsv lieferte nichts – der Bericht zeigte still „0 fehlen“."""
    await _catalog(session_factory)
    monkeypatch.setattr(japanese_gaps, "RETRY_SECONDS", 0.0)
    broken = httpx.MockTransport(lambda _request: httpx.Response(429, json={}))
    report = await JapaneseGaps(session_factory, settings, transport=broken).run(apply=True)
    assert report.error is not None and "429" in report.error
    assert "Fehler" in render_report(report)
