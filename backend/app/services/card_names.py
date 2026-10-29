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


@cache
def _ids_by_name(language: str) -> dict[str, str]:
    return {
        names[language].casefold(): species_id
        for species_id, names in _species().items()
        if language in names
    }


def species_id_by_name(name: str, language: str = "en") -> str | None:
    """Species-ID zu einem Pokémon-Namen (genau, ohne Zusätze), z. B. „Charizard“ → „6“."""
    return _ids_by_name(language).get(name.strip().casefold())


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


@cache
def _western_names() -> tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...]:
    """(deutscher/englischer Name, Wort-Muster, asiatische Namen) – einmal aufgebaut."""
    entries = []
    for names in _species().values():
        locals_ = tuple(
            names[language] for language in ("ja", "ko", "zh-tw", "zh-cn") if names.get(language)
        )
        for western in {names.get("de", ""), names.get("en", "")}:
            key = western.casefold()
            if len(key) >= 3 and locals_:  # noqa: PLR2004 – „Mew“ ja, Abkürzungen nein
                entries.append((key, re.compile(rf"(?<![\w]){re.escape(key)}(?![\w])"), locals_))
    return tuple(entries)


def foreign_search_terms(term: str) -> list[str]:
    """Suchbegriff auf Deutsch/Englisch → dieselbe Suche mit asiatischen Pokémon-Namen.

    ``"pikachu ex"`` → ``["ピカチュウex", "피카츄ex", "皮卡丘ex"]`` – so findet die Suche auch
    Karten, deren Namen man nicht lesen kann.

    Schnell genug für jede Suche: erst ein einfacher Teilstring-Test, das Wort-Muster nur bei
    Kandidaten (früher ~1.900 reguläre Ausdrücke je Suche, ~0,3 s).
    """
    lowered = term.casefold()
    terms: list[str] = []
    for key, pattern, locals_ in _western_names():
        if key not in lowered or not pattern.search(lowered):
            continue
        for local in locals_:
            compact = lowered.replace(key, local).replace(" ", "")
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


# Zusätze, die viele Karten teilen – sie sagen nichts darüber, welches Pokémon gemeint ist.
_GENERIC_WORDS = frozenset(
    {
        "mega", "vmax", "vstar", "gmax", "break", "prism", "star", "tera", "radiant",
        "shining", "dark", "light", "team", "rocket", "rockets", "alolan", "galarian",
        "hisuian", "paldean", "origin", "forme", "form", "the", "and", "with", "ex", "gx",
    }
)  # fmt: skip


def _plain_words(text: str) -> set[str]:
    plain = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    return set(re.findall(r"[a-z]{3,}", plain.casefold()))


@cache
def _pokemon_reading(name: str, language: str) -> tuple[str, frozenset[str]]:
    """(Art, Kennwörter): ``none`` – kein Pokémon-Name (Energie, die meisten Trainer);
    ``partial`` – ein Pokémon-Name steckt nur in einem längeren Namen („ラッキーエネルギー“
    Lucky Energy, „シャーロット・プリン“ aus One Piece) – nicht prüfbar; ``full`` – ganz
    übersetzt („噴火龍VMAX“ → Charizard VMAX, Kennwörter {"charizard"})."""
    translated = translate_card_name(name, language, target="en")
    if translated is None:
        return "none", frozenset()
    if not translated.isascii():
        return "partial", frozenset()
    return "full", frozenset(_plain_words(translated) - _GENERIC_WORDS)


def pokemon_words(name: str, language: str) -> frozenset[str] | None:
    """Kennwörter des Pokémon einer asiatischen Pokémon-Karte auf Englisch („噴火龍VMAX“ →
    {"charizard"}); ``None``, wenn der Name nicht ganz ein Pokémon-Name ist."""
    kind, words = _pokemon_reading(name, language)
    return words if kind == "full" else None


def contradicts_english(name: str, language: str, english: str) -> bool:
    """Gehört ein englischer Name (z. B. Cardmarket-Produkt) sicher zu einer anderen Karte?
    Nur bei ganz übersetzbaren Pokémon-Namen prüfbar: Kein Kennwort kommt darin vor."""
    words = pokemon_words(name, language)
    return bool(words) and not (words or frozenset()) & _plain_words(english)


def asian_names_conflict(
    first: str, first_language: str, second: str, second_language: str
) -> bool:
    """Zeigen zwei asiatische Karten mit derselben ID sicher verschiedene Karten? Promo-Sets
    sind je Land anders nummeriert: Japan SV-P 038 ist Basic Fire Energy, Taiwan SV-P 038
    Charizard VMAX. Konflikt, wenn eine sicher kein Pokémon ist und die andere ganz ein
    Pokémon-Name, oder wenn beide verschiedene Pokémon sind. Unklare Namen: kein Konflikt."""
    if first_language not in TRANSLATED_LANGUAGES or second_language not in TRANSLATED_LANGUAGES:
        return False
    one_kind, one = _pokemon_reading(first, first_language)
    two_kind, two = _pokemon_reading(second, second_language)
    if "partial" in (one_kind, two_kind) or one_kind == two_kind == "none":
        return False
    if "none" in (one_kind, two_kind):
        return True
    return bool(one) and bool(two) and not (one & two)
