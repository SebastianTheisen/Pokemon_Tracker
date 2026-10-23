"""Englische Namen asiatischer Sets."""

from __future__ import annotations

from app.services.set_names import translated_set_name


def test_japanese_set_names_are_translated() -> None:
    assert translated_set_name("S12", "ja", "パラダイムトリガー") == "Paradigm Trigger"
    assert translated_set_name("sv8a", "ja", "テラスタルフェスex") == "Terastal Festival ex"
    assert translated_set_name("SM1p", "ja", "サン&ムーン 強化拡張パック") == (
        "Sun & Moon Strengthening Expansion"
    )


def test_taiwan_and_korea_use_japanese_codes() -> None:
    assert translated_set_name("M2a", "zh-tw", "MEGAドリームex") == "MEGA Dream ex"
    assert translated_set_name("S4a", "ko", "샤이니스타V") == "Shiny Star V"


def test_no_translation_for_western_or_unknown_sets() -> None:
    assert translated_set_name("S12", "de", "x") is None
    assert translated_set_name("AC2a", "zh-tw", "AC2a") is None
    assert translated_set_name("M6a", "ja", "30th Celebration") is None  # schon gleich
