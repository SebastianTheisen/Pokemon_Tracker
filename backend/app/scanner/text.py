"""Merkmale aus dem erkannten Text: Kartennummer, Setcode, Namenskandidaten, Sprache.

Die OCR läuft auf dem ganzen Foto (Plan 5.6). Deshalb steht hier viel „Rauschen“:
Attackentexte, Hintergrund, Shop-Oberflächen. Die Funktionen sind bewusst großzügig beim
Sammeln von Kandidaten – aussortiert wird später beim Abgleich mit dem Katalog, wo nur
existierende Karten zählen.

Beispiele aus dem Testsatz (``scanner_testset/``):

* ``"DR231/182 會会"`` → Nummer 231, Setgröße 182, Setcode-Kandidat ``dr``
* ``"512 F 110/098 SR"`` → Nummer 110, Setgröße 98, Setcode-Kandidat ``s12`` („5“ statt „S“)
* ``"No.007"`` → Nummer 7 (alte Karten ohne Setnummer)
* ``"#110"`` → Nummer 110 (Slab-Label)
* ``"OP01-001"`` → One Piece: Set und Nummer in einem (unten rechts auf der Karte)
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.scanner.ocr import OcrLine
from app.scanner.slab import SlabLabel, parse_slab
from app.services.catalog_numbers import normalize_number

# ------------------------------------------------------------------ Normalisieren

_LONG_VOWEL = re.compile(r"(?<=[゠-ヿ])[-‐‑–—―一~〜]")  # noqa: RUF001 – OCR-Varianten von „ー“
_COMPACT = re.compile(r"[\s·・.,'’`\"-]+")  # noqa: RUF001


def normalize_text(text: str) -> str:
    """NFKC (Vollbreite → normal) und typische OCR-Verwechslungen bei Katakana."""
    text = unicodedata.normalize("NFKC", text).strip()
    # Langer Vokal: OCR liest „ー“ oft als „-“ oder „一“ („ブラッキ-“ → „ブラッキー“).
    return _LONG_VOWEL.sub("ー", text)


# Kleine Kana (ィ, ャ, ッ …) liest die OCR auf Fotos oft als große („リーフイア“ statt
# „リーフィア“) – im Vergleichsschlüssel zählen beide gleich. Dieselbe Zuordnung nutzt die
# SQL-Suche (:data:`SMALL_KANA`, :data:`LARGE_KANA`).
SMALL_KANA = "ァィゥェォッャュョヮヵヶぁぃぅぇぉっゃゅょゎ"
# Zeichen, die der Vergleichsschlüssel entfernt – für SQL (``translate``) wie ``_COMPACT``.
COMPACT_SQL_CHARS = " .,'’`\"-·・"  # noqa: RUF001
LARGE_KANA = "アイウエオツヤユヨワカケあいうえおつやゆよわ"
_KANA_SIZE = str.maketrans(SMALL_KANA, LARGE_KANA)


def compact_key(text: str) -> str:
    """Vergleichsschlüssel: normalisiert, ohne Leerraum/Satzzeichen, Groß/Klein und
    kleine/große Kana egal."""
    return _COMPACT.sub("", normalize_text(text)).casefold().translate(_KANA_SIZE)


_NAME_SUFFIX = re.compile(r"(?:vmax|vstar|v-union|vunion|gx|ex|v|break|prime|legend|lvx|[★☆*δ])$")
# Asiatische Namen enden nie auf Buchstaben außer dem Logo – die OCR macht aus „ex“ aber
# gern „X“, „E“ oder „OX“. Bis zu drei lateinische Zeichen nach Kana/Kanji fallen weg.
_CJK_LATIN_TAIL = re.compile(r"(?<=[^\x00-\x7f])[a-z0-9]{1,3}$")


def name_base(key: str) -> str:
    """Schlüssel ohne Logo-Zusatz (ex, V, VMAX …) – den liest die OCR oft nicht mit."""
    base = _NAME_SUFFIX.sub("", key)
    base = _CJK_LATIN_TAIL.sub("", base)
    return base or key


# ------------------------------------------------------------------ Schriften


def _is_kana(char: str) -> bool:
    return "぀" <= char <= "ヿ" or "ㇰ" <= char <= "ㇿ"


def _is_hangul(char: str) -> bool:
    return "가" <= char <= "힯" or "ᄀ" <= char <= "ᇿ" or "㄰" <= char <= "㆏"


def _is_han(char: str) -> bool:
    return "一" <= char <= "鿿" or "㐀" <= char <= "䶿"


def is_cjk_text(text: str) -> bool:
    """Enthält Kana, Hangul oder Han-Zeichen."""
    return any(_is_kana(c) or _is_hangul(c) or _is_han(c) for c in text)


# Häufige Zeichen auf Karten, die es nur in einer der beiden chinesischen Schriften gibt.
_SIMPLIFIED = frozenset("伤宝梦进对战术们为这时击个张币则选择将从让")
_TRADITIONAL = frozenset("傷寶夢進對戰術們為這時擊個張幣則選擇將從讓")
_GERMAN_WORDS = frozenset(
    {
        "fähigkeit",
        "schadenspunkte",
        "schadenspunkt",
        "basis",
        "phase",
        "schwäche",
        "resistenz",
        "rückzug",
        "rückzugskosten",
        "deiner",
        "deinen",
        "dein",
        "deines",
        "gegner",
        "gegners",
        "karte",
        "karten",
        "ablagestapel",
        "bank",
        "entwickelt",
        "angriff",
        "attacke",
        "diese",
        "dieses",
        "wenn",
        "und",
        "oder",
        "mehr",
        "zug",
        "regel",
    }
)
_ENGLISH_WORDS = frozenset(
    {
        "ability",
        "damage",
        "basic",
        "stage",
        "weakness",
        "resistance",
        "retreat",
        "your",
        "opponent",
        "opponent's",
        "evolves",
        "from",
        "attack",
        "this",
        "the",
        "and",
        "more",
        "turn",
        "discard",
        "bench",
        "benched",
        "rule",
        "each",
        "card",
        "cards",
    }
)


@dataclass(frozen=True)
class LanguageGuess:
    """Vermutete Sprache(n) der Karte, wahrscheinlichste zuerst; leer = unbekannt."""

    languages: tuple[str, ...] = ()
    script: str | None = None

    @property
    def primary(self) -> str | None:
        return self.languages[0] if self.languages else None


def guess_language(texts: Iterable[str]) -> LanguageGuess:
    """Sprache aus der Schrift: Kana → ja, Hangul → ko, nur Han → zh, Latein → de/en."""
    kana = hangul = han = simplified = traditional = german = english = 0
    for text in texts:
        for char in text:
            kana += _is_kana(char)
            hangul += _is_hangul(char)
            han += _is_han(char)
            simplified += char in _SIMPLIFIED
            traditional += char in _TRADITIONAL
        for word in re.findall(r"[^\W\d_]+(?:'s)?", text.casefold()):
            german += word in _GERMAN_WORDS
            english += word in _ENGLISH_WORDS
    if hangul >= 2:  # noqa: PLR2004 – Mindestzahl Zeichen gegen Zufallstreffer
        return LanguageGuess(("ko",), "hangul")
    if kana >= 3:  # noqa: PLR2004
        return LanguageGuess(("ja",), "kana")
    if han >= 3:  # noqa: PLR2004
        order = ("zh-tw", "zh-cn") if traditional > simplified else ("zh-cn", "zh-tw")
        return LanguageGuess(order, "han")
    if german or english:
        order = ("en", "de") if english > german else ("de", "en")
        return LanguageGuess(order, "latin")
    return LanguageGuess()


# ------------------------------------------------------------------ Nummern


@dataclass(frozen=True)
class NumberHit:
    """Eine gelesene Kartennummer.

    ``number`` ist normalisiert wie ``cards.number_norm`` (``"110"``, ``"TG5"``).
    ``total`` ist die Setgröße hinter dem Schrägstrich (``98``) – ein starkes Merkmal,
    weil sie zur offiziellen Kartenzahl des Sets passen muss.
    """

    number: str
    raw: str
    source: str  # fraction | no | hash | promo
    total: int | None = None
    total_code: str | None = None  # z. B. "SV-P" bei Promos
    prefix: str | None = None  # Buchstaben direkt vor der Nummer, z. B. "DR"


_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1"})
_LOOSE_FRACTION = re.compile(r"(?<![A-Za-z0-9])[0-9OolI]{1,3}\s*/\s*[0-9OolI]{1,3}(?![0-9A-Za-z])")
_FRACTION = re.compile(
    r"(?<![0-9])(?P<prefix>[A-Z]{1,4})?(?P<num>\d{1,3})\s*/\s*"
    r"(?P<total>[A-Z]{1,4}-?[A-Z0-9]{0,4}|\d{2,3})(?![0-9])"
)
_NO_NUMBER = re.compile(r"(?<![A-Za-z])N[oO0º°]\s*[.:]?\s*(\d{1,3})(?![0-9])")
_HASH_NUMBER = re.compile(r"#\s*(\d{1,3})(?![0-9])")
_PROMO_NUMBER = re.compile(r"(?<![A-Za-z0-9])(SWSH|SM|XY|SVP|SV|BW|HGSS|DP)\s?-?(\d{2,3})(?![0-9])")
# One Piece: „OP01-001“, „ST10-005“, „EB01-061“, „PRB01-001“, Promos „P-001“. Die OCR liest
# „0P“ statt „OP“, „5T“ statt „ST“, „E8“ statt „EB“ und „O“ statt „0“ in den Ziffern.
_ONEPIECE_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(?P<code>PRB|OP|0P|ST|5T|EB|E8)\s?(?P<set>[0-9OolI]{2})\s?[-\u2010\u2013\u2014]?\s?"
    r"(?P<num>[0-9OolI]{3})(?![0-9A-Za-z])"
    r"|(?<![A-Za-z0-9])P\s?[-\u2010\u2013\u2014]\s?(?P<promo>[0-9OolI]{3})(?![0-9A-Za-z])"
)
_ONEPIECE_CODE_FIX = {"0P": "OP", "5T": "ST", "E8": "EB"}


def _fix_loose_fractions(text: str) -> str:
    """„11O/O98“ → „110/098“: Buchstaben-Verwechsler nur in alleinstehenden Brüchen."""

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        return value.translate(_DIGIT_FIX) if any(c.isdigit() for c in value) else value

    return _LOOSE_FRACTION.sub(replace, text)


def parse_numbers(text: str) -> list[NumberHit]:
    """Alle Kartennummern einer Textzeile."""
    text = _fix_loose_fractions(normalize_text(text))
    hits: list[NumberHit] = []
    for match in _FRACTION.finditer(text):
        prefix, digits, total_raw = match.group("prefix"), match.group("num"), match.group("total")
        total: int | None = None
        total_code: str | None = None
        if total_raw.isdigit():
            number, total = digits, int(total_raw)
        else:
            letters = re.match(r"[A-Z]+", total_raw)
            total_code = total_raw
            # „TG05/TG30“: gleiche Buchstaben vorn und hinten gehören zur Nummer.
            if prefix and letters and letters.group(0) == prefix:
                number, prefix = prefix + digits, None
            else:
                number = digits
        hits.append(
            NumberHit(
                number=normalize_number(number),
                raw=match.group(0),
                source="fraction",
                total=total,
                total_code=total_code,
                prefix=prefix,
            )
        )
    for pattern, source in ((_NO_NUMBER, "no"), (_HASH_NUMBER, "hash")):
        hits += [
            NumberHit(number=normalize_number(m.group(1)), raw=m.group(0), source=source)
            for m in pattern.finditer(text)
        ]
    hits += [
        NumberHit(number=normalize_number(m.group(1) + m.group(2)), raw=m.group(0), source="promo")
        for m in _PROMO_NUMBER.finditer(text)
    ]
    hits += [onepiece_hit(m) for m in _ONEPIECE_NUMBER.finditer(text)]
    return [hit for hit in hits if hit.number not in {"", "0"}]


def onepiece_hit(match: re.Match[str]) -> NumberHit:
    """One-Piece-Nummer aus einem Treffer von :data:`_ONEPIECE_NUMBER` (OCR-Fehler bereinigt)."""
    if match.group("promo") is not None:
        printed = f"P-{match.group('promo').translate(_DIGIT_FIX)}"
    else:
        code = _ONEPIECE_CODE_FIX.get(match.group("code"), match.group("code"))
        digits = match.group("set").translate(_DIGIT_FIX)
        printed = f"{code}{digits}-{match.group('num').translate(_DIGIT_FIX)}"
    return NumberHit(number=normalize_number(printed), raw=match.group(0), source="onepiece")


# ------------------------------------------------------------------ Setcodes

_CODE_TOKEN = re.compile(r"[A-Za-z0-9]{2,6}")


def set_code_variants(token: str) -> set[str]:
    """Mögliche Setcodes eines Tokens (casefold), inkl. OCR-Verwechslung „5“ ↔ „S“."""
    variants: set[str] = set()
    has_letter = any(c.isalpha() for c in token)
    has_digit = any(c.isdigit() for c in token)
    if has_letter and (has_digit or (token.isupper() and len(token) <= 4)):  # noqa: PLR2004
        variants.add(token.casefold())
    if token[0] == "5" and len(token) >= 2:  # noqa: PLR2004 – „512“ gelesen, „S12“ gedruckt
        variants.add(("s" + token[1:]).casefold())
    return variants


def parse_set_codes(texts: Iterable[str], numbers: Iterable[NumberHit] = ()) -> frozenset[str]:
    """Setcode-Kandidaten. Welche davon echte Sets sind, entscheidet der Katalogabgleich."""
    codes: set[str] = set()
    for text in texts:
        for token in _CODE_TOKEN.findall(normalize_text(text)):
            codes |= set_code_variants(token)
    codes |= {hit.prefix.casefold() for hit in numbers if hit.prefix}
    # Promo-Nummern wie „132/M-P“ oder „001/SV-P“: der Teil hinter dem Schrägstrich ist das Set.
    codes |= {hit.total_code.casefold() for hit in numbers if hit.total_code}
    return frozenset(codes | {code.replace("-", "") for code in codes})


# ------------------------------------------------------------------ Namen

_HP_SUFFIX = re.compile(r"\s*(?:KP|HP|PV|LV\.?)\s*\d+.*$", re.IGNORECASE)
_HP_PREFIX = re.compile(r"^(?:KP|HP|PV)\s*\d+\s*", re.IGNORECASE)
# Japanische Karten: das kleine „HP“ fehlt in der OCR oft, die Zahl klebt dann am Namen
# („ルファイヤーV220“). Zwei bis drei Ziffern nach Kana/Kanji (ggf. nach dem Logo) fallen
# weg – eine einzelne Ziffer gehört zum Namen („ポリゴン2“).
_CJK_HP_TAIL = re.compile(
    r"(?<=[^\x00-\x7f])((?:VMAX|VSTAR|V|GX|ex)?)\s*\d{2,3}[A-Za-z]?$", re.IGNORECASE
)
# Das „V“-Logo liest die OCR auf japanischen Karten gern als „ソ“ („ゼラオラソ“). Kein
# Pokémon-Name endet auf ソ – sonst passen alle Fassungen (GX, VMAX …) gleich gut, und die
# richtige fällt aus den Kandidaten für den Bildabgleich (Screenshot 28.10.).
_CJK_V_MISREAD = re.compile(r"(?<=[ァ-ヺー]{2})ソ$")
_STAGE_PREFIX = re.compile(
    r"^(?:BASIS|BASIC|PHASE\s*\d|STAGE\s*\d|たね|[12]進化|[12]退化|1化)\s*", re.IGNORECASE
)
_SENTENCE = re.compile(r"[。、，,:：;；!?！？「」()（）©®+=%×]")  # noqa: RUF001 – Satzzeichen
_NAME_STOPWORDS = frozenset(
    {
        "kp",
        "hp",
        "pv",
        "basis",
        "basic",
        "phase1",
        "phase2",
        "stage1",
        "stage2",
        "vmax",
        "vstar",
        "v",
        "ex",
        "gx",
        "たね",
        "1進化",
        "2進化",
        "fähigkeit",
        "ability",
        "弱点",
        "抵抗力",
        "にげる",
        "weakness",
        "resistance",
        "retreat",
        "schwäche",
        "resistenz",
        "rückzug",
        "pokémon",
        "pokemon",
        "trainer",
        "item",
        "supporter",
        "unterstützer",
        "stadion",
        "stadium",
        "energie",
        "energy",
        "gemmt",
        "gemmint",
        "mint",
        "psa",
        "bgs",
        "cgc",
        "nurversand",
        "versenden",
        "vregel",
        "vルール",
        "pokémon-ex-regel",
        "pokémonexregel",
    }
)
MAX_NAME_CANDIDATES = 8
_MIN_CJK_NAME, _MAX_CJK_NAME = 2, 12
_MIN_LATIN_NAME, _MAX_LATIN_NAME = 3, 28
_MAX_NAME_WORDS = 4
_MIN_LETTER_RATIO = 0.7


@dataclass(frozen=True)
class NameCandidate:
    """Eine Textzeile, die ein Kartenname sein könnte."""

    text: str
    key: str
    base: str
    height: float


def clean_name(text: str) -> str:
    """Entfernt KP-Angaben und Stufen-Wörter: „BASIS Glurak KP120“ → „Glurak“."""
    text = normalize_text(text)
    text = _STAGE_PREFIX.sub("", text)
    text = _HP_PREFIX.sub("", text)
    text = _HP_SUFFIX.sub("", text).strip()
    text = _CJK_HP_TAIL.sub(r"\1", text).strip()
    return _CJK_V_MISREAD.sub("V", text)


def name_candidate(line: OcrLine) -> NameCandidate | None:
    """Prüft, ob eine Zeile als Name taugt (kurz, überwiegend Buchstaben, kein Satz)."""
    text = clean_name(line.text)
    key = compact_key(text)
    if not key or key in _NAME_STOPWORDS or _SENTENCE.search(text):
        return None
    letters = sum(char.isalpha() for char in key)
    if letters / len(key) < _MIN_LETTER_RATIO:
        return None
    if is_cjk_text(key):
        if not _MIN_CJK_NAME <= len(key) <= _MAX_CJK_NAME:
            return None
    elif not _MIN_LATIN_NAME <= len(key) <= _MAX_LATIN_NAME or (
        len(text.split()) > _MAX_NAME_WORDS
    ):
        return None
    return NameCandidate(text=text, key=key, base=name_base(key), height=line.height)


def name_candidates(
    lines: Iterable[OcrLine], limit: int = MAX_NAME_CANDIDATES
) -> list[NameCandidate]:
    """Die größten Zeilen, die ein Name sein könnten – Namen sind auf Karten groß gedruckt."""
    found: dict[str, NameCandidate] = {}
    for line in lines:
        candidate = name_candidate(line)
        if candidate and (
            candidate.key not in found or found[candidate.key].height < candidate.height
        ):
            found[candidate.key] = candidate
    return sorted(found.values(), key=lambda c: c.height, reverse=True)[:limit]


# ------------------------------------------------------------------ Gesamtergebnis


@dataclass(frozen=True)
class TextFeatures:
    """Alle Merkmale eines Fotos aus der OCR."""

    numbers: tuple[NumberHit, ...] = ()
    set_codes: frozenset[str] = field(default_factory=frozenset)
    names: tuple[NameCandidate, ...] = ()
    language: LanguageGuess = field(default_factory=LanguageGuess)
    slab: SlabLabel | None = None
    line_count: int = 0

    @property
    def has_anchor(self) -> bool:
        """Gibt es etwas, womit sich im Katalog suchen lässt?"""
        return bool(self.numbers or self.names)

    def summary(self) -> dict[str, Any]:
        """Kompakte, JSON-fähige Darstellung (API-Antwort und Scan-Protokoll)."""
        return {
            "numbers": [
                {"number": hit.number, "total": hit.total, "raw": hit.raw} for hit in self.numbers
            ],
            "names": [candidate.text for candidate in self.names[:5]],
            "languages": list(self.language.languages),
            "slab": self.slab.summary() if self.slab else None,
            "lines": self.line_count,
        }


def _dedupe_numbers(hits: Iterable[NumberHit]) -> tuple[NumberHit, ...]:
    seen: dict[tuple[str, int | None, str | None], NumberHit] = {}
    for hit in hits:
        seen.setdefault((hit.number, hit.total, hit.total_code), hit)
    # Brüche mit Setgröße sind am aussagekräftigsten.
    return tuple(sorted(seen.values(), key=lambda hit: hit.source != "fraction"))


def extract_text_features(lines: Sequence[OcrLine]) -> TextFeatures:
    """Wertet alle OCR-Zeilen eines Fotos aus."""
    texts = [line.text for line in lines]
    numbers = _dedupe_numbers(hit for text in texts for hit in parse_numbers(text))
    slab = parse_slab(lines)
    names = name_candidates(lines)
    if slab and slab.name_hint:
        hint = NameCandidate(
            text=slab.name_hint,
            key=compact_key(slab.name_hint),
            base=name_base(compact_key(slab.name_hint)),
            height=1.0,  # Label-Name ist verlässlich → vorne einsortieren
        )
        names = [hint, *(candidate for candidate in names if candidate.key != hint.key)]
    language = guess_language(texts)
    if slab and slab.language_hint and not language.languages:
        language = LanguageGuess((slab.language_hint,), "label")
    return TextFeatures(
        numbers=numbers,
        set_codes=parse_set_codes(texts, numbers),
        names=tuple(names[:MAX_NAME_CANDIDATES]),
        language=language,
        slab=slab,
        line_count=len(lines),
    )
