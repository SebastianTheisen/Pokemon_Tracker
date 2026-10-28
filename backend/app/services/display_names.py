"""Namen, wie die App sie zeigt: übersetzt, wenn es eine Übersetzung gibt, sonst das Original.

* Pokémon (Japanisch, Koreanisch, Chinesisch): deutscher Pokémon-Name
  (:mod:`app.services.card_names`), Sets mit englischem Namen (:mod:`app.services.set_names`).
* One Piece (Japanisch): englischer Name aus der englischen Kartenliste (``name_en``).

Gleiche Regel wie ``translated_name`` in den Katalog-Schemas – für Texte, die der Server
selbst baut (Tausch-Rechner, Push-Nachrichten, Scan-Hinweis, Sortierung).
"""

from __future__ import annotations

from app.models import Card, CardSet, Game
from app.services.card_names import translate_card_name
from app.services.set_names import translated_set_name


def translated_card_name(card: Card) -> str | None:
    """Übersetzter Kartenname oder ``None``."""
    if card.card_set.game != Game.POKEMON.value:
        return card.name_en  # Pokémon-Namen im Text zu suchen wäre hier Unsinn
    return translate_card_name(card.name, card.language)


def translated_set_title(card_set: CardSet) -> str | None:
    """Übersetzter Setname oder ``None``."""
    if card_set.game != Game.POKEMON.value:
        return card_set.name_en
    return translated_set_name(card_set.external_id, card_set.language, card_set.name)


def card_display_name(card: Card) -> str:
    return translated_card_name(card) or card.name


def set_display_name(card_set: CardSet) -> str:
    return translated_set_title(card_set) or card_set.name
