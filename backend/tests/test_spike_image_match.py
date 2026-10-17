"""Tests für den Bildabgleich-Spike – offline, mit simuliertem TCGdex (httpx.MockTransport).

Als „Katalogbilder“ dienen Fotos aus dem Testsatz: 04.jpg zeigt dieselbe Karte wie 03.jpg
(Lugia V, 110/098), 06.jpg eine andere (Lugia, 142/103).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("cv2")

import httpx
from PIL import Image

from scripts import spike_image_match as matcher
from scripts.spike_scanner import load_image

TESTSET = Path(__file__).resolve().parents[2] / "scanner_testset"


def _webp_bytes(photo: str) -> bytes:
    buffer = io.BytesIO()
    with Image.open(TESTSET / photo) as image:
        image.convert("RGB").save(buffer, format="WEBP")
    return buffer.getvalue()


def _fake_tcgdex() -> httpx.MockTransport:
    images = {"/ja/s12/110/high.webp": "04.jpg", "/ja/m6a/142/high.webp": "06.jpg"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/ja/cards":
            assert request.url.params["name"] == "ルギアV"
            return httpx.Response(
                200,
                json=[
                    {"id": "s12-110", "localId": "110", "name": "ルギアV",
                     "image": "https://assets.tcgdex.net/ja/s12/110"},
                    {"id": "m6a-142", "localId": "142", "name": "ルギアV",
                     "image": "https://assets.tcgdex.net/ja/m6a/142"},
                    {"id": "x-1", "localId": "1", "name": "ルギアV"},  # ohne Bild
                ],
            )  # fmt: skip
        if request.url.path in images:
            return httpx.Response(200, content=_webp_bytes(images[request.url.path]))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_same_card_scores_far_above_other_card() -> None:
    photo = matcher.extract_features(load_image(TESTSET / "03.jpg"))
    same = matcher.extract_features(load_image(TESTSET / "04.jpg"))
    other = matcher.extract_features(load_image(TESTSET / "06.jpg"))

    assert matcher.match_score(photo, same) > 5 * max(matcher.match_score(photo, other), 10)


def test_evaluate_photo_ranks_correct_card_first(tmp_path: Path) -> None:
    expected = matcher.Expected("03.jpg", "ルギアV", "110/098", "ja")

    with httpx.Client(transport=_fake_tcgdex()) as client:
        result = matcher.evaluate_photo(client, expected, TESTSET, tmp_path)

    assert result.correct_rank == 1
    assert [c.card_id for c in result.ranked][:2] == ["s12-110", "m6a-142"]
    assert result.note == "1 Kandidaten ohne Bild"
    assert len(list(tmp_path.iterdir())) == 2  # Katalogbilder wurden gecacht


@pytest.mark.parametrize(
    ("value", "head"),
    [("110/098", "110"), ("007", "7"), ("SV050", "SV50"), ("TG05", "TG5"), ("0", "0")],
)
def test_number_head(value: str, head: str) -> None:
    assert matcher._number_head(value) == head


def test_load_expected_reads_language(tmp_path: Path) -> None:
    csv_file = tmp_path / "soll.csv"
    csv_file.write_text("datei;name;nummer;sprache\n01.jpg;Glurak;039/165;de\n", encoding="utf-8")

    assert matcher.load_expected(csv_file) == [
        matcher.Expected("01.jpg", "Glurak", "039/165", "de")
    ]
