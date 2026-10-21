"""Englische Lücken aus pokemontcg.io und daraus abgeleitete deutsche Karten (me55c)."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CardSource
from app.services.card_names import translate_english_name
from app.services.german_import import TRANSLATED_NOTE, import_german
from app.services.ptcg_import import import_ptcg

SETS = [
    {
        "id": "me55c",
        "name": "30th Celebration: Classic Collection",
        "series": "Mega Evolution",
        "total": 3,
        "printedTotal": 30,
        "releaseDate": "2026/09/16",
        "images": {"logo": "https://images.scrydex.com/pokemon/me55c-logo/logo"},
    },
    {"id": "sm35", "name": "Shining Legends", "total": 3},
    {"id": "base1", "name": "Base", "total": 1},
]
CARDS = {
    "me55c": [
        {"id": "me55c-4", "name": "Charizard", "number": "4", "rarity": "Rare Holo",
         "artist": "Mitsuhiro Arita",
         "images": {"large": "https://images.scrydex.com/pokemon/me55c-4/large"}},
        {"id": "me55c-106", "name": "Shining Celebi", "number": "106"},
        {"id": "me55c-106b", "name": "Palkia LV.X", "number": "106"},
    ],
    "sm35": [
        {"id": "sm35-1", "name": "Pinsir", "number": "1"},
        {"id": "sm35-2", "name": "Pinsir-GX", "number": "2"},
        {"id": "sm35-3", "name": "Raikou", "number": "3"},
    ],
}  # fmt: skip


def transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        path = request.url.path
        if path.endswith("/sets/en.json"):
            return httpx.Response(200, json=SETS)
        set_id = path.rsplit("/", 1)[-1].removesuffix(".json")
        if set_id in CARDS:
            return httpx.Response(200, json=CARDS[set_id])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def _shining_legends(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        card_set = CardSet(external_id="sm3.5", language="en", name="Shining Legends")
        base = CardSet(external_id="base1", language="en", name="Base Set")
        session.add_all([card_set, base])
        await session.flush()
        session.add_all(
            [
                Card(
                    external_id="sm3.5-1",
                    language="en",
                    set_id=card_set.id,
                    number="1",
                    number_norm="1",
                    name="Pinsir",
                ),
                Card(
                    external_id="sm3.5-3",
                    language="en",
                    set_id=card_set.id,
                    number="3",
                    number_norm="3",
                    name="Raikou",
                ),
                Card(
                    external_id="base1-4",
                    language="en",
                    set_id=base.id,
                    number="4",
                    number_norm="4",
                    name="Charizard",
                ),
            ]
        )
        await session.commit()


async def test_missing_sets_and_cards_are_added(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await _shining_legends(session_factory)
    calls: list[str] = []

    preview = await import_ptcg(session_factory, settings, dry_run=True, transport=transport(calls))
    assert preview.added == 4
    report = await import_ptcg(session_factory, settings, transport=transport(calls))

    assert {(c.set_id, c.created, c.added) for c in report.changes} == {
        ("me55c", True, 3),
        ("sm3.5", False, 1),  # nur Pinsir-GX fehlte (Name verglichen)
    }
    assert not any("base1.json" in call for call in calls)  # vollständig → nicht geladen
    async with session_factory() as session:
        charizard = await session.scalar(select(Card).where(Card.external_id == "me55c-4"))
        assert charizard is not None
        assert (charizard.source, charizard.illustrator) == (
            CardSource.POKEMONTCG,
            "Mitsuhiro Arita",
        )
        assert charizard.card_set.name == "30th Celebration: Classic Collection"
        assert str(charizard.card_set.release_date) == "2026-09-16"
        gx = await session.scalar(select(Card).where(Card.name == "Pinsir-GX"))
        assert gx is not None and gx.external_id == "sm3.5-2"  # TCGdex-Schema des Sets
        shared = (await session.scalars(select(Card).where(Card.number == "106"))).all()
        assert len(shared) == 2  # gleiche Nummer, verschiedene Karten (Nachdruck-Set)

    again = await import_ptcg(session_factory, settings, transport=transport(calls))
    assert again.added == 0


async def test_german_cards_are_derived_for_known_german_release(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    calls: list[str] = []
    await import_ptcg(session_factory, settings, transport=transport(calls))

    def no_wiki(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"search": []}})

    report = await import_german(
        session_factory, settings, transport=httpx.MockTransport(no_wiki), pause=0
    )

    me55c = next(result for result in report.sets if result.set_id == "me55c")
    assert (me55c.added, me55c.note) == (3, TRANSLATED_NOTE)
    async with session_factory() as session:
        glurak = await session.scalar(
            select(Card).where(Card.external_id == "me55c-4", Card.language == "de")
        )
        assert glurak is not None
        assert (glurak.name, glurak.number, glurak.source) == ("Glurak", "4", CardSource.TRANSLATED)
        assert glurak.image_url == "https://images.scrydex.com/pokemon/me55c-4/large"


def test_translate_english_name() -> None:
    assert translate_english_name("Charizard") == "Glurak"
    assert translate_english_name("Erika's Jigglypuff") == "Erikas Pummeluff"
    assert translate_english_name("Dark Tyranitar") == "Dunkles Despotar"
    assert translate_english_name("N") == "N"
