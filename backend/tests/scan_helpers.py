"""Hilfen für Scanner-Tests: Testfotos, steuerbare Texterkennung, Katalog, Bild-Server.

Die Fotos stammen aus ``scanner_testset/`` (echte Handyfotos des Nutzers). Als
„Katalogbilder“ dienen Kartenausschnitte *anderer* Fotos derselben Karte – so prüft der
Bildabgleich echte Wiedererkennung und nicht nur identische Pixel.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet
from app.scanner.imaging import UInt8Image, card_crop, decode_image, encode_jpeg
from app.scanner.ocr import OcrLine
from app.services.catalog_numbers import normalize_number

TESTSET = Path(__file__).resolve().parents[2] / "scanner_testset"
ASSETS = "https://assets.tcgdex.net"


def photo_bytes(name: str) -> bytes:
    return (TESTSET / name).read_bytes()


def photo(name: str) -> UInt8Image:
    return decode_image(photo_bytes(name))


def fingerprint(image: UInt8Image) -> str:
    return hashlib.sha1(np.ascontiguousarray(image).tobytes(), usedforsecurity=False).hexdigest()


def lines(*texts: str, height: float = 0.03) -> list[OcrLine]:
    """OCR-Zeilen; die erste ist die größte (wie ein Kartenname)."""
    return [
        OcrLine(text=text, height=height * (2 if index == 0 else 1), top=index / 40)
        for index, text in enumerate(texts)
    ]


@dataclass
class ScriptedReader:
    """Texterkennung als Attrappe: liefert vorgegebene Zeilen je Bild (per Fingerabdruck)."""

    by_image: dict[str, list[OcrLine]] = field(default_factory=dict)
    korean_by_image: dict[str, list[OcrLine]] = field(default_factory=dict)
    calls: list[tuple[str, bool]] = field(default_factory=list)
    fail_korean: bool = False

    def script(self, image_name: str, ocr: Sequence[OcrLine], *, korean: bool = False) -> None:
        target = self.korean_by_image if korean else self.by_image
        target[fingerprint(photo(image_name))] = list(ocr)

    def read(self, image: UInt8Image, *, korean: bool = False) -> list[OcrLine]:
        key = fingerprint(image)
        self.calls.append((key, korean))
        if korean:
            if self.fail_korean:
                raise RuntimeError("Modell-Download fehlgeschlagen")
            return list(self.korean_by_image.get(key, []))
        return list(self.by_image.get(key, []))

    @property
    def korean_calls(self) -> int:
        return sum(korean for _, korean in self.calls)


def crop_jpeg(name: str) -> bytes:
    """Kartenausschnitt eines Testfotos als JPEG (dient als Katalogbild)."""
    image = photo(name)
    crop = card_crop(image)
    return encode_jpeg(crop if crop is not None else image)


@dataclass
class FakeImages:
    """Simulierter Bild-Server (assets.tcgdex.net)."""

    images: dict[str, bytes] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)

    def add(self, image_url: str, data: bytes) -> None:
        self.images[f"{image_url}/high.webp"] = data

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if url in self.images:
            return httpx.Response(200, content=self.images[url])
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@dataclass(frozen=True)
class CatalogCard:
    external_id: str
    number: str
    name: str
    image: str | None = None  # Testfoto, dessen Ausschnitt als Katalogbild dient


@dataclass(frozen=True)
class CatalogSet:
    external_id: str
    language: str
    name: str
    official: int
    released: date
    cards: tuple[CatalogCard, ...]


def scan_catalog() -> list[CatalogSet]:
    """Kleiner Katalog nach dem Vorbild der echten Testkarten (IDs wie bei TCGdex)."""
    return [
        CatalogSet(
            "S12",
            "ja",
            "パラダイムトリガー",
            98,
            date(2022, 10, 21),
            (
                CatalogCard("S12-110", "110", "ルギアV", image="03.jpg"),
                CatalogCard("S12-079", "079", "ルギアV", image="07.jpg"),
                CatalogCard("S12-080", "080", "ルギアVSTAR"),
            ),
        ),
        # Gleiche Set-ID auf Chinesisch (traditionell) – darf JP-Fotos nicht gewinnen.
        CatalogSet(
            "S12",
            "zh-tw",
            "Paradigm Trigger",
            98,
            date(2022, 10, 21),
            (CatalogCard("S12-110", "110", "洛奇亞V"),),
        ),
        CatalogSet(
            "sv10",
            "de",
            "Ewige Rivalen",
            182,
            date(2025, 5, 30),
            (
                CatalogCard("sv10-231", "231", "Team Rockets Mewtu ex", image="02.jpg"),
                CatalogCard("sv10-213", "213", "Team Rockets Mewtu ex"),
            ),
        ),
        CatalogSet(
            "sv10",
            "en",
            "Destined Rivals",
            182,
            date(2025, 5, 30),
            (CatalogCard("sv10-231", "231", "Team Rocket's Mewtwo ex", image="02.jpg"),),
        ),
        CatalogSet(
            "SV8a",
            "ja",
            "テラスタルフェスex",
            187,
            date(2024, 12, 6),
            (
                CatalogCard("SV8a-217", "217", "ブラッキーex", image="05.jpg"),
                CatalogCard("SV8a-093", "093", "ブラッキーex", image="07.jpg"),
            ),
        ),
        CatalogSet(
            "SV2a",
            "ja",
            "ポケモンカード151",
            165,
            date(2023, 6, 16),
            (CatalogCard("SV2a-007", "007", "ゼニガメ", image="07.jpg"),),
        ),
        # Lugia 142/103 ohne Katalogbild (wie im Spike) → nur Text bzw. eigenes Referenzbild.
        CatalogSet(
            "PCG10",
            "ja",
            "Lugia-Set",
            103,
            date(2006, 1, 1),
            (CatalogCard("PCG10-142", "142", "ルギア"),),
        ),
        CatalogSet(
            "KO1",
            "ko",
            "패러다임 트리거",
            98,
            date(2022, 10, 21),
            (CatalogCard("KO1-110", "110", "루기아V"),),
        ),
    ]


def image_url(card_set: CatalogSet, card: CatalogCard) -> str:
    return f"{ASSETS}/{card_set.language}/{card_set.external_id}/{card.number}"


async def build_scan_catalog(
    session_factory: async_sessionmaker[AsyncSession], images: FakeImages
) -> dict[tuple[str, str], Card]:
    """Schreibt den Katalog und hinterlegt die Katalogbilder. Schlüssel: (ID, Sprache)."""
    cards: dict[tuple[str, str], Card] = {}
    crops: dict[str, bytes] = {}
    async with session_factory() as session:
        for spec in scan_catalog():
            card_set = CardSet(
                external_id=spec.external_id,
                language=spec.language,
                name=spec.name,
                card_count_official=spec.official,
                release_date=spec.released,
            )
            session.add(card_set)
            await session.flush()
            for card_spec in spec.cards:
                url = image_url(spec, card_spec) if card_spec.image else None
                if card_spec.image and url:
                    crops.setdefault(card_spec.image, crop_jpeg(card_spec.image))
                    images.add(url, crops[card_spec.image])
                card = Card(
                    external_id=card_spec.external_id,
                    language=spec.language,
                    set_id=card_set.id,
                    number=card_spec.number,
                    number_norm=normalize_number(card_spec.number),
                    name=card_spec.name,
                    image_url=url,
                )
                session.add(card)
                cards[(card_spec.external_id, spec.language)] = card
        await session.commit()
        for card in cards.values():
            await session.refresh(card, ["card_set"])
    return cards
