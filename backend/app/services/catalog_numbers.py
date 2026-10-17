"""Kartennummern normalisieren und Suchanfragen in Name und Nummer zerlegen."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Token, das wie eine Kartennummer aussieht: 215, 007, 215/203, SV050, TG05, 125/SM-P, #42
_NUMBER_TOKEN = re.compile(r"^#?([A-Za-z]{0,5}\d{1,4}[A-Za-z]?)(/[A-Za-z0-9-]+)?$")
_LEADING_ZEROS = re.compile(r"(?<![0-9])0+(?=[0-9])")


def normalize_number(number: str) -> str:
    """Vergleichbare Form einer Kartennummer.

    ``"215/203"`` → ``"215"``, ``"007"`` → ``"7"``, ``"SV050"`` → ``"SV50"``,
    ``"tg05"`` → ``"TG5"``. Der Teil nach dem Schrägstrich (Setgröße) zählt nicht.
    """
    head = number.strip().lstrip("#").split("/", maxsplit=1)[0]
    head = re.sub(r"[\s-]+", "", head).upper()
    return _LEADING_ZEROS.sub("", head)


@dataclass(frozen=True)
class ParsedQuery:
    """Zerlegte Suchanfrage."""

    name: str
    number: str | None

    @property
    def is_empty(self) -> bool:
        return not self.name and self.number is None


def parse_query(query: str) -> ParsedQuery:
    """Trennt Name und Nummer: ``"nachtara 215"`` → Name ``"nachtara"``, Nummer ``"215"``.

    Als Nummer zählt das *letzte* passende Token, das eine Ziffer enthält; alles andere ist
    Name. Namen mit Ziffern wie „Porygon2“ bleiben Name (zu viele Buchstaben vor der Ziffer).
    """
    tokens = query.split()
    number: str | None = None
    for index in range(len(tokens) - 1, -1, -1):
        if _NUMBER_TOKEN.match(tokens[index]):
            number = normalize_number(tokens.pop(index))
            break
    return ParsedQuery(name=" ".join(tokens).strip(), number=number)
