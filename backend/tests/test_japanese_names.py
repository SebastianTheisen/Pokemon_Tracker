"""Englische Namen japanischer Trainer aus Cardmarket („ナンジャモ“ → „Iono“)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, CmProduct
from app.schemas.catalog import CardOut
from app.services.display_names import card_display_name
from app.services.japanese_names import fill_english_names


async def test_trainer_names_from_cardmarket(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                CmProduct(id_product=1, id_expansion=1, id_metacard=1, name="Iono (V.2)"),
                CmProduct(id_product=2, id_expansion=1, id_metacard=2, name="Espeon V"),
            ]
        )
        card_set = CardSet(external_id="SV2a", language="ja", name="ポケモンカード151")
        session.add(card_set)
        await session.flush()
        iono = Card(
            external_id="SV2a-096", language="ja", set_id=card_set.id, number="096",
            number_norm="96", name="ナンジャモ", cardmarket_product_id=1,
        )  # fmt: skip
        espeon = Card(
            external_id="SV2a-081", language="ja", set_id=card_set.id, number="081",
            number_norm="81", name="エーフィV", cardmarket_product_id=2,
        )  # fmt: skip
        session.add_all([iono, espeon])
        await session.commit()

        assert await fill_english_names(session) == 2
        await session.commit()
        await session.refresh(iono)
        await session.refresh(espeon)
        assert iono.name_en == "Iono"
        assert CardOut.model_validate(iono).translated_name == "Iono"
        assert card_display_name(iono) == "Iono"
        # Pokémon: weiter der deutsche Name aus der eigenen Übersetzung
        assert CardOut.model_validate(espeon).translated_name == "Psiana V"
        assert await fill_english_names(session) == 0  # nur leere Namen


def test_matching_uses_tcgplayer_english_name() -> None:
    """Japanische Trainer ohne Pokédex-Übersetzung: Cardmarket-Zuordnung über ``name_en``."""
    from app.services.cardmarket_matching import english_name  # noqa: PLC0415

    assert english_name("ナンジャモ", "ja", None) is None
    assert english_name("ナンジャモ", "ja", None, "Iono") == "Iono"
    assert english_name("エーフィV", "ja", None, "Espeon V") == "Espeon V"
