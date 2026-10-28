"""Textmerkmale und Slab-Labels – mit OCR-Zeilen aus dem Phase-0-Spike (echte Testfotos)."""

from __future__ import annotations

import pytest

from app.scanner.ocr import OcrLine
from app.scanner.slab import parse_slab
from app.scanner.text import (
    clean_name,
    compact_key,
    extract_text_features,
    guess_language,
    name_base,
    name_candidate,
    normalize_text,
    parse_numbers,
    parse_set_codes,
    set_code_variants,
)
from tests.scan_helpers import lines


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("110/098", [("110", 98, None)]),
        ("512 F 110/098 SR", [("110", 98, None)]),
        ("DR231/182 會会", [("231", 182, "DR")]),
        ("11O/O98", [("110", 98, None)]),  # O statt 0
        ("1I0/O98", [("110", 98, None)]),  # I statt 1
        ("\uff11\uff11\uff10\uff0f\uff10\uff19\uff18", [("110", 98, None)]),  # Vollbreite
        ("TG05/TG30", [("TG5", None, None)]),
        ("001/SV-P", [("1", None, None)]),
        ("No.007", [("7", None, None)]),
        ("NO 042", [("42", None, None)]),
        ("#110", [("110", None, None)]),
        ("SWSH050", [("SWSH50", None, None)]),
        ("OP01-001", [("OP1001", None, None)]),  # One Piece: Set + Nummer
        ("0P05-1I9 SR", [("OP5119", None, None)]),  # OCR: 0 statt O, I statt 1
        ("ST10 005", [("ST10005", None, None)]),
        ("P-001", [("P1", None, None)]),
        ("HP220", []),
        ("LV.15 HP50", []),
        ("2022 POKEMON JPN.SWSH", []),
        ("1/2", []),  # zu kleine Setgröße → kein Kartenbruch
        ("000/100", []),
    ],
)
def test_parse_numbers(text: str, expected: list[tuple[str, int | None, str | None]]) -> None:
    assert [(hit.number, hit.total, hit.prefix) for hit in parse_numbers(text)] == expected


def test_promo_numbers_keep_their_code() -> None:
    (hit,) = parse_numbers("001/SV-P")
    assert hit.total_code == "SV-P"
    assert hit.source == "fraction"


def test_set_code_variants_cover_ocr_confusion() -> None:
    assert set_code_variants("S12") == {"s12"}
    assert set_code_variants("512") == {"s12"}  # „5“ statt „S“
    assert set_code_variants("SV8a") == {"sv8a"}
    assert set_code_variants("DRI") == {"dri"}
    assert set_code_variants("Team") == set()
    assert set_code_variants("123") == set()


def test_promo_total_counts_as_set_code() -> None:
    # Testfoto des Nutzers: Pikachu ex „132/M-P“ (Mega-Promo, JP)
    features = extract_text_features(lines("ピカチュウex", "J PROMO 132/M-P"))
    assert [(hit.number, hit.total_code) for hit in features.numbers] == [("132", "M-P")]
    assert {"m-p", "mp"} <= features.set_codes


def test_parse_set_codes_includes_number_prefix() -> None:
    numbers = parse_numbers("DR231/182")
    assert {"dr", "s12"} <= parse_set_codes(["512 F 110/098 SR", "DR231/182"], numbers)


def test_normalize_and_keys() -> None:
    assert normalize_text("ブラッキ-") == "ブラッキー"
    assert normalize_text("ﾙｷﾞｱ") == "ルギア"  # Halbbreite
    assert compact_key("Team Rocket's Mewtwo ex") == "teamrocketsmewtwoex"
    assert name_base("teamrocketsmewtuex") == "teamrocketsmewtu"
    assert name_base("ルギアv") == "ルギア"
    assert name_base("v") == "v"
    # Echtes Binderfoto (28.10.): kleine Kana als große gelesen, „ex“ als „X“/„EX“/„E“.
    assert compact_key("シヤワーズ") == compact_key("シャワーズ")
    assert name_base(compact_key("リーフイアEX")) == name_base(compact_key("リーフィアex"))
    assert name_base(compact_key("サンダースX")) == "サンダース"
    assert name_base(compact_key("グレイァE")) == "グレイア"
    assert name_base("pikachu") == "pikachu"  # lateinische Namen bleiben
    assert clean_name("BASIS Glurak KP120") == "Glurak"
    assert clean_name("HP80 ルギア") == "ルギア"


@pytest.mark.parametrize(
    ("text", "accepted"),
    [
        ("ルギアV", True),
        ("Team Rockets MewtuX", True),
        ("BASIS", False),
        ("Fähigkeit", False),
        ("280", False),
        ("Dieses Pokémon kann nicht angreifen, es sei denn, du hast", False),
        ("当分の手れを1秘トラッシュする。", False),
        ("ab", False),  # zu kurz (Latein)
        ("Eins Zwei Drei Vier Fünf", False),  # zu viele Wörter
        ("ルギアルギアルギアルギアルギア", False),  # zu lang (CJK)
        ("x2", False),
    ],
)
def test_name_candidate_filter(text: str, accepted: bool) -> None:
    assert (name_candidate(OcrLine(text=text, height=0.05)) is not None) is accepted


@pytest.mark.parametrize(
    ("texts", "languages", "script"),
    [
        (["ルギアV", "かぜよみ"], ("ja",), "kana"),
        (["루기아V", "기술"], ("ko",), "hangul"),
        (["抛提2次硬币。如果全为正面的话。则追加造成20伤害"], ("zh-cn", "zh-tw"), "han"),
        (["拋擲2次硬幣。如果皆為正面的話。則追加造成20傷害"], ("zh-tw", "zh-cn"), "han"),
        (["Fähigkeit", "Dieses Pokémon kann nicht angreifen"], ("de", "en"), "latin"),
        (["Ability", "Your opponent's Active Pokémon"], ("en", "de"), "latin"),
        (["220", "HP"], (), None),
    ],
)
def test_guess_language(texts: list[str], languages: tuple[str, ...], script: str | None) -> None:
    guess = guess_language(texts)
    assert guess.languages == languages
    assert guess.script == script
    assert guess.primary == (languages[0] if languages else None)


def test_features_of_spike_photo_03() -> None:
    features = extract_text_features(
        lines(
            "ルギアV",
            "たね",
            "220",
            "HP",
            "かぜよみ",
            "当分の手れを1秘トラッシュする。その後、自分の面礼を3段引く。",
            "512 F 110/098 SR",
            "©2022 Pokémon/Nintendo/Creatures/GAM",
        )
    )
    assert [(hit.number, hit.total) for hit in features.numbers] == [("110", 98)]
    assert "s12" in features.set_codes
    assert features.names[0].text == "ルギアV"
    assert features.language.languages == ("ja",)
    assert features.slab is None
    assert features.has_anchor
    summary = features.summary()
    assert summary["numbers"] == [{"number": "110", "total": 98, "raw": "110/098"}]
    assert summary["lines"] == 8


def test_slab_label_of_spike_photo_04() -> None:
    features = extract_text_features(
        lines(
            "#110",
            "2022 POKEMON JPN.SWSH",
            "GEM MT",
            "FA/LUGIA V",
            "10",
            "PARADIGMTRIGGER",
            "73270136",
            "ルギアV",
            "PSA.",
        )
    )
    assert features.slab is not None
    assert features.slab.summary() == {
        "company": "PSA",
        "grade": "10",
        "number": "110",
        "name": "LUGIA V",
        "language": "ja",
        "cert": "73270136",
    }
    assert features.names[0].text == "LUGIA V"  # Label-Name zuerst
    assert ("110", None) in [(hit.number, hit.total) for hit in features.numbers]


def test_slab_fallbacks() -> None:
    # OCR „FSA“ statt „PSA“, Note in eigener Zeile (Testfoto 01).
    slab = parse_slab(lines("GEM MT", "xxxx", "10", "FSA"))
    assert slab is not None
    assert (slab.company, slab.grade, slab.name_hint) == ("PSA", "10", None)

    # Note im selben Text, BGS.
    bgs = parse_slab(lines("BGS", "2021 POKEMON EVOLVING SKIES", "UMBREON VMAX", "GEM MINT 9.5"))
    assert bgs is not None
    assert (bgs.company, bgs.grade, bgs.name_hint, bgs.language_hint) == (
        "BGS",
        "9.5",
        "UMBREON VMAX",
        None,
    )

    # Nur Notenwort ohne Zahl → PSA-Tabelle; bei CGC keine Vermutung.
    assert parse_slab(lines("PSA", "NM-MT")).grade == "8"  # type: ignore[union-attr]
    assert parse_slab(lines("CGC", "MINT+")).grade is None  # type: ignore[union-attr]

    # Firma ohne Notenwort (z. B. Werbung) bzw. Notenwort ohne Firma → kein Slab.
    assert parse_slab(lines("PSA Shop", "Versand")) is None
    assert parse_slab(lines("GEM MT", "10")) is None
    # Unplausible Note wird ignoriert.
    assert parse_slab(lines("PSA", "GEM MT 11")).grade == "10"  # type: ignore[union-attr]
    assert parse_slab(lines("PSA", "2022 POKEMON KOREAN", "PIKACHU", "MINT 9")) is not None
    korean = parse_slab(lines("PSA", "2022 POKEMON KOREAN", "PIKACHU", "MINT 9"))
    assert korean is not None
    assert (korean.language_hint, korean.name_hint) == ("ko", "PIKACHU")


def test_slab_language_hint_used_when_text_has_none() -> None:
    features = extract_text_features(
        lines("PSA", "2022 POKEMON JPN.SWSH", "FA/LUGIA V", "GEM MT 10")
    )
    assert features.language.languages == ("ja",)
    assert features.language.script == "label"


def test_psa_label_with_logo_only() -> None:
    """Neues PSA-Label: „PSA“ nur als Logo – OCR-Zeilen wie beim echten Foto (20.10.2026)."""
    slab = parse_slab(
        lines(
            "2025 POKEMON M2a JP",
            "#246",
            "MEGA DRAGONITE ex",
            "GEM MT",
            "SPECIAL ART RARE",
            "10",
            "154634082",
            "メガカイュービX",
        )
    )
    assert slab is not None
    assert (slab.company, slab.grade, slab.number, slab.language_hint) == ("PSA", "10", "246", "ja")
    assert slab.name_hint == "MEGA DRAGONITE EX"


def test_black_label_and_no_false_psa() -> None:
    black = parse_slab(lines("BECKETT", "2021 POKEMON", "PRISTINE 10", "BLACK LABEL"))
    assert black is not None and black.grade == "10 BL"
    # Ohne Kopfzeile oder Zertifikatsnummer bleibt es keine PSA-Erkennung.
    assert parse_slab(lines("GEM MT", "10", "154634082")) is None
    assert parse_slab(lines("2025 POKEMON M2a JP", "GEM MT", "10")) is None


def test_one_piece_slab_label() -> None:
    features = extract_text_features(
        lines(
            "2023 ONE PIECE JAPANESE",
            "OP05-AWAKENING OF THE NEW ERA",
            "MONKEY.D.LUFFY",
            "#OP05-119",
            "GEM MT",
            "10",
            "81234567",
            "PSA",
        )
    )

    assert features.slab is not None
    assert (features.slab.company, features.slab.grade, features.slab.cert) == (
        "PSA",
        "10",
        "81234567",
    )
    assert features.slab.language_hint == "ja"
    assert features.names[0].text == "MONKEY.D.LUFFY"
    assert "OP5119" in [hit.number for hit in features.numbers]
