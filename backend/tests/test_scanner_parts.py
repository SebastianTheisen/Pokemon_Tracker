"""Bausteine des Scanners: Bild laden, Bildabgleich, Ablage, Katalogbilder, Binder, Punkte."""

from __future__ import annotations

import asyncio
import io
import os
import time
import uuid
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from PIL import Image

from app.models import Card, CardSet
from app.scanner.binder import binder_cells, split_grid
from app.scanner.catalog_images import CatalogImageIndex, download_url
from app.scanner.imaging import (
    InvalidImageError,
    card_crop,
    decode_image,
    downscale,
    encode_jpeg,
)
from app.scanner.matching import ImageFeatures, extract_features, match_score
from app.scanner.storage import FeatureCache, PendingScans, ReferenceStore
from app.scanner.text import LanguageGuess, extract_text_features
from app.scanner.twins import TwinDecision, pick_twin
from app.services.scan_scoring import (
    Candidate,
    is_confident,
    language_penalty,
    name_similarity,
    rank,
    score_text,
)
from tests.scan_helpers import crop_jpeg, lines, photo

# ------------------------------------------------------------------ Bild laden


def _encoded(image: Image.Image, fmt: str, **options: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def test_decode_downscales_and_returns_bgr() -> None:
    red = Image.new("RGB", (3000, 1500), (255, 0, 0))
    image = decode_image(_encoded(red, "PNG"))
    assert image.shape == (640, 1280, 3)
    assert tuple(image[0, 0]) == (0, 0, 255)  # BGR


def test_decode_respects_exif_rotation() -> None:
    portrait = Image.new("RGB", (200, 100), (0, 0, 0))
    exif = portrait.getexif()
    exif[0x0112] = 6  # 90° gedreht
    image = decode_image(_encoded(portrait, "JPEG", exif=exif))
    assert image.shape[:2] == (200, 100)


def test_decode_supports_heic() -> None:
    from pillow_heif import from_pillow  # noqa: PLC0415

    buffer = io.BytesIO()
    from_pillow(Image.new("RGB", (64, 48), (0, 128, 0))).save(buffer, quality=90)
    assert decode_image(buffer.getvalue()).shape == (48, 64, 3)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "leer"),
        (b"kein bild", "kein lesbares Bild"),
        (_encoded(Image.new("RGB", (10, 10)), "GIF"), "GIF wird nicht unterstützt"),
        (_encoded(Image.new("RGB", (10, 10)), "PNG")[:40], "kein lesbares Bild"),
    ],
)
def test_decode_rejects_bad_files(data: bytes, message: str) -> None:
    with pytest.raises(InvalidImageError, match=message):
        decode_image(data)


def test_decode_rejects_too_many_pixels() -> None:
    with pytest.raises(InvalidImageError, match="zu viele Pixel"):
        decode_image(_encoded(Image.new("RGB", (2000, 2000)), "PNG"), max_pixels=1_000_000)


def test_downscale_and_encode() -> None:
    image = np.zeros((100, 400, 3), dtype=np.uint8)
    assert downscale(image, 200).shape == (50, 200, 3)
    assert downscale(image, 1000) is image
    data = encode_jpeg(image, max_side=200)
    assert Image.open(io.BytesIO(data)).size == (200, 50)


def test_card_crop_finds_card_on_real_photo() -> None:
    crop = card_crop(photo("06.jpg"))  # flach auf dunklem Untergrund
    assert crop is not None
    assert crop.shape == (880, 630, 3)
    assert card_crop(np.full((400, 300, 3), 128, dtype=np.uint8)) is None


# ------------------------------------------------------------------ Bildabgleich


def test_same_card_matches_different_photos() -> None:
    lugia_toploader = extract_features(photo("03.jpg"))
    lugia_slab = extract_features(photo("04.jpg"))
    other = extract_features(photo("07.jpg"))
    assert match_score(lugia_slab, lugia_toploader) >= 50
    assert match_score(other, lugia_toploader) < 25


def test_features_round_trip_and_validation() -> None:
    features = extract_features(photo("06.jpg"), max_features=500)
    restored = ImageFeatures.from_bytes(features.to_bytes())
    assert len(restored) == len(features) <= 500
    assert restored.descriptors.dtype == np.uint8
    assert np.array_equal(restored.points, features.points)

    buffer = io.BytesIO()
    np.savez_compressed(buffer, points=np.zeros((3, 2)), descriptors=np.zeros((2, 128)))
    with pytest.raises(ValueError, match="Ungültige"):
        ImageFeatures.from_bytes(buffer.getvalue())


def test_empty_images_have_no_features() -> None:
    blank = extract_features(np.full((100, 100, 3), 200, dtype=np.uint8))
    assert len(blank) == 0
    assert match_score(blank, extract_features(photo("06.jpg"))) == 0


# ------------------------------------------------------------------ Ablage


def test_feature_cache(tmp_path: Path) -> None:
    cache = FeatureCache(tmp_path)
    url = "https://assets.tcgdex.net/ja/S12/110"
    features = extract_features(photo("03.jpg"), max_features=200)

    assert cache.get(url) is None
    cache.mark_missing(url)
    assert cache.missing_since(url) is not None
    cache.put(url, features)
    assert cache.missing_since(url) is None
    cached = cache.get(url)
    assert cached is not None
    assert len(cached) == len(features)

    # Defekte Datei → wird gelöscht und neu geladen.
    (tmp_path / "catalog" / f"{cache.key(url)}.npz").write_bytes(b"kaputt")
    assert cache.get(url) is None
    assert not (tmp_path / "catalog" / f"{cache.key(url)}.npz").exists()


def test_reference_store(tmp_path: Path) -> None:
    store = ReferenceStore(tmp_path)
    user, reference = uuid.uuid4(), uuid.uuid4()
    features = extract_features(photo("06.jpg"), max_features=100)

    assert store.prune(set()) == 0  # noch kein Ordner
    store.save(user, reference, b"jpeg", features)
    assert store.image(user, reference) == b"jpeg"
    loaded = store.features(user, reference)
    assert loaded is not None
    assert len(loaded) == len(features)
    assert store.features(user, uuid.uuid4()) is None
    assert store.image(user, uuid.uuid4()) is None

    (tmp_path / "references" / str(user) / "fremd.txt").write_text("x")
    assert store.prune({(user, reference)}) == 0
    assert store.prune(set()) == 2
    store.delete(user, reference)  # schon weg → kein Fehler


def test_pending_scans_expire_and_belong_to_user(monkeypatch: pytest.MonkeyPatch) -> None:
    pending = PendingScans(ttl_seconds=60, max_entries=2)
    owner, stranger = uuid.uuid4(), uuid.uuid4()
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    pending.put(first, owner, b"1")
    pending.put(second, owner, b"2")
    pending.put(third, owner, b"3")  # verdrängt den ältesten

    assert len(pending) == 2
    assert not pending.contains(first)
    assert pending.pop(second, stranger) is None  # fremder Nutzer
    item = pending.pop(second, owner)
    assert item is not None
    assert item.image_jpeg == b"2"
    assert pending.pop(second, owner) is None  # nur einmal

    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now + 61)
    assert not pending.contains(third)


# ------------------------------------------------------------------ Katalogbilder


async def _run_now(func: Callable[..., Any], *args: Any) -> Any:
    return await asyncio.to_thread(func, *args)


def _index(
    tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response]
) -> tuple[CatalogImageIndex, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    index = CatalogImageIndex(
        FeatureCache(tmp_path),
        client,
        _run_now,
        allowed_hosts=["assets.tcgdex.net"],
        memory_entries=1,
    )
    return index, client


def test_download_url() -> None:
    assert download_url("https://assets.tcgdex.net/ja/S12/110") == (
        "https://assets.tcgdex.net/ja/S12/110/high.webp"
    )
    assert download_url("https://assets.tcgdex.net/x.png") == "https://assets.tcgdex.net/x.png"
    # Andere Quellen: Adresse unverändert (z. B. ohne Endung bei scrydex).
    scrydex = "https://images.scrydex.com/pokemon/me2pt5-1/large"
    assert download_url(scrydex) == scrydex


async def test_catalog_index_downloads_caches_and_guards(tmp_path: Path) -> None:
    calls: list[str] = []
    jpeg = crop_jpeg("03.jpg")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if path.startswith("/ok"):
            return httpx.Response(200, content=jpeg)
        if path.startswith("/kaputt"):
            return httpx.Response(200, content=b"kein bild")
        if path.startswith("/fehler"):
            return httpx.Response(503)
        if path.startswith("/riesig"):
            return httpx.Response(200, content=b"\0" * (9 * 1024 * 1024))
        return httpx.Response(404)

    index, client = _index(tmp_path, handler)
    async with client:
        ok = "https://assets.tcgdex.net/ok/1"
        first = await index.features_for(ok)
        assert first is not None
        assert len(first) > 100
        assert await index.features_for(ok) is first  # Speicher
        await index.features_for("https://assets.tcgdex.net/ok/2")  # verdrängt /ok/1
        assert await index.features_for(ok) is not None  # Datei-Cache, kein Download
        assert calls.count(f"{ok}/high.webp") == 1

        # Fehlt bei der Quelle oder ist kein Bild → gemerkt, kein erneuter Abruf.
        for url in ("https://assets.tcgdex.net/fehlt/1", "https://assets.tcgdex.net/kaputt/1"):
            assert await index.features_for(url) is None
            assert await index.features_for(url) is None
            assert calls.count(f"{url}/high.webp") == 1

        # Netzfehler / zu groß → nicht gemerkt, nächstes Mal neu versuchen.
        for url in ("https://assets.tcgdex.net/fehler/1", "https://assets.tcgdex.net/riesig/1"):
            assert await index.features_for(url) is None
            assert await index.features_for(url) is None
            assert calls.count(f"{url}/high.webp") == 2

        # SSRF-Schutz: andere Hosts und HTTP werden gar nicht angefragt.
        before = len(calls)
        blocked: tuple[str | None, ...] = (
            None,
            "",
            "https://evil.example.com/ok/1",
            "http://assets.tcgdex.net/ok/1",
            "https://169.254.169.254/latest",
        )
        for blocked_url in blocked:
            assert await index.features_for(blocked_url) is None
        assert len(calls) == before

        results = await index.features_many([ok, None])
        assert results[0] is not None
        assert results[1] is None


async def test_catalog_index_retries_missing_after_a_while(tmp_path: Path) -> None:
    index, client = _index(tmp_path, lambda _request: httpx.Response(404))
    async with client:
        url = "https://assets.tcgdex.net/fehlt/1"
        assert await index.features_for(url) is None
        marker = tmp_path / "catalog" / f"{FeatureCache.key(url)}.missing"
        old = time.time() - 8 * 24 * 3600
        os.utime(marker, (old, old))
        assert await index.features_for(url) is None  # erneut versucht
        assert marker.stat().st_mtime > old


# ------------------------------------------------------------------ Binder


def test_split_grid() -> None:
    page = np.zeros((300, 400, 3), dtype=np.uint8)
    cells = split_grid(page, 4, 3)
    assert len(cells) == 12
    assert (cells[-1].row, cells[-1].column) == (2, 3)
    assert cells[0].image.shape == (92, 92, 3)


def test_binder_falls_back_to_grid() -> None:
    blank = np.full((900, 900, 3), 120, dtype=np.uint8)
    cells, method = binder_cells(blank, "auto")
    assert method == "3x3"
    assert len(cells) == 9
    cells, method = binder_cells(blank, "4x3")
    assert (method, len(cells)) == ("4x3", 12)


# ------------------------------------------------------------------ Punkte


def _card(name: str, number: str, *, language: str = "ja", set_id: str = "S12") -> Card:
    card_set = CardSet(
        external_id=set_id,
        language=language,
        name="Set",
        card_count_official=98,
        release_date=date(2022, 10, 21),
    )
    return Card(
        id=uuid.uuid4(),
        external_id=f"{set_id}-{number}",
        language=language,
        number=number,
        number_norm=number.lstrip("0"),
        name=name,
        card_set=card_set,
    )


@pytest.mark.parametrize(
    ("ocr", "card_name", "expected"),
    [
        ("ルギアV", "ルギアV", 1.0),
        ("ルギア", "ルギアV", 0.95),
        ("Team Rockets MewtuX", "Team Rockets Mewtu ex", 0.85),
        ("ブラッキ", "ブラッキーex", 0.84),
        ("Glurek", "Glurak", 0.75),
        ("Team Rockets MewtuX", "Mew", 0.0),  # kurzer Name steckt im OCR-Text – zählt nicht
        ("Pikachu", "Glurak", 0.0),
    ],
)
def test_name_similarity(ocr: str, card_name: str, expected: float) -> None:
    names = extract_text_features(lines(ocr)).names
    assert name_similarity(names, card_name) == pytest.approx(expected, abs=0.01)


def test_language_penalty() -> None:
    japanese = LanguageGuess(("ja",), "kana")
    latin = LanguageGuess(("de", "en"), "latin")
    assert language_penalty("ja", japanese, None) == 0
    assert language_penalty("zh-tw", japanese, None) == 0.25
    assert language_penalty("en", latin, None) == 0.05
    assert language_penalty("ja", LanguageGuess(), None) == 0
    assert language_penalty("ja", japanese, "zh-tw") == 0.3
    assert language_penalty("zh-tw", japanese, "zh-tw") == 0


def test_confidence_rules() -> None:
    text = extract_text_features(lines("ルギアV", "512 F 110/098 SR"))
    right = score_text(Candidate(_card("ルギアV", "110")), text)
    other_art = score_text(Candidate(_card("ルギアV", "079")), text)
    chinese = score_text(Candidate(_card("洛奇亞V", "110", language="zh-tw")), text)

    assert right.number_match and right.total_match and right.set_code_match
    assert right.confidence == 1.0
    assert "Setcode S12" in right.reasons
    assert "Sprache zh-tw statt ja" in chinese.reasons
    ranked = rank([chinese, other_art, right])
    assert ranked[0] is right
    assert is_confident(ranked)  # dieselbe Karte auf Chinesisch ist keine Konkurrenz

    # Promo „132/M-P“: Setcode steckt hinter dem Schrägstrich → sicher.
    promo_text = extract_text_features(lines("ピカチュウex", "132/M-P"))
    promo = score_text(Candidate(_card("ピカチュウex", "132", set_id="M-P")), promo_text)
    assert promo.set_code_match
    assert is_confident([promo])

    # Nur Nummer + Name ohne Setgröße/Setcode → nicht sicher.
    weak_text = extract_text_features(lines("ゼニガメ", "No.007"))
    weak = score_text(Candidate(_card("ゼニガメ", "007", set_id="SV2a")), weak_text)
    assert not weak.strong_evidence
    assert not is_confident([weak])

    # Starker Bildabgleich, aber eine andere Karte liegt fast gleichauf → nicht sicher.
    twin_a = Candidate(_card("ルギアV", "110"), catalog_inliers=200)
    twin_b = Candidate(_card("ルギアV", "111"), catalog_inliers=190)
    assert not is_confident(rank([twin_a, twin_b]))
    assert is_confident([twin_a])
    assert not is_confident([])
    assert twin_a.inliers == 200
    assert Candidate(_card("x", "1")).inliers is None


# ------------------------------------------------------------------ echte OCR


def test_rapidocr_reader_reads_photo_with_positions() -> None:
    from app.scanner.ocr import RapidOcrReader  # noqa: PLC0415

    reader = RapidOcrReader()
    assert reader.warm_up() >= 1
    result = reader.read(photo("03.jpg"))
    texts = [line.text for line in result]
    assert any("110/098" in text for text in texts)
    assert all(0 <= line.top <= 1 and 0 <= line.left <= 1 for line in result)
    assert reader.read(np.full((60, 60, 3), 255, dtype=np.uint8)) == []


def test_twins_need_the_same_artwork() -> None:
    """Verschiedene Grafiken sind keine Nachdrucke – der Vergleich hält sich dann heraus."""
    lugia, mewtu = card_crop(photo("03.jpg")), card_crop(photo("02.jpg"))
    assert lugia is not None and mewtu is not None
    assert pick_twin(lugia, [lugia, mewtu]) == TwinDecision()
    same = pick_twin(lugia, [lugia, lugia.copy()])
    assert (same.members, same.index) == ((0, 1), None)  # kein sichtbarer Unterschied
