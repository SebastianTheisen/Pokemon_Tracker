"""Gleiche ID, andere Karte: Asiatische Promo-Sets sind je Land anders nummeriert (Japan SV-P 038
Basic Fire Energy, Taiwan SV-P 038 Charizard VMAX). Weder Bild noch Cardmarket-Produkt dürfen
zwischen solchen Karten wandern."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CmProduct, ImageSource
from app.services.card_names import asian_names_conflict, contradicts_english, pokemon_words
from app.services.cardmarket_catalog import learn_tcgdex_product
from app.services.cardmarket_rescue import drop_contradicting_products
from app.services.catalog_sync import fill_image_fallbacks
from tests.pricing_helpers import make_card

ENERGY = "基本炎エネルギー"
CHARIZARD_TW = "噴火龍VMAX"
TW_IMAGE = "https://asia.pokemon-card.com/tw/card-img/tw00008735.png"


def test_pokemon_words_ignore_shared_suffixes() -> None:
    assert pokemon_words(CHARIZARD_TW, "zh-tw") == {"charizard"}
    assert pokemon_words("リザードンex", "ja") == {"charizard"}
    assert pokemon_words(ENERGY, "ja") is None  # keine Pokémon-Karte


@pytest.mark.parametrize(
    ("first", "first_language", "second", "second_language", "conflict"),
    [
        (ENERGY, "ja", CHARIZARD_TW, "zh-tw", True),  # Pokémon gegen Energie
        ("リザードンVMAX", "ja", CHARIZARD_TW, "zh-tw", False),  # dieselbe Karte
        ("ピカチュウ", "ja", CHARIZARD_TW, "zh-tw", True),  # verschiedene Pokémon
        ("ナンジャモ", "ja", "奇樹", "zh-tw", False),  # Trainer: nicht prüfbar
        ("ホウオウex", "ja", "鳳王ex", "zh-tw", False),  # nur kurze Wörter: nicht prüfbar
        ("Glurak", "de", CHARIZARD_TW, "zh-tw", False),  # nur asiatische Paare
    ],
)
def test_asian_names_conflict(
    first: str, first_language: str, second: str, second_language: str, conflict: bool
) -> None:
    assert asian_names_conflict(first, first_language, second, second_language) is conflict


def test_contradicts_english() -> None:
    assert contradicts_english(CHARIZARD_TW, "zh-tw", "Basic Fire Energy")
    assert not contradicts_english("ガラル サンダーV", "ja", "Galarian Zapdos V")
    assert not contradicts_english("フラベベ", "ja", "Flabebe")  # Akzente egal
    assert not contradicts_english(ENERGY, "ja", "Basic Fire Energy")  # nicht prüfbar


async def _promo_pair(factory: async_sessionmaker[AsyncSession]) -> tuple[Card, Card]:
    energy = await make_card(
        factory, external_id="SV-P-038", name=ENERGY, number="038", language="ja"
    )
    charizard = await make_card(
        factory, external_id="SV-P-038", name=CHARIZARD_TW, number="038", language="zh-tw"
    )
    async with factory() as session:
        loaded = await session.get_one(Card, charizard.id)
        loaded.image_url = TW_IMAGE
        await session.commit()
    return energy, charizard


async def test_no_fallback_image_from_a_different_card(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    energy, _ = await _promo_pair(session_factory)
    same = await make_card(
        session_factory, external_id="SV-P-038", name="리자몽VMAX", number="038", language="ko"
    )
    async with session_factory() as session:
        # Stand vorher: Energie mit dem Glurak-Bild aus Taiwan
        wrong = await session.get_one(Card, energy.id)
        wrong.image_url, wrong.image_source, wrong.image_language = TW_IMAGE, "fallback", "zh-tw"
        await session.commit()

        assert await fill_image_fallbacks(session) == 1  # nur die koreanische Fassung
        await session.commit()
        energy_now = await session.get_one(Card, energy.id)
        same_now = await session.get_one(Card, same.id)
        await session.refresh(energy_now)
        await session.refresh(same_now)

    assert (energy_now.image_url, energy_now.image_source) == (None, None)
    assert (same_now.image_url, same_now.image_source) == (TW_IMAGE, ImageSource.FALLBACK)


async def _energy_product(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        session.add(
            CmProduct(
                id_product=695779, name="Basic Fire Energy", id_expansion=5212, id_metacard=1,
                date_added=datetime(2023, 1, 1, tzinfo=UTC).date(),
            )
        )  # fmt: skip
        await session.commit()


async def test_tcgdex_product_of_another_card_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    energy, charizard = await _promo_pair(session_factory)
    await _energy_product(session_factory)
    async with session_factory() as session:
        loaded_charizard = await session.get_one(Card, charizard.id)
        loaded_energy = await session.get_one(Card, energy.id)
        await session.refresh(loaded_charizard, ["card_set"])
        await session.refresh(loaded_energy, ["card_set"])

        assert not await learn_tcgdex_product(session, loaded_charizard, 695779)
        assert await learn_tcgdex_product(session, loaded_energy, 695779)

    assert loaded_charizard.cardmarket_product_id is None
    assert loaded_energy.cardmarket_product_id == 695779


async def test_existing_wrong_products_are_dropped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    energy, charizard = await _promo_pair(session_factory)
    await _energy_product(session_factory)
    async with session_factory() as session:
        for card_id in (energy.id, charizard.id):
            card = await session.get_one(Card, card_id)
            card.cardmarket_product_id = 695779
            card.name_en = "Basic Fire Energy"
        await session.commit()

        lines = await drop_contradicting_products(session)  # Probelauf
        assert len(lines) == 1 and CHARIZARD_TW in lines[0]
        assert (await session.get_one(Card, charizard.id)).cardmarket_product_id == 695779

        assert len(await drop_contradicting_products(session, dry_run=False)) == 1
        await session.commit()
        charizard_now = await session.get_one(Card, charizard.id)
        energy_now = await session.get_one(Card, energy.id)

    assert (charizard_now.cardmarket_product_id, charizard_now.name_en) == (None, None)
    assert (energy_now.cardmarket_product_id, energy_now.name_en) == (695779, "Basic Fire Energy")


@pytest.mark.parametrize(
    ("name", "english"),
    [
        ("ラッキーエネルギー", "Lucky Energy"),  # „ラッキー“ ist auch Chaneira
        ("ブルーの探索", "Green's Exploration"),
        ("ウッウロボ", "Cram-o-matic"),
        ("ポケモンだいすきクラブ", "Pokémon Fan Club"),
        ("シャーロット・プリン", "Charlotte Pudding"),  # One Piece
    ],
)
def test_names_containing_a_pokemon_are_not_checked(name: str, english: str) -> None:
    """Probelauf 29.10.: 179 Fehlalarme, weil ein Pokémon-Name in Trainer-, Item- und
    One-Piece-Namen steckt. Geprüft wird nur, was ganz ein Pokémon-Name ist."""
    assert pokemon_words(name, "ja") is None
    assert not contradicts_english(name, "ja", english)
    assert not asian_names_conflict(name, "ja", CHARIZARD_TW, "zh-tw")


@pytest.mark.parametrize(
    ("name", "language", "english"),
    [
        ("バドレックス", "ja", "Calyrex [King's Instructions | Bloomshine]"),
        ("蕾冠王", "zh-tw", "Calyrex [King's Instructions | Bloomshine]"),
        ("ドヒドイデ", "ja", "Toxapex [Venoshock | Spike Shot]"),
        ("サーナイトEX", "ja", "MGardevoir EX [Brilliant Arrow]"),
    ],
)
def test_names_ending_in_ex_and_mega_prefix_fit(name: str, language: str, english: str) -> None:
    """Probelauf 29.10.: „Calyrex“ wurde zu „Calyr ex“ getrennt, „MGardevoir“ nicht erkannt."""
    assert not contradicts_english(name, language, english)


def test_swapped_products_are_found() -> None:
    """Echte Fehler aus dem Probelauf: Produkte zweier Karten vertauscht (S11 047/048)."""
    assert contradicts_english("ペロッパフ", "ja", "Slurpuff [Draining Kiss | Magical Shot]")
    assert contradicts_english("コクーン", "ja", "Beedrill [Sudden Sting | Sharp Sting]")
