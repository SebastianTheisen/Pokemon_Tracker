"""Cardmarket-Zuordnung über Kartennamen (Sets ohne Ausgabe, Karten ohne Produkt)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, CmExpansion, CmPrice, CmProduct
from app.services.cardmarket_catalog import SINGLE_CATEGORY, correct_cardmarket_quotes
from app.services.cardmarket_matching import match_cardmarket, name_key
from app.services.pricing import card_ref

# Cardmarket: 30th Celebration japanisch (6602) und vereinfacht-chinesisch (6603), Zwillinge.
ENGLISH = [
    "Bulbasaur [Tackle]",
    "Squirtle [Bubble]",
    "Eevee [Gnaw]",
    "Pikachu [Thunder Shock]",
    "Mewtwo ex [Psychic]",
    "Charizard ex [Burning Darkness | Explosive Vortex]",
    "Charizard ex [Burning Darkness | Explosive Vortex] (V.2)",  # Special Art Rare
]
JAPANESE = [
    ("001", "フシギダネ"),
    ("007", "ゼニガメ"),
    ("133", "イーブイ"),
    ("025", "ピカチュウ"),
    ("150", "ミュウツーex"),
    ("006", "リザードンex"),
    ("137", "リザードンex"),
    ("099", "博士の研究"),  # Trainer: ohne englischen Namen → offen
]
CHINESE = ["妙蛙种子", "杰尼龟", "伊布", "皮卡丘", "超梦ex", "喷火龙ex", "喷火龙ex", "博士的研究"]


async def _catalog(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        session.add_all(
            [
                CmExpansion(id_expansion=6602, product_count=7, first_added=date(2026, 9, 10),
                            twin_ids=[6603]),
                CmExpansion(id_expansion=6603, product_count=7, first_added=date(2026, 9, 11),
                            twin_ids=[6602]),
                CmExpansion(id_expansion=5000, product_count=3, first_added=date(2020, 1, 1)),
            ]
        )  # fmt: skip
        for offset, expansion in ((0, 6602), (100, 6603)):
            session.add_all(
                CmProduct(id_product=600000 + offset + index, id_expansion=expansion,
                          id_metacard=index + 1, name=name, id_category=SINGLE_CATEGORY,
                          category_name="Pokémon Single")
                for index, name in enumerate(ENGLISH)
            )  # fmt: skip
        session.add(
            CmProduct(id_product=1, id_expansion=5000, id_metacard=99, name="Pikachu",
                      id_category=SINGLE_CATEGORY, category_name="Pokémon Single")
        )  # fmt: skip
        for language, set_id, names in (
            ("ja", "M6a", [name for _, name in JAPANESE]),
            ("zh-cn", "CSM6aC", CHINESE),
        ):
            card_set = CardSet(
                external_id=set_id, language=language, name="30th", release_date=date(2026, 9, 16)
            )
            session.add(card_set)
            await session.flush()
            session.add_all(
                Card(external_id=f"{set_id}-{number}", language=language, set_id=card_set.id,
                     number=number, number_norm=number.lstrip("0"), name=name)
                for (number, _), name in zip(JAPANESE, names, strict=True)
            )  # fmt: skip
        await session.commit()


async def test_sets_and_cards_are_linked_by_name(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _catalog(session_factory)

    async with session_factory() as session:
        preview = await match_cardmarket(session, dry_run=True)
    assert preview.sets_linked == {"ja": 1, "zh-cn": 1}
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(CardSet.cardmarket_expansion_id).where(CardSet.external_id == "M6a")
            )
            is None
        )  # Probelauf speichert nichts

    async with session_factory() as session:
        report = await match_cardmarket(session)
        await session.commit()

    assert report.cards_linked == {"ja": 7, "zh-cn": 7}
    async with session_factory() as session:
        sets = {
            s.external_id: (s.cardmarket_expansion_id, s.cardmarket_expansion_source)
            for s in (await session.scalars(select(CardSet))).all()
        }
        assert sets == {"M6a": (6602, "matched"), "CSM6aC": (6603, "matched")}
        products = {
            c.number: c.cardmarket_product_id
            for c in (await session.scalars(select(Card).where(Card.language == "ja"))).all()
        }
        # Zweimal „Charizard ex“: Reihenfolge der Nummern = Reihenfolge der Produkte
        assert (products["006"], products["137"]) == (600005, 600006)
        assert products["025"] == 600003
        assert products["099"] is None

    async with session_factory() as session:
        again = await match_cardmarket(session)
    assert (again.sets_linked, again.cards_linked) == ({}, {})


def test_name_key() -> None:
    assert name_key("Charizard ex [Burning Darkness | Explosive Vortex] (V.2)") == "charizardex"
    assert name_key("Charizard-ex") == "charizardex"


async def test_linked_product_gives_price_without_tcgdex(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Karte, die TCGdex nicht kennt, aber über den Namen ein Produkt hat → Preisführer."""
    await _catalog(session_factory)
    async with session_factory() as session:
        await match_cardmarket(session)
        session.add(
            CmPrice(id_product=600003, metrics={"trend": 4.5, "low": 3.0},
                    updated_at=datetime(2026, 10, 23, tzinfo=UTC))
        )  # fmt: skip
        await session.commit()
    async with session_factory() as session:
        pikachu = await session.scalar(
            select(Card).where(Card.language == "ja", Card.number == "025")
        )
        assert pikachu is not None
        quotes = await correct_cardmarket_quotes(session, pikachu, card_ref(pikachu), [])

    assert {(q.source, q.metric, str(q.value)) for q in quotes} >= {("cardmarket", "trend", "4.50")}


async def test_expansion_of_another_set_is_not_taken(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Gehören die Ausgaben schon anderen Sets (z. B. englisches „151“), bleibt das Set offen."""
    await _catalog(session_factory)
    async with session_factory() as session:
        for set_id, expansion in (("sv03.5", 6602), ("sv03.5c", 6603)):
            session.add(
                CardSet(external_id=set_id, language="en", name="151",
                        cardmarket_expansion_id=expansion, cardmarket_expansion_source="tcgdex")
            )  # fmt: skip
        await session.commit()
        report = await match_cardmarket(session, dry_run=True)

    assert report.sets_linked == {}
    assert report.links == []
