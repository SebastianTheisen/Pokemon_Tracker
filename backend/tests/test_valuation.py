"""Bewertung einzelner Positionen (ohne Datenbank)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models import CollectionItem, GradingCompany
from app.services.pricing import CardPrices, ConditionPrice
from app.services.valuation import item_kind, unit_value, value_item

CARD_ID = uuid.uuid4()
NOW = datetime(2026, 10, 17, tzinfo=UTC)


def _condition(
    condition: str, value: str, *, kind: str = "estimated", variant: str = "normal"
) -> ConditionPrice:
    return ConditionPrice(
        variant=variant,
        condition=condition,
        value=Decimal(value),
        currency="EUR",
        kind=kind,  # type: ignore[arg-type]
        source="cardmarket" if kind == "estimated" else "plugin",
        updated_at=NOW,
        url=None,
        basis_metric="median(trend, avg7, avg30)" if kind == "estimated" else None,
        basis_value=Decimal("100") if kind == "estimated" else None,
        factor=Decimal("0.85") if kind == "estimated" else None,
    )


PRICES = CardPrices(
    card_id=CARD_ID,
    last_checked_at=NOW,
    offers=[],
    conditions=[
        _condition("NM", "100.00"),
        _condition("EX", "85.00"),
        _condition("NM", "3.00", variant="reverse"),
        _condition("LP", "50.00", kind="external"),
    ],
)


def _item(**fields: object) -> CollectionItem:
    defaults: dict[str, object] = {
        "card_id": CARD_ID,
        "product_id": None,
        "variant": "normal",
        "condition": "NM",
        "quantity": 1,
        "custom_price": None,
        "grading_company": None,
        "value_at_add": None,
    }
    return CollectionItem(**(defaults | fields))


@pytest.mark.parametrize(
    ("fields", "expected_kind", "expected_value"),
    [
        ({}, "estimated", Decimal("100.00")),
        ({"condition": "EX"}, "estimated", Decimal("85.00")),
        ({"condition": None}, "estimated", Decimal("100.00")),  # ohne Zustand: NM
        ({"condition": "LP"}, "external", Decimal("50.00")),
        ({"variant": "reverse"}, "estimated", Decimal("3.00")),
        ({"condition": "PO"}, "none", None),  # kein Preis für diesen Zustand vorhanden
        ({"custom_price": Decimal("123.45")}, "manual", Decimal("123.45")),
        ({"grading_company": GradingCompany.PSA}, "none", None),
        (
            {"grading_company": GradingCompany.PSA, "custom_price": Decimal("900")},
            "manual",
            Decimal("900"),
        ),
        ({"card_id": None, "product_id": uuid.uuid4()}, "none", None),
    ],
)
def test_unit_value_order(
    fields: dict[str, object], expected_kind: str, expected_value: Decimal | None
) -> None:
    value = unit_value(_item(**fields), PRICES)

    assert (value.kind, value.unit_value) == (expected_kind, expected_value)


def test_estimated_value_explains_basis() -> None:
    value = unit_value(_item(condition="EX"), PRICES)

    assert value.basis == "median(trend, avg7, avg30) = 100 × 0.85"


def test_quantity_and_change_since_added() -> None:
    item = _item(quantity=3, value_at_add=Decimal("80.00"))

    value = value_item(item, {CARD_ID: PRICES})

    assert value.total_value == Decimal("300.00")
    assert value.change == Decimal("60.00")  # 3 × (100 − 80)


def test_without_value_at_add_there_is_no_change() -> None:
    value = value_item(_item(), {CARD_ID: PRICES})

    assert value.change is None


def test_item_kinds() -> None:
    assert item_kind(_item()) == "raw"
    assert item_kind(_item(grading_company=GradingCompany.CGC)) == "graded"
    assert item_kind(_item(card_id=None, product_id=uuid.uuid4())) == "sealed"
