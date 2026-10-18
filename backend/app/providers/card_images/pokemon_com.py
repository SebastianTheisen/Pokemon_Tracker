"""Offizielle Kartenbilder von pokemon.com (Deutsch und Englisch).

Die Kartendatenbank von pokemon.com legt ihre Bilder nach einem festen Muster ab::

    https://assets.pokemon.com/static-assets/content-assets/cms2-de-de/img/cards/web/SWSH7/SWSH7_DE_215.png
    https://assets.pokemon.com/static-assets/content-assets/cms2/img/cards/web/SV08/SV08_EN_162.png

Der Setcode entspricht meist der TCGdex-ID in Großbuchstaben (``swsh7`` → ``SWSH7``,
``swsh10tg`` → ``SWSH10TG``, ``smp`` → ``SMP``). Ob es das Bild gibt, wird geprüft, bevor
die Adresse gespeichert wird; ältere Sets (vor Sonne & Mond) gibt es dort nicht.
"""

from __future__ import annotations

import re

BASE_URL = "https://assets.pokemon.com/static-assets/content-assets"
_LOCALE_PATH = {"de": "cms2-de-de", "en": "cms2"}
_SAFE = re.compile(r"^[A-Z0-9]+$")


def official_image_url(set_external_id: str, number: str, language: str) -> str | None:
    """Erwartete Bildadresse oder ``None``, wenn Sprache oder Set nicht passen."""
    locale = _LOCALE_PATH.get(language)
    code = set_external_id.upper().replace(".", "").replace("-", "")
    printed = number.strip().upper()
    head = printed.lstrip("0") or "0"
    if locale is None or not _SAFE.match(code) or not _SAFE.match(head):
        return None
    return f"{BASE_URL}/{locale}/img/cards/web/{code}/{code}_{language.upper()}_{head}.png"
