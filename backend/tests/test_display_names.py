"""Anzeigenamen in Texten des Servers (Tausch-Rechner, Push, Scan-Hinweis)."""

from __future__ import annotations

from app.models import Card, CardSet
from app.services.display_names import card_display_name, set_display_name
from app.services.trades import TradeLine, _label


def _card(name: str, *, language: str, set_id: str, set_name: str, game: str = "pokemon") -> Card:
    card_set = CardSet(external_id=set_id, language=language, name=set_name, game=game)
    return Card(language=language, number="110", number_norm="110", name=name, card_set=card_set)


def test_japanese_pokemon_card_in_trade_label() -> None:
    """Rückmeldung: Im Tausch-Rechner stand „ルギアV (パラダイムトリガー 110)“."""
    lugia = _card("ルギアV", language="ja", set_id="S12", set_name="パラダイムトリガー")
    line = TradeLine(side="give", quantity=1, grading_company="PSA", grade="10")

    assert card_display_name(lugia) == "Lugia V"
    assert set_display_name(lugia.card_set) == "Paradigm Trigger"
    assert _label(lugia, None, line) == "Lugia V (Paradigm Trigger 110) · PSA 10"


def test_german_and_one_piece_names() -> None:
    glurak = _card("Glurak", language="de", set_id="sv10", set_name="Ewige Rivalen")
    assert card_display_name(glurak) == "Glurak"
    assert set_display_name(glurak.card_set) == "Ewige Rivalen"

    roger = _card(
        "ゴール・D・ロジャー (Parallel)",
        language="ja",
        set_id="op-OP09",
        set_name="ブースターパック 受け継がれる意志",
        game="onepiece",
    )
    roger.name_en = "Gol.D.Roger (Parallel)"
    roger.card_set.name_en = "Emperors in the New World"
    assert card_display_name(roger) == "Gol.D.Roger (Parallel)"
    assert set_display_name(roger.card_set) == "Emperors in the New World"
