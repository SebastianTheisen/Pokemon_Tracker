"""Unit-Tests für Nummern-Normalisierung und Zerlegung von Suchanfragen."""

from __future__ import annotations

import pytest

from app.services.catalog_numbers import ParsedQuery, normalize_number, parse_query


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("215", "215"),
        ("215/203", "215"),
        ("007", "7"),
        ("SV050", "SV50"),
        ("tg05", "TG5"),
        ("125/SM-P", "125"),
        ("#42", "42"),
        ("0", "0"),
        ("H 12", "H12"),
    ],
)
def test_normalize_number(raw: str, normalized: str) -> None:
    assert normalize_number(raw) == normalized


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("nachtara 215", ParsedQuery("nachtara", "215")),
        ("Nachtara VMAX 215/203", ParsedQuery("Nachtara VMAX", "215")),
        ("Team Rockets Mewtu ex 231", ParsedQuery("Team Rockets Mewtu ex", "231")),
        ("glurak", ParsedQuery("glurak", None)),
        ("215", ParsedQuery("", "215")),
        ("Porygon2", ParsedQuery("Porygon2", None)),
        ("pikachu SV050", ParsedQuery("pikachu", "SV50")),
        ("  umbreon   #215  ", ParsedQuery("umbreon", "215")),
        ("", ParsedQuery("", None)),
    ],
)
def test_parse_query(query: str, expected: ParsedQuery) -> None:
    assert parse_query(query) == expected


def test_parsed_query_is_empty() -> None:
    assert parse_query("   ").is_empty
    assert not parse_query("215").is_empty
