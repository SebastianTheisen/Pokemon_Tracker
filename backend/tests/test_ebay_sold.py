"""Selbst ausgelesene eBay-Verkäufe: Auswertung, Vorschau, Speichern, Wert gegradeter Karten."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card
from app.services.ebay_sold import (
    SoldRow,
    evaluate_sold,
    graded_variant,
    grading_group,
    parse_sold_date,
)
from app.services.errors import InvalidInputError
from tests.conftest import RegisterUser
from tests.pricing_helpers import make_card

API = "/api/v1"
PAGE = "https://www.ebay.de/sch/i.html?_nkw=Nachtara+VMAX+215&LH_Sold=1&LH_Complete=1"
TODAY = date(2026, 10, 18)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Verkauft  12. Okt 2026", date(2026, 10, 12)),
        ("Verkauft 3. Mär. 2026", date(2026, 3, 3)),
        ("Sold Oct 12, 2026", date(2026, 10, 12)),
        ("Verkauft 01.09.2026", date(2026, 9, 1)),
        ("Verkauft 12. Okt 2027", None),  # Zukunft
        ("gestern", None),
    ],
)
def test_parse_sold_date(text: str, expected: date | None) -> None:
    assert parse_sold_date(text, today=TODAY) == expected


@pytest.mark.parametrize(
    ("title", "group"),
    [
        ("Pokemon Nachtara VMAX 215/203 PSA 10 Gem Mint", "PSA 10"),
        ("Umbreon VMAX 215 Beckett 9.5", "BGS 9.5"),
        ("Nachtara VMAX 215/203 CGC 9,5", "CGC 9.5"),
        ("Nachtara VMAX 215/203 Drachenwandel NM", "raw"),
        ("PSA GEM MT 10 Umbreon VMAX 215", "PSA 10"),
    ],
)
def test_grading_group(title: str, group: str) -> None:
    assert grading_group(title) == group


def test_graded_variant() -> None:
    assert graded_variant("PSA", "10") == "graded:PSA 10"
    assert graded_variant("CGC", "9,5") == "graded:CGC 9.5"
    assert graded_variant("BGS", "9.0") == "graded:BGS 9"
    assert graded_variant("PSA", None) is None


def _card() -> Card:
    return Card(language="de", name="Nachtara VMAX", number="215", number_norm="215")


ROWS = [
    SoldRow("Nachtara VMAX 215/203 Drachenwandel NM", "EUR 180,00", "Verkauft 12. Okt 2026"),
    SoldRow("Nachtara VMAX 215/203 deutsch", "200,00 €", "Verkauft 10. Okt 2026"),
    SoldRow("Nachtara VMAX 215/203", "160,00 €", "Verkauft 1. Okt 2026"),
    SoldRow("Nachtara VMAX 215/203 PSA 10", "650,00 €", "Verkauft 9. Okt 2026"),
    SoldRow("Pokemon Karten Konvolut 50 Stück Nachtara 215", "40,00 €", "Verkauft 9. Okt 2026"),
    SoldRow("Nachtara VMAX Drachenwandel", "120,00 €", "Verkauft 8. Okt 2026"),  # ohne Nummer
    SoldRow("Nachtara VMAX 215/203", "150,00 €", "Verkauft 2. Mai 2026"),  # zu alt
    SoldRow("Nachtara VMAX 215/203", "$210.00", "Sold Oct 11, 2026"),
]


def test_evaluate_sold_suggests_safe_sales_and_groups() -> None:
    result = evaluate_sold(_card(), f"{PAGE}#kartenkiste=x", ROWS, today=TODAY)

    assert result.page_url == PAGE
    assert [sale.suggested for sale in result.sales] == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert result.sales[4].issues == ("Konvolut/Produkt/Fälschung?",)
    assert result.sales[5].issues == ("Nummer fehlt im Titel",)
    assert result.sales[6].issues == ("älter als 4 Monate",)
    assert result.sales[7].price is None  # Dollar
    groups = {group.group: group for group in result.groups}
    raw = groups["raw"]
    assert (raw.median, raw.low, raw.high, raw.count) == (
        Decimal("180.00"),
        Decimal("160.00"),
        Decimal("200.00"),
        3,
    )
    assert groups["PSA 10"].median == Decimal("650.00")
    assert any("nicht in Euro" in warning for warning in result.warnings)


def test_user_selection_overrides_suggestion() -> None:
    result = evaluate_sold(_card(), PAGE, ROWS, selected=[0, 5, 99], today=TODAY)
    assert [(g.group, g.count, g.median) for g in result.groups] == [("raw", 2, Decimal("150.00"))]


def test_only_ebay_pages() -> None:
    with pytest.raises(InvalidInputError):
        evaluate_sold(_card(), "https://www.ebay.evil.com/sch", [], today=TODAY)
    evaluate_sold(_card(), "https://www.ebay.com/sch/i.html?_nkw=x", [], today=TODAY)


async def test_api_save_values_graded_item(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    sold = f"Verkauft {date.today():%d.%m.%Y}"  # Datum relativ zu heute: Test altert nicht
    rows = [
        {"title": "Nachtara VMAX 215/203 PSA 10", "price": "650,00 €", "sold": sold},
        {"title": "Nachtara VMAX 215/203 PSA 10", "price": "700,00 €", "sold": sold},
        {"title": "Nachtara VMAX 215/203", "price": "180,00 €", "sold": sold},
    ]
    item = await client.post(
        f"{API}/collection/items",
        json={"card_id": str(card.id), "grading_company": "PSA", "grade": "10"},
        headers=user.headers,
    )
    assert item.json()["value"]["kind"] == "none"  # vorher: kein Wert

    preview = await client.post(
        f"{API}/cards/{card.id}/ebay-sold",
        json={"page_url": PAGE, "rows": rows},
        headers=user.headers,
    )
    assert preview.status_code == 200
    assert preview.json()["saved"] == 0
    assert [g["group"] for g in preview.json()["groups"]] == ["raw", "PSA 10"]

    saved = await client.post(
        f"{API}/cards/{card.id}/ebay-sold",
        json={"page_url": PAGE, "rows": rows, "selected": [0, 1, 2], "save": True},
        headers=user.headers,
    )
    assert saved.json()["saved"] == 8  # 2 Gruppen × Median/ab/bis/Anzahl

    items = (await client.get(f"{API}/collection/items", headers=user.headers)).json()
    value = items["items"][0]["value"] if isinstance(items, dict) else items[0]["value"]
    assert (value["kind"], value["unit_value"], value["source"]) == (
        "external",
        "675.00",
        "ebay_sold",
    )
    assert value["basis"] == "Median aus 2 eBay-Verkäufen"

    prices = (await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)).json()
    ebay = [o for o in prices["offers"] if o["source"] == "ebay_sold"]
    assert {o["variant"] for o in ebay} == {"raw", "graded:PSA 10"}
    assert all(o["url"] == PAGE for o in ebay)
