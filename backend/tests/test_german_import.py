"""Deutsche Karten aus dem PokéWiki: Kartenliste lesen, zuordnen, fehlende Karten anlegen."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CardSource
from app.services.german_import import import_german, match_rows, parse_rows, remove_imported

PROMOS = """{{ErweiterungPrevNext}} Zu den '''XY Black Star Promos''' gehören …
{{Setheader|level=nein}}
{{Setzeile|XY01|Endivie|Pflanze}}
{{Setzeile|XY02|Feurigel|Feuer}}
{{Setzeile|XY03|Karnimani|Wasser}}
"""
VAULT = """{{Infobox Erweiterung |Name=Drachengruft |Englisch=Dragon Vault }}
{{Setzeile|1|Dratini|Drache}}
{{Setzeile|2|Dragonir|Drache}}
"""
UNRELATED = "|Englisch=Base\n{{Setzeile|77|Glurak|Feuer}}\n{{Setzeile|78|Turtok|Wasser}}"


def wiki_transport(calls: list[dict[str, Any]]) -> httpx.MockTransport:
    pages = {
        "XY Black Star Promos (TCG)": PROMOS,
        "Drachengruft (TCG)": VAULT,
        "Basis Set (TCG)": UNRELATED,
    }
    searches = {"Base (TCG)": ["Basis Set (TCG)"]}

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        if params.get("action") == "parse":
            text = pages.get(params["page"])
            body: Any = {"parse": {"wikitext": text}} if text else {"error": {"code": "missing"}}
        else:
            titles = searches.get(params.get("srsearch", ""), [])
            body = {"query": {"search": [{"title": title} for title in titles]}}
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


async def _english_set(
    factory: async_sessionmaker[AsyncSession], set_id: str, name: str, numbers: list[str]
) -> None:
    async with factory() as session:
        card_set = CardSet(external_id=set_id, language="en", name=name, series_name="XY")
        session.add(card_set)
        await session.flush()
        session.add_all(
            Card(
                external_id=f"{set_id}-{number}",
                language="en",
                set_id=card_set.id,
                number=number,
                number_norm=number.lstrip("0") or "0",
                name=f"EN {number}",
                image_url=f"https://assets.tcgdex.net/en/{set_id}/{number}",
                cardmarket_product_id=1000 + index,
            )
            for index, number in enumerate(numbers)
        )
        await session.commit()


def test_parse_rows_skips_duplicate_numbers() -> None:
    kit = "{{Setzeile|1|Dartiri|Farblos}}{{Setzeile|1|Snubbull|Fee}}{{Setzeile|2|Tausch|I}}"
    assert parse_rows(PROMOS) == [("XY01", "Endivie"), ("XY02", "Feurigel"), ("XY03", "Karnimani")]
    assert parse_rows(kit) == [("2", "Tausch")]  # zwei Deckhälften mit gleicher Nummer


def test_match_rows_exact_or_by_digits() -> None:
    cards = [
        Card(external_id="xyp-XY01", number="XY01", number_norm="XY1", name="a"),
        Card(external_id="xyp-XY02", number="XY02", number_norm="XY2", name="b"),
    ]
    matched = match_rows([("XY01", "Endivie"), ("2", "Feurigel"), ("99", "?")], cards)
    assert [(card.external_id, name) for card, name in matched] == [
        ("xyp-XY01", "Endivie"),
        ("xyp-XY02", "Feurigel"),
    ]


async def test_import_adds_missing_german_cards(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await _english_set(session_factory, "xyp", "XY Black Star Promos", ["XY01", "XY02", "XY03"])
    await _english_set(session_factory, "dv1", "Dragon Vault", ["1", "2"])
    await _english_set(session_factory, "base1", "Base", ["1", "2"])
    calls: list[dict[str, Any]] = []

    preview = await import_german(
        session_factory, settings, dry_run=True, transport=wiki_transport(calls), pause=0
    )
    assert preview.added == 5
    async with session_factory() as session:
        assert await session.scalar(select(Card).where(Card.language == "de")) is None

    report = await import_german(
        session_factory, settings, transport=wiki_transport(calls), pause=0
    )

    by_set = {result.set_id: result for result in report.sets}
    assert (by_set["xyp"].added, by_set["dv1"].added, by_set["base1"].added) == (3, 2, 0)
    assert by_set["base1"].note == "Seite passt nicht zu den Nummern"  # 77/78 ≠ 1/2
    async with session_factory() as session:
        card = await session.scalar(
            select(Card).where(Card.external_id == "xyp-XY02", Card.language == "de")
        )
        assert card is not None
        assert (card.name, card.number, card.source) == ("Feurigel", "XY02", CardSource.POKEWIKI)
        assert card.cardmarket_product_id == 1001  # gleiches Cardmarket-Produkt wie EN
        assert card.image_url == "https://assets.tcgdex.net/en/xyp/XY02"  # Ersatzbild EN
        assert card.card_set.name == "XY Black Star Promos"
        vault = await session.scalar(
            select(CardSet).where(CardSet.external_id == "dv1", CardSet.language == "de")
        )
        assert vault is not None and vault.name == "Drachengruft"

    again = await import_german(session_factory, settings, transport=wiki_transport(calls), pause=0)
    assert again.added == 0  # nichts doppelt


async def test_remove_imported_cards_of_a_set(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await _english_set(session_factory, "xyp", "XY Black Star Promos", ["XY01", "XY02", "XY03"])
    await _english_set(session_factory, "dv1", "Dragon Vault", ["1", "2"])
    calls: list[dict[str, Any]] = []
    await import_german(session_factory, settings, transport=wiki_transport(calls), pause=0)

    async with session_factory() as session:
        preview = await remove_imported(session, ["dv1"], dry_run=True)
        assert (preview.cards_removed, preview.cards_kept) == (2, 0)
        report = await remove_imported(session, ["dv1"])
        await session.commit()
        assert (report.cards_removed, report.sets_removed) == (2, 1)
        german = (
            await session.scalars(select(Card.external_id).where(Card.language == "de"))
        ).all()
        assert sorted(str(x) for x in german) == ["xyp-XY01", "xyp-XY02", "xyp-XY03"]  # anderes Set
