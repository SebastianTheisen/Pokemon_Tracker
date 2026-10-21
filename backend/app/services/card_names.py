"""Übersetzung von Kartennamen (Japanisch, Koreanisch, Chinesisch → Deutsch) und
mehrsprachige Suche über die Pokémon-Namen.

Grundlage sind die offenen PokéAPI-Daten (``app/data/species_names.json``, erzeugt mit
``scripts/build_species_names.py``): jedes Pokémon in allen Katalogsprachen. Übersetzt wird
der Pokémon-Teil des Kartennamens, Zusätze wie „ex“, „V“ oder „GX“ bleiben:

* ``ピカチュウex`` → ``Pikachu ex``
* ``メガリザードンXex`` → ``Mega-Glurak X ex``
* ``ロケット団のミュウツーex`` → ``Team Rockets Mewtu ex``

Trainer-, Item- und Energiekarten haben keinen Pokémon-Namen → keine Übersetzung.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "species_names.json"
TRANSLATED_LANGUAGES = frozenset({"ja", "ko", "zh-tw", "zh-cn"})
TARGET_LANGUAGE = "de"
_CJK = re.compile(r"[぀-ヿ一-鿿가-힯]")

# Häufige Namenszusätze auf asiatischen Karten (Reihenfolge: längere zuerst).
_AFFIXES: dict[str, tuple[tuple[str, str], ...]] = {
    "ja": (
        ("ロケット団の", "Team Rockets "),
        ("メガ", "Mega-"),
        ("ヒスイ", "Hisui-"),
        ("ガラル", "Galar-"),
        ("アローラ", "Alola-"),
        ("パルデア", "Paldea-"),
        ("テラスタル", "Terakristall-"),
        ("ひかる", "Leuchtendes "),
        ("かがやく", "Strahlendes "),
    ),
    "ko": (
        ("로켓단의 ", "Team Rockets "),
        ("로켓단의", "Team Rockets "),
        ("메가", "Mega-"),
        ("히스이 ", "Hisui-"),
        ("가라르 ", "Galar-"),
        ("알로라 ", "Alola-"),
        ("빛나는 ", "Strahlendes "),
    ),
    "zh": (
        ("火箭队的", "Team Rockets "),
        ("火箭隊的", "Team Rockets "),
        ("超级", "Mega-"),
        ("超級", "Mega-"),
        ("洗翠", "Hisui-"),
        ("伽勒尔", "Galar-"),
        ("伽勒爾", "Galar-"),
        ("阿罗拉", "Alola-"),
        ("阿羅拉", "Alola-"),
        ("光辉", "Strahlendes "),
        ("光輝", "Strahlendes "),
    ),
}
# Für englische Ziele (PriceCharting-Suche): deutsche Zusätze → englische Schreibweise.
_AFFIXES_EN = (
    ("Team Rockets ", "Team Rocket's "),
    ("Mega-", "Mega "),
    ("Hisui-", "Hisuian "),
    ("Galar-", "Galarian "),
    ("Alola-", "Alolan "),
    ("Paldea-", "Paldean "),
    ("Terakristall-", "Tera "),
    ("Leuchtendes ", "Shining "),
    ("Strahlendes ", "Radiant "),
)
_SUFFIX = re.compile(r"(?<=[^\s-])(ex|EX|GX|VMAX|VSTAR|V-UNION|V|BREAK)$")


def _family(language: str) -> str:
    return "zh" if language.startswith("zh") else language


@cache
def _species() -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, dict[str, str]]] = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return data["species"]


@cache
def _names_by_language(family: str) -> tuple[tuple[str, str], ...]:
    """(Name in der Sprache, Species-ID), längste Namen zuerst (gierige Suche)."""
    languages = ("zh-tw", "zh-cn") if family == "zh" else (family,)
    pairs = {
        (unicodedata.normalize("NFKC", names[language]), species_id)
        for species_id, names in _species().items()
        for language in languages
        if language in names
    }
    return tuple(sorted(pairs, key=lambda pair: len(pair[0]), reverse=True))


def species_name(species_id: str, language: str = TARGET_LANGUAGE) -> str | None:
    return _species().get(species_id, {}).get(language)


def translate_card_name(name: str, language: str, target: str = TARGET_LANGUAGE) -> str | None:
    """Deutscher (bzw. ``target``) Name einer asiatischen Karte – ``None`` ohne Pokémon-Namen."""
    if language not in TRANSLATED_LANGUAGES:
        return None
    family = _family(language)
    text = unicodedata.normalize("NFKC", name).strip()
    found = False
    for local, species_id in _names_by_language(family):
        if local in text:
            translated = species_name(species_id, target)
            if translated:
                text = text.replace(local, f" {translated} ")
                found = True
    if not found:
        return None
    for local, german in _AFFIXES.get(family, ()):
        text = text.replace(local, german)
    if target == "en":
        for german, english in _AFFIXES_EN:
            text = text.replace(german, english)
    text = re.sub(r"\s*&\s*", " & ", text)
    text = re.sub(r"-\s+", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _SUFFIX.sub(r" \1", text)


def foreign_search_terms(term: str) -> list[str]:
    """Suchbegriff auf Deutsch/Englisch → dieselbe Suche mit asiatischen Pokémon-Namen.

    ``"pikachu ex"`` → ``["ピカチュウex", "피카츄ex", "皮卡丘ex"]`` – so findet die Suche auch
    Karten, deren Namen man nicht lesen kann.
    """
    lowered = term.casefold()
    terms: list[str] = []
    for names in _species().values():
        for western in {names.get("de", ""), names.get("en", "")}:
            key = western.casefold()
            if len(key) < 3 or not re.search(rf"(?<![\w]){re.escape(key)}(?![\w])", lowered):  # noqa: PLR2004
                continue
            for language in ("ja", "ko", "zh-tw", "zh-cn"):
                local = names.get(language)
                if local:
                    replaced = re.sub(re.escape(key), local, lowered)
                    compact = replaced.replace(" ", "")
                    if compact not in terms:
                        terms.append(compact)
    return terms


def has_cjk(text: str) -> bool:
    return bool(_CJK.search(text))


# Englische Zusätze auf deutschen Karten (Reihenfolge: längere zuerst).
_ENGLISH_AFFIXES = (
    ("Team Rocket's ", "Team Rockets "),
    ("Dark ", "Dunkles "),
    ("Light ", "Helles "),
    ("Shining ", "Schillerndes "),
    ("Radiant ", "Strahlendes "),
    ("Alolan ", "Alola-"),
    ("Galarian ", "Galar-"),
    ("Hisuian ", "Hisui-"),
    ("Paldean ", "Paldea-"),
)


@cache
def _english_to_german() -> tuple[tuple[re.Pattern[str], str], ...]:
    pairs = {
        (names["en"], names["de"])
        for names in _species().values()
        if names.get("en") and names.get("de") and names["en"] != names["de"]
    }
    return tuple(
        (re.compile(rf"(?<![\w-]){re.escape(english)}(?![\w])"), german)
        for english, german in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)
    )


def translate_english_name(name: str) -> str:
    """Englischer Kartenname → deutsche Schreibweise der Pokémon (Rest bleibt).

    ``Charizard`` → ``Glurak``, ``Erika's Jigglypuff`` → ``Erikas Pummeluff``,
    ``Dark Tyranitar`` → ``Dunkles Despotar``. Trainer- und Itemkarten bleiben englisch.
    """
    text = name
    for english, german in _ENGLISH_AFFIXES:
        text = text.replace(english, german)
    for pattern, german in _english_to_german():
        text = pattern.sub(german, text)
    return re.sub(r"(\w)'s\b", r"\1s", text)
