"""Offene Cardmarket-Zuordnungen nachträglich (Collectr-Import 29.10.: 27 Karten offen)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, CmExpansion, CmProduct
from app.services.cardmarket_catalog import SINGLE_CATEGORY
from app.services.cardmarket_rescue import (
    _Open,
    pick_group,
    pick_product,
    render_rescue_report,
    rescue_cardmarket,
)


def test_pick_product_rules() -> None:
    assert pick_product("89", 63, [10, 20], [20]) == 20  # nur eines frei
    assert pick_product("89", 63, [10, 20], [10, 20]) == 20  # Secret Rare → letztes
    assert pick_product("12", 63, [10, 20], [10, 20]) == 10  # regulär → erstes
    assert pick_product("12", None, [10, 20], [10, 20]) is None  # ohne Setgröße unsicher
    assert pick_product("12", 63, [], []) is None


def product(pid: int, expansion: int, name: str) -> CmProduct:
    return CmProduct(
        id_product=pid,
        id_expansion=expansion,
        id_metacard=pid,
        name=name,
        id_category=SINGLE_CATEGORY,
    )


async def test_rescue_secret_rare_and_small_set(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        # SV9a: „Ethan's Adventure“ normal (verknüpft) und SAR (offen) – Namen doppelt
        session.add(CmExpansion(id_expansion=1, product_count=3, first_added=date(2025, 1, 24)))
        session.add_all(
            [
                product(100, 1, "Ethan's Adventure"),
                product(101, 1, "Pikachu"),
                product(150, 1, "Ethan's Adventure (V.2)"),
            ]
        )
        sv9a = CardSet(
            external_id="SV9a", language="ja", name="熱風のアリーナ",
            card_count_official=63, cardmarket_expansion_id=1,
            release_date=date(2025, 1, 24),
        )  # fmt: skip
        # CP5: Set ohne Ausgabe, klein; Ausgabe 2 enthält alle Namen
        session.add(CmExpansion(id_expansion=2, product_count=4, first_added=date(2016, 9, 1)))
        session.add_all(
            [
                product(200, 2, "Mew"),
                product(201, 2, "Keldeo"),
                product(202, 2, "Dedenne"),
                product(203, 2, "Pikachu"),
            ]
        )
        cp5 = CardSet(external_id="CP5", language="ja", name="CP5", release_date=date(2016, 9, 2))
        session.add_all([sv9a, cp5])
        await session.flush()
        session.add_all(
            [
                Card(external_id="SV9a-063", language="ja", set_id=sv9a.id, number="063",
                     number_norm="63", name="ヒビキの冒険", name_en="Ethan's Adventure",
                     cardmarket_product_id=100),
                Card(external_id="SV9a-089", language="ja", set_id=sv9a.id, number="089",
                     number_norm="89", name="ヒビキの冒険", name_en="Ethan's Adventure"),
            ]
            + [
                Card(external_id=f"CP5-{n}", language="ja", set_id=cp5.id, number=f"{n:03d}",
                     number_norm=str(n), name=name, name_en=en)
                for n, name, en in ((16, "ミュウ", "Mew"), (14, "ケルディオ", "Keldeo"),
                                    (12, "デデンネ", "Dedenne"))
            ]
        )  # fmt: skip
        await session.commit()

        dry = await rescue_cardmarket(session)
        assert dry.dry_run and len(dry.cards) == 4 and len(dry.sets) == 1
        text = render_rescue_report(dry)
        assert "SV9a 89" in text and "150" in text  # SAR → späteres Produkt
        assert (await session.get(CardSet, cp5.id)).cardmarket_expansion_id is None  # type: ignore[union-attr]

        applied = await rescue_cardmarket(session, dry_run=False)
        await session.commit()
        assert len(applied.cards) == 4
        links = dict((await session.execute(select(Card.number, Card.cardmarket_product_id))).all())
        assert links["089"] == 150
        assert {links["016"], links["014"], links["012"]} == {200, 201, 202}
        assert (await session.get(CardSet, cp5.id)).cardmarket_expansion_id == 2  # type: ignore[union-attr]


def test_pick_group_secret_rares() -> None:
    """SV9a: Ho-Oh ex 86 (SR) und 90 (SAR) offen, drei Produkte (normal, SR, SAR)."""

    def card(number: str) -> _Open:
        return _Open(id=uuid.uuid4(), set_id=uuid.uuid4(), number=number, name="x", key="x")

    sr, sar = card("86"), card("90")
    assert [(c.number, p) for c, p in pick_group([sar, sr], 63, [10, 20, 30])] == [
        ("86", 20),
        ("90", 30),
    ]
    assert [p for _, p in pick_group([card("12"), card("13")], 63, [5, 6, 7])] == [5, 6]
    assert pick_group([card("12"), card("90")], 63, [5, 6, 7]) == []  # gemischt → offen
    assert pick_group([sr, sar], None, [10, 20, 30]) == []  # ohne Setgröße offen
