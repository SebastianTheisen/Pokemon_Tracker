"""Japanische Classic Collection: Import aus tcgcsv.com, Verknüpfung mit Cardmarket, Namen."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CmProduct
from app.scanner.text import extract_text_features
from app.services.classic_collection import (
    ClassicCard,
    ClassicCollection,
    match_products,
    parse_products,
    render_report,
)
from app.services.display_names import card_display_name
from app.services.scan_scoring import Candidate, is_confident, rank, score_text
from tests.scan_helpers import lines


def product(name: str, number: str | None, product_id: int) -> dict[str, Any]:
    extended = [{"name": "Number", "value": number}] if number else []
    return {
        "productId": product_id,
        "name": name,
        "imageUrl": f"https://tcgplayer-cdn.tcgplayer.com/product/{product_id}_200w.jpg",
        "extendedData": [*extended, {"name": "Rarity", "value": "Common"}],
    }


# Wie tcgcsv (Prüfung 28.10.): Deck selbst ohne Nummer, Karten mit „001/032“.
CHARIZARD_DECK = [
    product("Pokemon TCG Classic: Charizard Deck", None, 591900),
    product("Charmander", "001/032", 591909),
    product("Charmeleon", "002/032", 591910),
    product("Ho-Oh ex", "007/032", 591915),
    product("Stantler Lv.28", "016/032", 591924),
    product("Professor Oak", "027/032", 591935),
]


def tcgcsv(requests: list[str], *, large_images: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(f"{request.method} {request.url.path}")
        if request.method == "HEAD":
            return httpx.Response(200 if large_images else 404)
        if request.url.path.endswith("/85/23818/products"):
            return httpx.Response(200, content=json.dumps({"results": CHARIZARD_DECK}).encode())
        if request.url.path.endswith("/products"):
            return httpx.Response(200, content=b'{"results": []}')
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def add_cardmarket(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Cardmarket-Ausgabe 5528 wie im echten Katalog (Namen mit Attacken in Klammern)."""
    rows = [
        (743143, "Pokémon Card Game Classic: Charizard & Ho-Oh ex Deck", "Pokémon Theme Decks"),
        (744592, "Charmander [Scratch | Ember]", "Pokémon Single"),
        (744593, "Charmeleon [Slash | Flamethrower]", "Pokémon Single"),
        (744598, "Ho-Oh ex [Phoenix Breath | Eternal Blaze]", "Pokémon Single"),
        (744607, "Stantler Lv.28 [Lead | Frighten Horn]", "Pokémon Single"),
        (744618, "Professor Oak", "Pokémon Single"),
    ]
    async with session_factory() as session:
        for product_id, name, category in rows:
            session.add(
                CmProduct(
                    id_product=product_id,
                    game="pokemon",
                    id_expansion=5528,
                    id_metacard=0,
                    name=name,
                    date_added=date(2023, 10, 31) if "Deck" in name else date(2023, 11, 8),
                    id_category=51 if category == "Pokémon Single" else 52,
                    category_name=category,
                )
            )
        await session.commit()


def test_parse_and_japanese_names() -> None:
    cards = parse_products({"results": CHARIZARD_DECK})
    assert [card.number for card in cards] == ["001", "002", "007", "016", "027"]
    assert cards[0].total == 32
    assert [card.japanese for card in cards] == [
        "ヒトカゲ",
        "リザード",
        "ホウオウex",
        "オドシシ",  # „Lv.28“ steht nicht im Namen
        None,  # Trainer: kein Pokémon-Name
    ]


def test_cardmarket_matching_by_name_then_order() -> None:
    cards = [
        ClassicCard("Charmander", "001", 32, None, None),
        ClassicCard("Bill", "028", 32, None, None),
        ClassicCard("Basic Fire Energy", "034", 32, None, None),
    ]
    products = [
        (744592, "Charmander [Scratch | Ember]"),
        (744621, "Bill"),
        (744625, "Fire Energy"),  # anderer Name – bleibt übrig und passt in der Reihenfolge
    ]
    assert match_products(cards, products) == {"001": 744592, "028": 744621, "034": 744625}


async def test_import_creates_sets_cards_and_cardmarket_links(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await add_cardmarket(session_factory)
    requests: list[str] = []
    importer = ClassicCollection(session_factory, settings, transport=tcgcsv(requests))

    report = await importer.run()
    again = await importer.run()  # wiederholbar, keine Doppel

    assert [deck.code for deck in report.decks] == ["CLL", "CLF", "CLK"]
    cll = report.decks[0]
    assert (cll.cards, cll.japanese_names, cll.linked, cll.unlinked) == (5, 4, 5, [])
    assert cll.large_images
    assert again.decks[0].linked == 5
    assert "CLL**: 5 Karten" in render_report(report)
    async with session_factory() as session:
        card_set = await session.scalar(select(CardSet).where(CardSet.external_id == "CLL"))
        assert card_set is not None
        assert (card_set.language, card_set.code, card_set.card_count_official) == ("ja", "CLL", 32)
        assert card_set.cardmarket_expansion_id == 5528
        assert card_set.release_date == date(2023, 10, 31)  # erstes Cardmarket-Produkt
        cards = {
            card.number: card
            for card in (
                await session.scalars(
                    select(Card).where(Card.set_id == card_set.id).order_by(Card.number)
                )
            ).unique()
        }
        for card in cards.values():
            await session.refresh(card, ["card_set"])
    assert len(cards) == 5
    charmander = cards["001"]
    assert (charmander.external_id, charmander.name, charmander.name_en) == (
        "CLL-001",
        "ヒトカゲ",
        "Charmander",
    )
    assert charmander.number_norm == "1"
    assert charmander.cardmarket_product_id == 744592
    assert (
        charmander.image_url
        == "https://tcgplayer-cdn.tcgplayer.com/product/591909_in_1000x1000.jpg"
    )
    assert card_display_name(charmander) == "Glumanda"  # App zeigt den deutschen Namen
    assert cards["027"].name == "Professor Oak"
    assert cards["027"].cardmarket_product_id == 744618


async def test_dry_run_and_small_images(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    requests: list[str] = []
    importer = ClassicCollection(
        session_factory, settings, transport=tcgcsv(requests, large_images=False)
    )
    report = await importer.run(dry_run=True)

    assert report.decks[0].cards == 5
    assert not report.decks[0].large_images
    assert "Probelauf" in render_report(report)
    async with session_factory() as session:
        assert await session.scalar(select(CardSet).where(CardSet.external_id == "CLL")) is None


async def test_scanner_prefers_classic_over_base_set_artwork(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Binder-Foto 28.10.: „リザード“ + „002/032“ – vorher gewann das Grundset 1996 (gleiche
    Grafik) per Bildabgleich als „sicher“. Jetzt: Classic-Karte sicher, Grundset widerspricht."""
    await ClassicCollection(session_factory, settings, transport=tcgcsv([])).run()
    async with session_factory() as session:
        classic = await session.scalar(select(Card).where(Card.external_id == "CLL-002"))
        assert classic is not None
        await session.refresh(classic, ["card_set"])
    base_set = Card(
        language="ja",
        number="5",
        number_norm="5",
        name="リザード",
        card_set=CardSet(
            external_id="pc-pokemon-japanese-expansion-pack",
            language="ja",
            name="Pokemon Japanese Expansion Pack",
            card_count_official=102,
            game="pokemon",
        ),
    )
    text = extract_text_features(lines("リザード", "002/032"))
    ranked = rank(
        [
            score_text(Candidate(classic, catalog_inliers=140), text),
            score_text(Candidate(base_set, catalog_inliers=150), text),
        ]
    )
    assert ranked[0].card.external_id == "CLL-002"
    assert ranked[1].total_conflict
    assert is_confident(ranked)
