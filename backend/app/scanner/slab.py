"""Grading-Labels (PSA, BGS/Beckett, CGC) aus dem OCR-Text lesen (Plan 5.6, Slab-Pfad).

Ein PSA-Label sieht im OCR z. B. so aus (Testfoto 04)::

    #110 · 2022 POKEMON JPN.SWSH · GEM MT · FA/LUGIA V · 10 · PARADIGMTRIGGER · 73270136 · PSA

Erkannt wird ein Slab, wenn eine Grading-Firma **und** eine Notenbezeichnung vorkommen.
Daraus entstehen: Firma, Note, Nummer (``#110``), englischer Name (``LUGIA V``) und ein
Sprachhinweis (``JPN``). Gegradete Karten zeigt die App immer zur Bestätigung an.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.scanner.ocr import OcrLine

# OCR liest „PSA“ gern als „FSA“ oder „P5A“ (Testfoto 01).
_COMPANIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PSA", re.compile(r"(?<![A-Z])[PF][S5]A(?![A-Z])")),
    ("BGS", re.compile(r"(?<![A-Z])(?:BGS|BECKETT)(?![A-Z])")),
    ("CGC", re.compile(r"(?<![A-Z])CGC(?![A-Z])")),
)
_GRADE_WORD = re.compile(
    r"(?<![A-Z])(GEM\s*-?\s*MT|GEM\s*MINT|PRISTINE|NM\s*-?\s*MT\+?|EX\s*-?\s*MT\+?|VG\s*-?\s*EX\+?"
    r"|MINT\+?|NM\+?|EX\+?|VG\+?|GOOD\+?|FAIR|POOR|AUTHENTIC)(?![A-Z])"
    r"(?:\s*(\d{1,2}(?:\.5)?))?"
)
_GRADE_NUMBER = re.compile(r"^(\d{1,2}(?:\.5)?)$")
# PSA-Notenbezeichnungen → Note, falls die Zahl nicht gelesen wurde.
_PSA_WORD_GRADES = {
    "GEMMT": "10",
    "MINT": "9",
    "NMMT": "8",
    "NM": "7",
    "EXMT": "6",
    "EX": "5",
    "VGEX": "4",
    "VG": "3",
    "GOOD": "2",
    "FAIR": "1.5",
    "POOR": "1",
}
_LANGUAGE_HINTS = (
    ("JPN", "ja"),
    ("JAPANESE", "ja"),
    ("KOREAN", "ko"),
    ("KOR", "ko"),
    ("CHINESE", "zh-tw"),
    ("GERMAN", "de"),
)
_NAME_LINE = re.compile(r"^[A-Z][A-Z .'/&-]{2,40}$")
_NOT_A_NAME = re.compile(
    r"POKEMON|POKÉMON|GEM|MINT|PRISTINE|PSA|BGS|CGC|BECKETT|AUTHENTIC|HOLO$|^\d|CERT"
    r"|BASIC|BASIS|STAGE|WEAKNESS|RESISTANCE|RETREAT|ABILITY|TRAINER"
)
_MAX_GRADE = 10.0
_GRADE_SEARCH_DISTANCE = 3


@dataclass(frozen=True)
class SlabLabel:
    """Gelesenes Grading-Label."""

    company: str
    grade: str | None = None
    number: str | None = None
    name_hint: str | None = None
    language_hint: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "grade": self.grade,
            "number": self.number,
            "name": self.name_hint,
            "language": self.language_hint,
        }


def _upper(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().upper()


def _find_company(texts: Sequence[str]) -> str | None:
    for company, pattern in _COMPANIES:
        if any(pattern.search(text) for text in texts):
            return company
    return None


def _valid_grade(value: str) -> bool:
    return 0 < float(value) <= _MAX_GRADE


def _find_grade(texts: Sequence[str], company: str) -> tuple[bool, str | None]:
    """(Notenbezeichnung gefunden?, Note). Die Zahl steht oft in einer eigenen Zeile."""
    for index, text in enumerate(texts):
        match = _GRADE_WORD.search(text)
        if not match:
            continue
        if match.group(2) and _valid_grade(match.group(2)):
            return True, match.group(2)
        nearby = texts[max(0, index - _GRADE_SEARCH_DISTANCE) : index + _GRADE_SEARCH_DISTANCE + 1]
        for other in nearby:
            number = _GRADE_NUMBER.match(other.strip())
            if number and _valid_grade(number.group(1)):
                return True, number.group(1)
        word = re.sub(r"[\s+-]", "", match.group(1))
        return True, _PSA_WORD_GRADES.get(word) if company == "PSA" else None
    return False, None


def _find_name(texts: Sequence[str]) -> str | None:
    """Kartenname auf dem Label: „FA/LUGIA V“ → „LUGIA V“ (Zusatz vor dem Schrägstrich weg).

    Bevorzugt Zeilen mit Schrägstrich (typisch für PSA), sonst die erste Großbuchstaben-Zeile
    nach der Zeile mit „POKEMON“ (Jahr + Spiel + Set).
    """
    after_header = False
    fallback: str | None = None
    for text in texts:
        if "POKEMON" in text or "POKÉMON" in text:
            after_header = True
            continue
        if not _NAME_LINE.match(text) or _NOT_A_NAME.search(text):
            continue
        name = text.rsplit("/", maxsplit=1)[-1].strip()
        if len(name) < 3:  # noqa: PLR2004
            continue
        if "/" in text:
            return name
        if after_header and fallback is None:
            fallback = name
    return fallback


def parse_slab(lines: Sequence[OcrLine]) -> SlabLabel | None:
    """Liest ein Grading-Label – oder ``None``, wenn keins im Bild ist."""
    texts = [_upper(line.text) for line in lines]
    company = _find_company(texts)
    if company is None:
        return None
    has_grade_word, grade = _find_grade(texts, company)
    if not has_grade_word:
        return None
    number = next(
        (match.group(1) for text in texts if (match := re.search(r"#\s*(\d{1,4})\b", text))),
        None,
    )
    language = next(
        (
            code
            for text in texts
            if "POKEMON" in text or "POKÉMON" in text
            for keyword, code in _LANGUAGE_HINTS
            if re.search(rf"(?<![A-Z]){keyword}(?![A-Z])", text)
        ),
        None,
    )
    return SlabLabel(
        company=company,
        grade=grade,
        number=number.lstrip("0") or None if number else None,
        name_hint=_find_name(texts),
        language_hint=language,
    )
