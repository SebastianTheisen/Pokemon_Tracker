"""Kartendetails aus TCGdex: Einlesen, Hintergrund-Abgleich, Ausgabe in der API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card
from app.providers.tcgdex import TcgdexClient, TcgdexError
from app.services.card_details import parse_details, sync_card_details
from tests.conftest import RegisterUser
from tests.pricing_helpers import make_card

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)
DETAILS: dict[str, Any] = {
    "id": "swsh7-215",
    "rarity": "Secret Rare",
    "illustrator": "Ryota Murayama",
    "variants": {"normal": False, "reverse": False, "holo": True, "firstEdition": False},
    "pricing": {"cardmarket": {"idProduct": 574273}},
}


class FakeTcgdex:
    """Antworten je (Sprache, Karten-ID): Daten, 404 oder Serverfehler."""

    def __init__(self, answers: dict[tuple[str, str], dict[str, Any] | int]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    async def get_card(self, language: str, card_id: str) -> dict[str, object]:
        self.calls.append((language, card_id))
        answer = self.answers.get((language, card_id), 404)
        if isinstance(answer, int):
            raise TcgdexError(f"HTTP {answer}", status_code=answer)
        return answer


def test_parse_details_keeps_known_fields_only() -> None:
    details = parse_details(DETAILS)
    junk = parse_details({"rarity": "  ", "variants": "kaputt", "illustrator": 3})

    assert (details.rarity, details.illustrator, details.cardmarket_product_id) == (
        "Secret Rare",
        "Ryota Murayama",
        574273,
    )
    assert details.variants == {
        "normal": False,
        "reverse": False,
        "holo": True,
        "firstEdition": False,
    }
    assert (junk.rarity, junk.variants, junk.illustrator, junk.cardmarket_product_id) == (
        None,
        None,
        None,
        None,
    )


async def test_sync_updates_marks_unknown_and_retries_failures(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    german = await make_card(session_factory, external_id="swsh7-215", language="de")
    english = await make_card(session_factory, external_id="gone-1", language="en")
    japanese = await make_card(session_factory, external_id="sv2a-1", language="ja")
    await make_card(session_factory, external_id=None, name="Eigene Karte")  # selbst angelegt
    fake = FakeTcgdex({("de", "swsh7-215"): DETAILS, ("ja", "sv2a-1"): 500})

    report = await sync_card_details(session_factory, cast(TcgdexClient, fake), clock=lambda: NOW)

    assert (report.pending, report.updated, report.not_found, report.failed) == (3, 1, 1, 1)
    async with session_factory() as session:
        card = await session.get_one(Card, german.id)
        assert (card.rarity, card.illustrator, (card.variants or {}).get("holo")) == (
            "Secret Rare",
            "Ryota Murayama",
            True,
        )
        assert card.cardmarket_product_id == 574273
        assert card.details_synced_at == NOW
        assert (await session.get_one(Card, english.id)).details_synced_at == NOW
        assert (await session.get_one(Card, japanese.id)).details_synced_at is None

    fake.calls.clear()
    again = await sync_card_details(session_factory, cast(TcgdexClient, fake), clock=lambda: NOW)
    assert (again.pending, fake.calls) == (1, [("ja", "sv2a-1")])


async def test_limit_takes_german_first(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await make_card(session_factory, external_id="a-1", language="en")
    await make_card(session_factory, external_id="b-1", language="ja")
    await make_card(session_factory, external_id="c-1", language="de")
    fake = FakeTcgdex({})

    await sync_card_details(session_factory, cast(TcgdexClient, fake), limit=1)

    assert fake.calls == [("de", "c-1")]


async def test_card_api_shows_details(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    await sync_card_details(
        session_factory,
        cast(TcgdexClient, FakeTcgdex({("de", "swsh7-215"): DETAILS})),
        clock=lambda: NOW,
    )

    body = (await client.get(f"/api/v1/cards/{card.id}", headers=user.headers)).json()

    assert (body["rarity"], body["illustrator"]) == ("Secret Rare", "Ryota Murayama")
    assert body["variants"] == {
        "normal": False,
        "reverse": False,
        "holo": True,
        "firstEdition": False,
    }
