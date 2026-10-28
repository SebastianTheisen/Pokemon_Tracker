"""Englische Namen asiatischer Sets („パラダイムトリガー“ → „Paradigm Trigger“).

Japanische Sets haben keine deutschen Namen, aber offizielle englische (Bulbapedia,
PriceCharting). Taiwan und Korea übernehmen die japanischen Set-Codes – der Name gilt dort
ebenso. Grundlage: ``app/data/set_names.json`` (Set-Code → Name).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "set_names.json"
TRANSLATED_LANGUAGES = frozenset({"ja", "ko", "zh-tw"})


@cache
def _names() -> dict[str, str]:
    data: dict[str, dict[str, str]] = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {_code(code): name for code, name in data["sets"].items()}


def _code(code: str) -> str:
    """„SM-P“ und „SMP“ sind dasselbe Set (Schreibweisen der Quellen)."""
    return code.casefold().replace("-", "")


def translated_set_name(external_id: str, language: str, name: str) -> str | None:
    """Englischer Name oder ``None`` (andere Sprache, unbekannter Code, Name schon gleich)."""
    if language not in TRANSLATED_LANGUAGES:
        return None
    translated = _names().get(_code(external_id))
    return translated if translated and translated.casefold() != name.casefold() else None
