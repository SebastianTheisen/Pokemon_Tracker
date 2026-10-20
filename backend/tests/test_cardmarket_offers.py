"""Selbst ausgelesene Cardmarket-Angebote: Auswertung, Vorschau und Speichern."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card
from app.services.cardmarket_offers import (
    OfferRow,
    evaluate_offers,
    label_language,
    page_filters,
    parse_price,
)
from app.services.errors import InvalidInputError
from tests.conftest import RegisterUser
from tests.pricing_helpers import FakeProvider, cardmarket, make_card

API = "/api/v1"
PAGE = (
    "https://www.cardmarket.com/de/Pokemon/Products/Singles/Evolving-Skies/Umbreon-VMAX-V2-EVS215"
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234,56 €", Decimal("1234.56")),
        ("0,02 €", Decimal("0.02")),
        ("12,50€", Decimal("12.50")),
        ("€1,234.56", Decimal("1234.56")),
        ("3.50", Decimal("3.50")),
        ("1.000 €", Decimal("1000.00")),
        ("ab 7 €", Decimal("7.00")),
        ("kein Preis", None),
        ("0,00 €", None),
    ],
)
def test_parse_price(text: str, expected: Decimal | None) -> None:
    assert parse_price(text) == expected


def test_label_language_and_page_filters() -> None:
    assert label_language(["Deutsch"]) == "de"
    assert label_language(["Sprache: German"]) == "de"
    assert label_language(["Reverse Holo", "Japanisch"]) == "ja"
    assert label_language(["Französisch"]) == "other"
    assert label_language(["Reverse Holo"]) is None
    assert page_filters(f"{PAGE}?language=3&minCondition=2") == ("de", "NM")
    assert page_filters(f"{PAGE}?language=1,3") == (None, None)  # mehrere Sprachen
    assert page_filters(PAGE) == (None, None)


def _card(language: str = "de") -> Card:
    return Card(language=language, name="Nachtara VMAX", number="215", number_norm="215")


def test_evaluate_offers_per_condition_or_better() -> None:
    rows = [
        OfferRow("EX", "150,00 €", ("Deutsch",)),
        OfferRow("NM", "180,00 €", ("Deutsch",)),
        OfferRow("NM", "170,00 €", ("Englisch",)),  # andere Sprache
        OfferRow("NM", "185,00 €", ("Deutsch",)),
        OfferRow("MT", "200,00 €", ("Deutsch",)),
        OfferRow("NM", "90,00 €", ("Deutsch", "Signiert")),  # zählt nicht
        OfferRow("NM", "40,00 €", ("Deutsch", "Reverse Holo")),
        OfferRow("??", "1,00 €", ("Deutsch",)),
    ]

    result = evaluate_offers(_card(), f"{PAGE}#kartenkiste=abc", rows)

    assert (result.accepted, result.skipped) == (5, 3)
    assert result.page_url == PAGE  # ohne Sprungmarke
    by_key = {(p.variant, p.condition): p for p in result.prices}
    assert by_key[("normal", "MT")].low == Decimal("200.00")
    nm = by_key[("normal", "NM")]
    assert (nm.low, nm.low3, nm.offers) == (Decimal("180.00"), Decimal("188.33"), 3)
    ex = by_key[("normal", "EX")]
    assert (ex.low, ex.offers) == (Decimal("150.00"), 4)
    assert by_key[("normal", "PO")].low == Decimal("150.00")  # „PO oder besser“
    assert by_key[("reverse", "NM")].low == Decimal("40.00")
    assert ("reverse", "MT") not in by_key


def test_evaluate_offers_respects_page_filters() -> None:
    rows = [OfferRow("NM", "10,00 €"), OfferRow("MT", "12,00 €")]  # ohne Sprachsymbol

    result = evaluate_offers(_card(), f"{PAGE}?language=3&minCondition=2", rows)

    # Sprache aus dem Seitenfilter; schlechtere Zustände als NM waren ausgeblendet.
    assert [(p.condition, p.low) for p in result.prices] == [
        ("MT", Decimal("12.00")),
        ("NM", Decimal("10.00")),
    ]
    wrong = evaluate_offers(_card("en"), f"{PAGE}?language=3", rows)
    assert wrong.accepted == 0
    assert len(wrong.warnings) == 2  # andere Sprache + nichts gefunden


def test_only_cardmarket_pages() -> None:
    with pytest.raises(InvalidInputError):
        evaluate_offers(_card(), "https://example.com/?language=3", [])
    with pytest.raises(InvalidInputError):
        evaluate_offers(_card(), "http://www.cardmarket.com/de/Pokemon", [])


async def test_api_preview_then_save_becomes_condition_price(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    price_provider.quotes = [cardmarket("trend", "200")]
    body = {
        "page_url": f"{PAGE}?language=3&minCondition=3",
        "rows": [
            {"condition": "NM", "price": "180,00 €", "labels": ["Deutsch"]},
            {"condition": "EX", "price": "150,00 €", "labels": ["Deutsch"]},
        ],
    }

    preview = await client.post(
        f"{API}/cards/{card.id}/cardmarket-offers", json=body, headers=user.headers
    )
    assert preview.status_code == 200
    assert preview.json()["saved"] == 0
    # Kein MT-Angebot → kein MT-Preis; schlechter als EX war per Filter ausgeblendet.
    assert [(p["condition"], p["low"]) for p in preview.json()["prices"]] == [
        ("NM", "180.00"),
        ("EX", "150.00"),
    ]
    prices = (await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)).json()
    nm = next(c for c in prices["conditions"] if c["condition"] == "NM")
    assert nm["kind"] == "estimated"  # Vorschau speichert nichts

    saved = await client.post(
        f"{API}/cards/{card.id}/cardmarket-offers",
        json={**body, "save": True},
        headers=user.headers,
    )
    assert saved.json()["saved"] == 4  # NM und EX, je low + low3

    prices = (await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)).json()
    by_condition = {c["condition"]: c for c in prices["conditions"] if c["variant"] == "normal"}
    assert (by_condition["NM"]["kind"], by_condition["NM"]["value"]) == ("external", "180.00")
    assert by_condition["NM"]["source"] == "cardmarket_offers"
    assert by_condition["NM"]["url"] == f"{PAGE}?language=3&minCondition=3"
    assert by_condition["EX"]["value"] == "150.00"
    assert by_condition["GD"]["kind"] == "estimated"  # nicht ausgelesen → Schätzung


async def test_api_rejects_foreign_pages(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    response = await client.post(
        f"{API}/cards/{card.id}/cardmarket-offers",
        json={"page_url": "https://evil.example/", "rows": []},
        headers=user.headers,
    )
    assert response.status_code == 400
    unauthenticated = await client.post(
        f"{API}/cards/{card.id}/cardmarket-offers", json={"page_url": PAGE, "rows": []}
    )
    assert unauthenticated.status_code == 401


async def test_saving_from_product_page_corrects_cardmarket_link(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    """TCGdex verweist auf die falsche Ausgabe → ausgelesene Seite gilt künftig für die Karte."""
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    price_provider.quotes = [cardmarket("trend", "76.19")]  # Wert der falschen Ausgabe
    product = (
        "https://www.cardmarket.com/de/Pokemon/Products/Singles/30th-Celebration/Charizard-M6a137"
    )
    body = {
        "page_url": f"{product}?language=3&minCondition=2#kartenkiste={card.id}",
        "rows": [{"condition": "NM", "price": "120,00 €", "labels": ["Deutsch"]}],
        "save": True,
        "remember_page": True,
    }

    saved = await client.post(
        f"{API}/cards/{card.id}/cardmarket-offers", json=body, headers=user.headers
    )
    assert saved.status_code == 200, saved.text

    prices = (await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)).json()
    assert prices["cardmarket_link"] == product
    assert all(offer["source"] != "cardmarket" for offer in prices["offers"])
    nm = next(c for c in prices["conditions"] if c["condition"] == "NM")
    assert (nm["value"], nm["source"]) == ("120.00", "cardmarket_offers")
    assert not any(c["kind"] == "estimated" for c in prices["conditions"])  # keine 76,19 €


async def test_price_target_roundtrip(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    empty = await client.get(f"{API}/me/price-target", headers=user.headers)
    assert empty.json() == {"card_id": None}

    await client.put(f"{API}/me/price-target", json={"card_id": str(card.id)}, headers=user.headers)

    current = await client.get(f"{API}/me/price-target", headers=user.headers)
    assert current.json() == {"card_id": str(card.id)}
