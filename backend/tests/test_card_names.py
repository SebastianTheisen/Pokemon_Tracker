"""Übersetzung asiatischer Kartennamen und mehrsprachige Suche (PokéAPI-Namen)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.card_names import foreign_search_terms, has_cjk, translate_card_name
from tests.conftest import Account
from tests.pricing_helpers import make_card


@pytest.mark.parametrize(
    ("name", "language", "expected"),
    [
        ("ピカチュウex", "ja", "Pikachu ex"),  # Testkarte des Nutzers (132/M-P)
        ("ブラッキーex", "ja", "Nachtara ex"),
        ("ルギアV", "ja", "Lugia V"),
        ("ゼニガメ", "ja", "Schiggy"),
        ("メガリザードンXex", "ja", "Mega-Glurak X ex"),
        ("ロケット団のミュウツーex", "ja", "Team Rockets Mewtu ex"),
        ("ピカチュウ&ゼクロムGX", "ja", "Pikachu & Zekrom GX"),
        ("ｹﾞﾝｶﾞｰ", "ja", "Gengar"),  # Halbbreite Katakana
        ("루기아V", "ko", "Lugia V"),
        ("洛奇亞V", "zh-tw", "Lugia V"),
        ("鲤鱼王", "zh-cn", "Karpador"),
        ("スパイクエネルギー", "ja", None),  # Energie – kein Pokémon
        ("Pikachu", "de", None),  # nur asiatische Karten
    ],
)
def test_translate_card_name(name: str, language: str, expected: str | None) -> None:
    assert translate_card_name(name, language) == expected


def test_foreign_search_terms() -> None:
    assert foreign_search_terms("pikachu ex") == ["ピカチュウex", "피카츄ex", "皮卡丘ex"]
    assert "ブラッキー" in foreign_search_terms("Umbreon")  # englisch
    assert "ブラッキー" in foreign_search_terms("nachtara")  # deutsch
    assert foreign_search_terms("Trainer") == []
    assert foreign_search_terms("pikachuu") == []  # nur ganze Wörter
    assert has_cjk("ピカチュウ")
    assert not has_cjk("Pikachu")


async def test_search_finds_japanese_card_by_german_name(
    client: AsyncClient,
    admin: Account,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await make_card(
        session_factory, external_id="M-P-132", name="ピカチュウex", number="132", language="ja"
    )
    await make_card(session_factory, external_id="sv1-50", name="Glurak", number="50")

    response = await client.get(
        "/api/v1/cards/search", params={"q": "pikachu 132"}, headers=admin.headers
    )

    assert response.status_code == 200
    (hit,) = response.json()
    assert hit["card"]["name"] == "ピカチュウex"
    assert hit["card"]["translated_name"] == "Pikachu ex"
    german = await client.get("/api/v1/cards/search", params={"q": "glurak"}, headers=admin.headers)
    assert german.json()[0]["card"]["translated_name"] is None
