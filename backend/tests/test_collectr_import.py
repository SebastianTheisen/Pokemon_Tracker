"""Collectr-Showcase übernehmen: Kacheln auswerten, dem Katalog zuordnen, in Ordner übernehmen.

Die Kachel-Zeilen stammen aus den Screenshots des Showcase (28.10.2026).
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet
from app.services.collectr_import import parse_row
from tests.conftest import RegisterUser

API = "/api/v1"

ESPEON = [
    "Espeon V (JP)",
    "Eevee Heroes",
    "Secret Rare • 081/069",
    "Near Mint • Holofoil",
    "$169.02",
    "$0.00 (0,00%)",
    "Qty: 2",
]
CHARIZARD = [  # neueres japanisches Set – Collectr schreibt kein „(JP)“
    "Mega Charizard X ex",
    "Inferno X",
    "Mega Ultra Rare • 116/080",
    "Near Mint • Holofoil",
    "▼ $657.84",
    "-$48.17 (-6,82%)",
    "Qty: 1",
]
RED_PIKACHU = [
    "Red's Pikachu (JP)",
    "Sun & Moon Promos (JP)",
    "Promo • 270/SM-P",
    "Lightly Played • Reverse Holofoil",
    "$404.36",
    "Qty: 1",
]
GRADED_PIKACHU = [  # Ordner „Graded Cards“: keine Zustandszeile
    "Pikachu with Grey Felt Hat",
    "Scarlet & Violet Promo",
    "Promo • 085",
    "$2,566.53",
    "+$22.63 (0,89%)",
    "Qty: 1",
]
UNKNOWN = ["Irgendwas (JP)", "Unbekanntes Set", "Promo • 999/999", "Near Mint • Holofoil"]


def test_parse_row_reads_every_field() -> None:
    row = parse_row(ESPEON)
    assert row is not None
    assert (row.name, row.set_name, row.japanese) == ("Espeon V", "Eevee Heroes", True)
    assert (row.rarity, row.number, row.total, row.number_norm) == (
        "Secret Rare",
        "081",
        "069",
        "81",
    )
    assert (row.condition, row.variant, row.quantity, row.graded) == ("NM", "normal", 2, False)

    red = parse_row(RED_PIKACHU)
    assert red is not None
    assert (red.set_name, red.total, red.condition, red.variant) == (
        "Sun & Moon Promos",
        "SM-P",
        "EX",  # Lightly Played → Cardmarket-Skala
        "reverse",
    )
    graded = parse_row(GRADED_PIKACHU)
    assert graded is not None
    assert (graded.number, graded.total, graded.graded, graded.condition) == (
        "085",
        None,
        True,
        None,
    )
    charizard = parse_row(CHARIZARD)
    assert charizard is not None and not charizard.japanese


def test_parse_row_joins_split_lines() -> None:
    """Flex-Layout: der Browser liefert Teile einer Zeile einzeln."""
    row = parse_row(
        [
            "Espeon V (JP)",
            "Eevee Heroes",
            "Secret Rare",
            "•",
            "081/069",
            "Near Mint",
            "•",
            "Reverse Holofoil",
            "$169.02",
            "Qty:",
            "3",
        ]
    )
    assert row is not None
    assert (row.rarity, row.number, row.total) == ("Secret Rare", "081", "069")
    assert (row.condition, row.variant, row.quantity) == ("NM", "reverse", 3)
    split = parse_row(["Mew ex", "Paldean Fates", "Special Illustration Rare •", "232/091"])
    assert split is not None and (split.number, split.total) == ("232", "091")


def test_parse_row_with_euro_prices_and_jp_suffix() -> None:
    """Showcase auf Euro umgestellt; Setname mit „JP“ ohne Klammern (Screenshot 28.10.)."""
    row = parse_row(
        [
            "Celebration Fanfare (JP)",
            "Scarlet & Violet Promo JP",
            "Common • 110/SV-P",
            "Near Mint • Normal",
            "€168.92",
            "€0.00 (0,00%)",
            "Qty: 1",
        ]
    )
    assert row is not None
    assert (row.name, row.set_name, row.japanese) == (
        "Celebration Fanfare",
        "Scarlet & Violet Promo",
        True,
    )
    assert (row.number, row.total, row.condition) == ("110", "SV-P", "NM")
    lillie = parse_row(
        ["Lillie (JP)", "Sun & Moon Promos (JP)", "Promo • 080/SM-P", "Near Mint • Holofoil",
         "€379.41", "-€25.32 (-6,26%)", "Qty: 1"]
    )  # fmt: skip
    assert lillie is not None and (lillie.number, lillie.total) == ("080", "SM-P")


def test_parse_row_ignores_tiles_without_number() -> None:
    assert parse_row(["Login to add", "Track this card in your collection"]) is None
    assert parse_row([]) is None


async def _catalog(factory: async_sessionmaker[AsyncSession]) -> dict[str, Card]:
    specs: list[tuple[str, str, str, int, str, str]] = [
        # (Set-Code, Sprache, Setname, Setgröße, Nummer, Kartenname)
        ("S6a", "ja", "強化拡張パック イーブイヒーローズ", 69, "081", "エーフィV"),
        ("S6H", "ja", "拡張パック 白銀のランス", 70, "081", "ブラッキーV"),  # gleiche Nummer
        ("swsh7", "en", "Evolving Skies", 203, "081", "Espeon V"),  # andere Setgröße
        ("M2", "ja", "拡張パック インフェルノX", 80, "116", "メガリザードンXex"),  # noqa: RUF001
        ("SM-P", "ja", "サン&ムーン プロモカード", 0, "270", "レッドのピカチュウ"),
        ("svp", "en", "SVP Black Star Promos", 0, "085", "Pikachu with Grey Felt Hat"),
        ("svp2", "en", "SVP Black Star Promos", 0, "085", "Pikachu"),
    ]
    cards: dict[str, Card] = {}
    async with factory() as session:
        for code, language, set_name, size, number, name in specs:
            card_set = CardSet(
                external_id=code,
                language=language,
                name=set_name,
                card_count_official=size or None,
            )
            session.add(card_set)
            await session.flush()
            card = Card(
                external_id=f"{code}-{number}",
                language=language,
                set_id=card_set.id,
                number=number,
                number_norm=number.lstrip("0"),
                name=name,
            )
            session.add(card)
            cards[f"{code}-{number}"] = card
        await session.commit()
    return cards


async def test_collectr_preview_and_commit(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user("alice@example.com")
    cards = await _catalog(session_factory)

    preview = await client.post(
        f"{API}/import/collectr/preview",
        json={
            "portfolio": "Main Ordner",
            "rows": [ESPEON, CHARIZARD, RED_PIKACHU, GRADED_PIKACHU, UNKNOWN, ["Qty: 1"]],
        },
        headers=alice.headers,
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["portfolio"] == "Main Ordner"
    rows: dict[int, Any] = {row["index"]: row for row in data["rows"]}
    assert set(rows) == {0, 1, 2, 3, 4}  # Zeile 5 ist keine Karte

    def best(index: int) -> str:
        return str(rows[index]["matches"][0]["card"]["id"])

    assert rows[0]["status"] == "matched"
    assert best(0) == str(cards["S6a-081"].id)  # nicht S6H (Setgröße) und nicht Englisch
    assert rows[1]["status"] == "matched"
    assert best(1) == str(cards["M2-116"].id)  # japanisch trotz fehlendem „(JP)“
    assert rows[2]["status"] == "matched"
    assert best(2) == str(cards["SM-P-270"].id)  # Promo-Kürzel als Setgröße
    assert rows[3]["status"] == "matched" and rows[3]["graded"]
    assert best(3) == str(cards["svp-085"].id)  # Name entscheidet ohne Setgröße
    assert rows[4]["status"] == "missing" and rows[4]["matches"] == []
    assert rows[0]["number"] == "081/069" and rows[0]["quantity"] == 2

    items = [
        {"card_id": best(0), "quantity": 2, "condition": "NM"},
        {"card_id": best(2), "condition": "EX", "variant": "reverse"},
        {"card_id": best(3), "grading_company": "PSA", "grade": "10"},
    ]
    commit = await client.post(
        f"{API}/import/collectr/commit",
        json={"folder_name": "Main Ordner", "items": items},
        headers=alice.headers,
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert (result["folder"]["name"], result["added"], result["skipped"]) == ("Main Ordner", 3, 0)

    # Zweiter Durchlauf (gleicher Ordner, Groß/Klein egal): nichts doppelt
    again = await client.post(
        f"{API}/import/collectr/commit",
        json={"folder_name": "main ordner", "items": items},
        headers=alice.headers,
    )
    assert again.json()["added"] == 0 and again.json()["skipped"] == 3
    assert again.json()["folder"]["id"] == result["folder"]["id"]

    listed = (
        await client.get(
            f"{API}/collection/items",
            params={"folder_id": result["folder"]["id"]},
            headers=alice.headers,
        )
    ).json()
    entries = listed["items"] if isinstance(listed, dict) else listed
    by_card = {e["card"]["id"]: e for e in entries}
    assert by_card[best(0)]["quantity"] == 2
    assert by_card[best(2)]["variant"] == "reverse"
    assert (by_card[best(3)]["grading_company"], by_card[best(3)]["grade"]) == ("PSA", "10")


async def test_collectr_import_needs_login(client: AsyncClient) -> None:
    response = await client.post(f"{API}/import/collectr/preview", json={"rows": []})
    assert response.status_code == 401
