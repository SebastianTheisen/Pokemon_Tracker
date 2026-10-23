"""Katalog: Import aus (simuliertem) TCGdex und Suche – Service und API."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, CardSource
from app.providers.tcgdex import TcgdexClient
from app.services.catalog_search import search_cards
from app.services.catalog_sync import LanguageReport, remove_digital_sets, sync_catalog
from tests.conftest import RegisterUser
from tests.fake_tcgdex import FakeTcgdex

API = "/api/v1"
LANGUAGES = ["de", "en", "ja"]


async def _sync(
    fake: FakeTcgdex,
    factory: async_sessionmaker[AsyncSession],
    *,
    full: bool = False,
    languages: list[str] | None = None,
) -> list[LanguageReport]:
    async with TcgdexClient(
        base_url="https://api.tcgdex.net/v2", user_agent="test", transport=fake.transport()
    ) as client:
        return await sync_catalog(client, factory, languages or LANGUAGES, full=full)


@pytest.fixture
async def synced(session_factory: async_sessionmaker[AsyncSession]) -> FakeTcgdex:
    fake = FakeTcgdex()
    await _sync(fake, session_factory)
    return fake


# --------------------------------------------------------------------------- Import


async def test_sync_imports_sets_and_cards_per_language(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    reports = await _sync(FakeTcgdex(), session_factory)

    assert [(r.language, r.sets_synced, r.cards_upserted, r.errors) for r in reports] == [
        ("de", 1, 4, []),
        ("en", 1, 4, []),
        ("ja", 2, 3, []),  # inkl. Set „SM1+“ (Sonderzeichen in der ID)
    ]
    async with session_factory() as session:
        card = await session.scalar(
            select(Card).where(Card.external_id == "swsh7-215", Card.language == "de")
        )
        assert card is not None
        assert (card.name, card.number, card.number_norm) == ("Nachtara VMAX", "215", "215")
        assert card.image_url == "https://assets.tcgdex.net/de/swsh/swsh7/215"
        assert card.card_set.name == "Drachenwandel"
        assert str(card.card_set.release_date) == "2021-08-27"


async def test_second_sync_skips_complete_sets_and_updates_changed_ones(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    synced.set_requests.clear()
    reports = await _sync(synced, session_factory)
    assert synced.set_requests == []
    assert all(r.sets_skipped == r.sets_total for r in reports)

    # Neues Set-Mitglied in DE → nur dieses Set wird neu geladen.
    synced.catalog["de"]["swsh7"]["cards"].append(
        {"id": "swsh7-216", "localId": "216", "name": "Neue Karte", "image": None}
    )
    synced.catalog["de"]["swsh7"]["cardCount"]["total"] = 5
    await _sync(synced, session_factory)
    assert synced.set_requests == ["de/swsh7"]

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(Card))
    assert count == 12


async def test_full_sync_updates_names_without_duplicates(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    synced.catalog["de"]["swsh7"]["cards"][2]["name"] = "Nachtara-VMAX (korrigiert)"

    await _sync(synced, session_factory, full=True)

    async with session_factory() as session:
        names = (
            await session.scalars(
                select(Card.name).where(Card.external_id == "swsh7-215", Card.language == "de")
            )
        ).all()
        assert names == ["Nachtara-VMAX (korrigiert)"]
        assert await session.scalar(select(func.count()).select_from(CardSet)) == 4


async def test_failing_set_is_reported_and_others_continue(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake = FakeTcgdex()
    fake.failing_sets.add("S12")

    reports = await _sync(fake, session_factory)

    ja = next(r for r in reports if r.language == "ja")
    assert ja.sets_synced == 1  # SM1+ klappt, S12 schlägt fehl
    assert len(ja.errors) == 1
    assert all(not r.errors for r in reports if r.language != "ja")


async def test_sync_never_touches_user_created_cards(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    async with session_factory() as session:
        card_set = await session.scalar(select(CardSet).where(CardSet.external_id == "S12"))
        assert card_set is not None
        session.add(
            Card(
                language="ja",
                set_id=card_set.id,
                number="999",
                number_norm="999",
                name="Eigene Karte",
                source=CardSource.USER,
            )
        )
        await session.commit()

    await _sync(synced, session_factory, full=True)

    async with session_factory() as session:
        own = await session.scalar(select(Card).where(Card.source == CardSource.USER))
    assert own is not None
    assert own.name == "Eigene Karte"


# ---------------------------------------------------------------------------- Suche


async def _search(
    factory: async_sessionmaker[AsyncSession], query: str, language: str | None = None
) -> list[tuple[str, str, str]]:
    async with factory() as session:
        hits = await search_cards(session, query, language=language)
    return [(h.card.language, h.card.name, h.card.number) for h in hits]


async def test_search_name_and_number_finds_card_in_all_languages(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    results = await _search(session_factory, "nachtara 215")

    assert results[0] == ("de", "Nachtara VMAX", "215")
    assert ("en", "Umbreon VMAX", "215") in results
    assert all(number == "215" for _, _, number in results)


async def test_search_with_english_name_finds_german_card(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    results = await _search(session_factory, "umbreon 215", language="de")

    assert results == [("de", "Nachtara VMAX", "215")]


async def test_search_tolerates_typos_and_case(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    assert ("de", "Nachtara VMAX", "215") in await _search(session_factory, "NACHTRA 215")


async def test_search_name_only_returns_all_prints(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    results = await _search(session_factory, "nachtara", language="de")

    assert sorted(number for _, _, number in results) == ["095", "188", "215"]


async def test_search_number_only_and_leading_zeros(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    results = await _search(session_factory, "7")

    assert sorted(results) == [("de", "Glurak", "007"), ("en", "Charizard", "007")]


async def test_search_japanese_name(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    assert await _search(session_factory, "ルギアV 110") == [("ja", "ルギアV", "110")]


async def test_search_without_match_or_with_like_wildcards(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    assert await _search(session_factory, "gibtsnicht") == []
    assert await _search(session_factory, "%") == []
    assert await _search(session_factory, "   ") == []


# ------------------------------------------------------------------------------ API


async def test_search_api_requires_login(client: AsyncClient) -> None:
    response = await client.get(f"{API}/cards/search", params={"q": "nachtara"})

    assert response.status_code == 401


async def test_search_and_detail_api(
    client: AsyncClient, register_user: RegisterUser, synced: FakeTcgdex
) -> None:
    user = await register_user("max@example.com")

    response = await client.get(
        f"{API}/cards/search", params={"q": "nachtara 215", "language": "de"}, headers=user.headers
    )
    assert response.status_code == 200
    hits = response.json()
    assert len(hits) == 1
    card = hits[0]["card"]
    assert card["name"] == "Nachtara VMAX"
    assert card["card_set"]["name"] == "Drachenwandel"
    assert 0 < hits[0]["score"] <= 1

    detail = await client.get(f"{API}/cards/{card['id']}", headers=user.headers)
    assert detail.status_code == 200
    assert detail.json()["external_id"] == "swsh7-215"

    sets = await client.get(f"{API}/sets", params={"language": "ja"}, headers=user.headers)
    assert [s["external_id"] for s in sets.json()] == ["S12", "SM1+"]


async def test_search_api_validates_language(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")

    response = await client.get(
        f"{API}/cards/search", params={"q": "x", "language": "xx"}, headers=user.headers
    )

    assert response.status_code == 422


async def test_set_ids_with_special_characters_are_url_encoded(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    assert "ja/SM1+" in synced.set_requests
    assert await _search(session_factory, "モクロー 1") == [("ja", "モクロー", "001")]


async def test_sets_with_fewer_delivered_than_announced_cards_are_not_refetched(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Wie bei vielen JP/KO-Sets: TCGdex meldet 100 Karten, liefert aber nur 2."""
    fake = FakeTcgdex()
    fake.catalog["ja"]["S12"]["cardCount"]["total"] = 100
    await _sync(fake, session_factory, languages=["ja"])

    fake.set_requests.clear()
    reports = await _sync(fake, session_factory, languages=["ja"])

    assert fake.set_requests == []
    assert reports[0].sets_skipped == reports[0].sets_total


async def test_missing_images_use_other_language_of_same_card(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from sqlalchemy import select  # noqa: PLC0415

    from app.models import Card  # noqa: PLC0415
    from app.services.catalog_sync import fill_image_fallbacks  # noqa: PLC0415
    from tests.pricing_helpers import make_card  # noqa: PLC0415

    english = await make_card(
        session_factory, external_id="swsh7-215", name="Umbreon VMAX", language="en"
    )
    german = await make_card(
        session_factory, external_id="swsh7-215", name="Nachtara VMAX", language="de"
    )
    lonely = await make_card(session_factory, external_id="xy1-1", name="Bisasam", language="de")
    async with session_factory() as session:
        en = await session.get(Card, english.id)
        assert en is not None
        en.image_url = "https://assets.tcgdex.net/en/swsh/swsh7/215"
        await session.commit()

        assert await fill_image_fallbacks(session) == 1
        await session.commit()
        rows = {
            card.id: card
            for card in (
                await session.scalars(select(Card).where(Card.id.in_([german.id, lonely.id])))
            ).all()
        }
    assert rows[german.id].image_url == "https://assets.tcgdex.net/en/swsh/swsh7/215"
    assert rows[german.id].image_language == "en"
    assert rows[lonely.id].image_url is None


# ------------------------------------------------------------- Pocket (Handyspiel)


def _pocket_set(set_id: str, cards: int) -> dict[str, object]:
    """Pocket-Set wie bei TCGdex: Serie ``tcgp``."""
    return {
        "id": set_id,
        "name": "Genetic Apex",
        "cardCount": {"total": cards, "official": cards},
        "serie": {"id": "tcgp", "name": "Pokémon TCG Pocket"},
        "releaseDate": "2024-10-30",
        "cards": [
            {"id": f"{set_id}-{i:03}", "localId": f"{i:03}", "name": f"Pocket {i}"}
            for i in range(1, cards + 1)
        ],
    }


async def test_pocket_sets_are_not_imported(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake = FakeTcgdex()
    fake.catalog["en"]["A1"] = _pocket_set("A1", 3)

    reports = await _sync(fake, session_factory, languages=["en"])

    assert (reports[0].sets_synced, reports[0].sets_digital) == (1, 1)
    async with session_factory() as session:
        assert await session.scalar(select(CardSet).where(CardSet.external_id == "A1")) is None


async def test_stored_pocket_sets_are_removed_except_collection_cards(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    register_user: RegisterUser,
    synced: FakeTcgdex,
) -> None:
    # Stand vor dieser Änderung: Pocket-Set wurde wie jedes andere gespeichert.
    async with session_factory() as session:
        pocket = CardSet(
            external_id="A1", language="en", name="Genetic Apex", series_name="Pokémon TCG Pocket"
        )
        session.add(pocket)
        await session.flush()
        cards = [
            Card(
                external_id=f"A1-00{i}",
                language="en",
                set_id=pocket.id,
                number=f"00{i}",
                number_norm=str(i),
                name=f"Pocket {i}",
                source=CardSource.TCGDEX,
            )
            for i in (1, 2, 3)
        ]
        session.add_all(cards)
        await session.commit()
        owned_id = cards[0].id
    user = await register_user("pocket@example.com")
    added = await client.post(
        f"{API}/collection/items", json={"card_id": str(owned_id)}, headers=user.headers
    )
    assert added.status_code == 201, added.text

    async with session_factory() as session:
        preview = await remove_digital_sets(session, dry_run=True)
        assert (len(preview.sets), preview.cards_removed, preview.cards_kept) == (1, 2, 1)
        assert await session.scalar(select(func.count()).select_from(Card)) == 14  # unverändert

    await _sync(synced, session_factory)  # Bereinigung läuft nach jedem Import

    async with session_factory() as session:
        remaining = (await session.scalars(select(Card.name).where(Card.set_id == pocket.id))).all()
        assert remaining == ["Pocket 1"]  # liegt in einer Sammlung → bleibt samt Set
        assert await session.get(CardSet, pocket.id) is not None
        assert await session.scalar(select(func.count()).select_from(Card)) == 12


# ------------------------------------------------- Setkürzel und doppelte Sets


async def test_search_by_set_code_and_number(
    session_factory: async_sessionmaker[AsyncSession], synced: FakeTcgdex
) -> None:
    async with session_factory() as session:
        for card_set in (await session.scalars(select(CardSet))).all():
            if card_set.external_id == "swsh7":
                card_set.code = "EVS"
        await session.commit()

    assert sorted(await _search(session_factory, "EVS215")) == [
        ("de", "Nachtara VMAX", "215"),
        ("en", "Umbreon VMAX", "215"),
    ]
    assert await _search(session_factory, "evs 215", language="de") == [
        ("de", "Nachtara VMAX", "215")
    ]
    assert await _search(session_factory, "swsh7-215", language="en") == [
        ("en", "Umbreon VMAX", "215")
    ]
    assert await _search(session_factory, "EVS999") == []


def _thirty(set_id: str, name: str, cards: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "id": set_id,
        "name": name,
        "cardCount": {"total": len(cards), "official": len(cards)},
        "serie": {"id": "me", "name": "Mega-Entwicklung"},
        "releaseDate": "2026-09-17",
        "cards": [
            {"id": f"{set_id}-{number}", "localId": number, "name": card} for number, card in cards
        ],
    }


async def test_tcgdex_duplicate_of_imported_set_is_merged(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TCGdex legt ein Set an, das schon aus pokemontcg.io kam (eigene ID, mit Bildern)."""
    async with session_factory() as session:
        imported = CardSet(
            external_id="me55c",
            language="de",
            name="30th Celebration: Classic Collection",
            release_date=date(2026, 9, 16),
        )
        session.add(imported)
        await session.flush()
        session.add_all(
            [
                Card(external_id=f"me55c-{n}", language="de", set_id=imported.id, number=n,
                     number_norm=n, name=name, source=CardSource.TRANSLATED,
                     image_url=f"https://images.scrydex.com/pokemon/me55c-{n}/large")
                for n, name in (("4", "Glurak"), ("58", "Pikachu"), ("43", "Selfe"))
            ]
        )  # fmt: skip
        await session.commit()
    fake = FakeTcgdex()
    fake.catalog["de"] = {
        "me02.5": _thirty(
            "me02.5",
            "30 Jahre: Klassische Sammlung",
            [("001", "Glurak"), ("002", "Pikachu"), ("003", "Selfe")],
        )
    }

    reports = await _sync(fake, session_factory, languages=["de"])

    assert reports[0].sets_duplicate == 1
    async with session_factory() as session:
        assert await session.scalar(select(CardSet).where(CardSet.external_id == "me02.5")) is None
        kept = await session.scalar(select(CardSet).where(CardSet.external_id == "me55c"))
        assert kept is not None and kept.name == "30 Jahre: Klassische Sammlung"
        numbers = sorted(
            (await session.scalars(select(Card.number).where(Card.set_id == kept.id))).all()
        )
        assert numbers == ["4", "43", "58"]  # aufgedruckte Nummern bleiben
