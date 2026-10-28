"""Scanner über die API: Erkennung, Slab, Bildabgleich, Bestätigen, Referenzbilder, Grenzen.

Die Texterkennung ist hier eine Attrappe mit OCR-Zeilen, wie sie RapidOCR im Phase-0-Spike
für die echten Testfotos geliefert hat. Bildabgleich, Bildladen und Datenbank sind echt.
Ein eigener Test am Ende nutzt die echte OCR.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.models import Card, CardReferenceImage, CardSet, Role, ScanLog
from app.scanner.imaging import decode_image, encode_jpeg
from app.scanner.storage import ReferenceStore
from app.services.admin import AdminService
from app.services.scan import prune_reference_files, purge_scan_logs
from app.worker import scanner_housekeeping
from tests.conftest import Account, RegisterUser, _login
from tests.pricing_helpers import FakeProvider
from tests.scan_helpers import (
    FakeImages,
    ScriptedReader,
    build_scan_catalog,
    crop_jpeg,
    fingerprint,
    lines,
    photo,
    photo_bytes,
)

API = "/api/v1"
CardMap = dict[tuple[str, str], Card]


# ------------------------------------------------------------------ Fixtures


@pytest.fixture
def settings(migrated_database: str, tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        log_level="WARNING",
        database_url=migrated_database,
        jwt_secret="test-secret-mit-ausreichender-laenge-1234567890",
        login_rate_limit=3,
        scanner_data_dir=tmp_path / "scanner",
    )


@pytest.fixture
def reader() -> ScriptedReader:
    return ScriptedReader()


@pytest.fixture
def images() -> FakeImages:
    return FakeImages()


@pytest.fixture
async def client(
    settings: Settings,
    engine: AsyncEngine,
    price_provider: FakeProvider,
    reader: ScriptedReader,
    images: FakeImages,
) -> AsyncIterator[AsyncClient]:
    """Wie in conftest, aber mit Scanner-Attrappen (überschreibt die gemeinsame Fixture)."""
    app = create_app(
        settings,
        engine=engine,
        price_providers=[price_provider],
        text_reader=reader,
        image_transport=images.transport(),
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client


@pytest.fixture
async def catalog(session_factory: async_sessionmaker[AsyncSession], images: FakeImages) -> CardMap:
    return await build_scan_catalog(session_factory, images)


async def _scan(
    client: AsyncClient,
    user: Account,
    data: bytes,
    *,
    params: dict[str, str] | None = None,
    expected: int = 200,
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/scan",
        files={"file": ("foto.jpg", data, "image/jpeg")},
        params=params or {},
        headers=user.headers,
    )
    assert response.status_code == expected, response.text
    body: dict[str, Any] = response.json()
    return body


def _best(result: dict[str, Any]) -> tuple[str, str]:
    card = result["best"]["card"]
    return card["external_id"], card["language"]


# ------------------------------------------------------------------ Erkennung


async def test_number_total_and_name_identify_german_card(
    client: AsyncClient, admin: Account, reader: ScriptedReader, catalog: CardMap
) -> None:
    # OCR-Zeilen von Testfoto 02 (Spike): „ex“-Logo als „X“ gelesen, Setcode „DR“ angeklebt.
    reader.script(
        "02.jpg",
        lines(
            "Team Rockets MewtuX",
            "BASIS",
            "280",
            "Fähigkeit",
            "Dieses Pokémon kann nicht angreifen, es sei denn, du hast",
            "auf deinen Ablagestapellegen. Diese Attacke fügt für jede",
            "DR231/182 會会",
        ),
    )

    result = await _scan(client, admin, photo_bytes("02.jpg"))

    assert result["confident"] is True
    assert result["hint"] == "Erkannt als Team Rockets Mewtu ex"
    assert _best(result) == ("sv10-231", "de")
    reasons = " | ".join(result["best"]["reasons"])
    assert "Nummer DR231/182 passt (Set mit 182 Karten)" in reasons
    assert "Name ähnlich „Team Rockets Mewtu ex“" in reasons
    # Dieselbe Karte auf Englisch ist Alternative, nicht Konkurrenz.
    alternatives = [
        (a["card"]["external_id"], a["card"]["language"]) for a in result["alternatives"]
    ]
    assert ("sv10-231", "en") in alternatives
    assert len(result["alternatives"]) <= 4
    assert result["detected"]["languages"] == ["de", "en"]
    assert result["grading"] is None


async def test_slab_is_read_and_card_found_by_image(
    client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    images: FakeImages,
    catalog: CardMap,
) -> None:
    # Testfoto 04: Daumen verdeckt die Nummer, das PSA-Label ist lesbar.
    reader.script(
        "04.jpg",
        lines(
            "#110",
            "2022 POKEMON JPN.SWSH",
            "GEM MT",
            "FA/LUGIA V",
            "10",
            "PARADIGMTRIGGER",
            "73270136",
            "たね",
            "ルギアV",
            "かぜよみ",
            "PSA.",
        ),
    )

    result = await _scan(client, admin, photo_bytes("04.jpg"))

    assert _best(result) == ("S12-110", "ja")
    assert result["confident"] is True
    assert result["grading"] == {"company": "PSA", "grade": "10", "cert": "73270136"}
    assert (result["psa"], result["psa_warning"]) == (None, None)  # ohne PSA-Token
    assert result["best"]["image_inliers"] >= 50  # Katalogbild = Ausschnitt von Foto 03
    assert result["detected"]["slab"]["name"] == "LUGIA V"
    # Die andere Lugia V (S12-079) verliert trotz gleichen Namens.
    assert all(
        a["card"]["external_id"] != "S12-110" or a["card"]["language"] != "ja"
        for a in result["alternatives"]
    )
    assert any(url.endswith("/ja/S12/110/high.webp") for url in images.requests)


async def test_catalog_images_are_cached(
    client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    images: FakeImages,
    catalog: CardMap,
    settings: Settings,
) -> None:
    reader.script("04.jpg", lines("ルギアV", "#110"))
    await _scan(client, admin, photo_bytes("04.jpg"))
    downloads = len(images.requests)
    await _scan(client, admin, photo_bytes("04.jpg"))

    assert downloads > 0
    assert len(images.requests) == downloads  # zweiter Scan ohne Download
    assert list((settings.scanner_data_dir / "catalog").glob("*.npz"))


async def test_image_rescues_unreadable_number(
    client: AsyncClient, admin: Account, reader: ScriptedReader, catalog: CardMap
) -> None:
    # Testfoto 05: Mini-Screenshot, Nummer falsch gelesen („212/38“), Name ohne „ex“.
    reader.script("05.jpg", lines("ブラッキ-", "1退化", "ムーンEラーシュ", "212/38"))

    result = await _scan(client, admin, photo_bytes("05.jpg"))

    assert _best(result) == ("SV8a-217", "ja")
    assert result["best"]["image_inliers"] >= 50
    assert result["confident"] is True


async def test_unsure_result_offers_search(
    client: AsyncClient, admin: Account, reader: ScriptedReader, catalog: CardMap
) -> None:
    # Testfoto 01: alte Karte „No.007“ – nicht im Katalog; SV2a-007 hat nur Nummer + Name.
    reader.script("01.jpg", lines("ゼニガメ", "LV.15", "HP50", "No.007", "GEM MT", "10", "FSA"))

    result = await _scan(client, admin, photo_bytes("01.jpg"))

    assert _best(result) == ("SV2a-007", "ja")
    assert result["confident"] is False
    assert result["hint"] == "Falsche Karte? Selbst suchen"
    assert result["grading"] == {"company": "PSA", "grade": "10", "cert": None}


async def test_text_alone_is_enough_without_catalog_image(
    client: AsyncClient, admin: Account, reader: ScriptedReader, catalog: CardMap
) -> None:
    # Testfoto 06: Lugia 142/103, Katalogkarte ohne Bild.
    reader.script("06.jpg", lines("ルギア", "HP80", "たねポケモン", "142/103"))

    result = await _scan(client, admin, photo_bytes("06.jpg"))

    assert _best(result) == ("PCG10-142", "ja")
    assert result["confident"] is True
    assert result["best"]["image_inliers"] is None


async def test_nothing_readable_and_no_references(
    client: AsyncClient, admin: Account, catalog: CardMap
) -> None:
    result = await _scan(client, admin, photo_bytes("07.jpg"))

    assert result["best"] is None
    assert result["confident"] is False
    assert result["hint"] == "Keine Karte erkannt – bitte selbst suchen"
    assert result["detected"]["rescue"] is True


async def test_language_hint_prefers_chosen_language(
    client: AsyncClient, admin: Account, reader: ScriptedReader, catalog: CardMap
) -> None:
    reader.script("03.jpg", lines("ルギアV", "512 F 110/098 SR"))

    japanese = await _scan(client, admin, photo_bytes("03.jpg"))
    chinese = await _scan(client, admin, photo_bytes("03.jpg"), params={"language": "zh-tw"})

    assert _best(japanese) == ("S12-110", "ja")
    assert "Setcode S12" in japanese["best"]["reasons"]  # „512“ gelesen
    assert _best(chinese) == ("S12-110", "zh-tw")
    assert {a["card"]["language"] for a in chinese["alternatives"]} <= {"zh-tw"}


async def test_korean_model_runs_when_first_pass_is_weak(
    client: AsyncClient, admin: Account, reader: ScriptedReader, catalog: CardMap
) -> None:
    # Nur eine (verwechselte) Nummer: passt zu S12-110 (ja/zh-tw) und KO1-110 – unsicher.
    reader.script("06.jpg", lines("1I0/O98"))
    reader.script("06.jpg", lines("루기아V", "110/098"), korean=True)

    result = await _scan(client, admin, photo_bytes("06.jpg"))

    assert reader.korean_calls == 1
    assert _best(result) == ("KO1-110", "ko")
    assert result["detected"]["languages"] == ["ko"]


async def test_korean_model_failure_does_not_break_scan(
    client: AsyncClient, admin: Account, reader: ScriptedReader, catalog: CardMap
) -> None:
    reader.fail_korean = True
    result = await _scan(client, admin, photo_bytes("06.jpg"), params={"language": "ko"})
    assert result["best"] is None


async def test_scan_log_is_written_without_image(
    client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    catalog: CardMap,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    reader.script("06.jpg", lines("ルギア", "142/103"))
    result = await _scan(client, admin, photo_bytes("06.jpg"))

    async with session_factory() as session:
        entry = await session.get(ScanLog, uuid.UUID(result["scan_id"]))
        assert entry is not None
        assert entry.user_id == admin.user_id
        assert entry.best_card_id == catalog[("PCG10-142", "ja")].id
        assert entry.detected["numbers"] == [{"number": "142", "total": 103, "raw": "142/103"}]
        assert entry.confident is True

        # Aufbewahrung: alte Einträge löscht der Worker.
        await session.execute(
            update(ScanLog).values(created_at=datetime.now(UTC) - timedelta(days=100))
        )
        assert await purge_scan_logs(session, retention_days=90) == 1
        await session.commit()


# ------------------------------------------------------------------ Bestätigen + Referenzen


async def _confirm(
    client: AsyncClient, user: Account, scan_id: str, card_id: uuid.UUID, **extra: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/scan/{scan_id}/confirm",
        json={"card_id": str(card_id), **extra},
        headers=user.headers,
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_confirmed_scan_becomes_own_reference(
    client: AsyncClient,
    admin: Account,
    register_user: RegisterUser,
    catalog: CardMap,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    lugia = catalog[("PCG10-142", "ja")]
    first = await _scan(client, admin, photo_bytes("06.jpg"))
    assert first["best"] is None  # kein Text, kein Katalogbild

    confirmed = await _confirm(client, admin, first["scan_id"], lugia.id)
    assert confirmed["reference_saved"] is True
    assert confirmed["card"]["external_id"] == "PCG10-142"

    # Gleiches Motiv erneut: jetzt über das eigene Referenzbild erkannt …
    again = await _scan(client, admin, photo_bytes("06.jpg"))
    assert _best(again) == ("PCG10-142", "ja")
    assert again["confident"] is True
    assert any("Eigenes Referenzbild" in reason for reason in again["best"]["reasons"])

    # … aber nur für den Nutzer, dem das Referenzbild gehört.
    friend = await register_user("freund@example.com")
    other = await _scan(client, friend, photo_bytes("06.jpg"))
    assert other["best"] is None

    async with session_factory() as session:
        entry = await session.get(ScanLog, uuid.UUID(first["scan_id"]))
        assert entry is not None
        assert entry.confirmed_card_id == lugia.id


async def test_reference_management(
    client: AsyncClient,
    admin: Account,
    register_user: RegisterUser,
    catalog: CardMap,
    settings: Settings,
) -> None:
    lugia = catalog[("PCG10-142", "ja")]
    scan = await _scan(client, admin, photo_bytes("06.jpg"))
    reference_id = (await _confirm(client, admin, scan["scan_id"], lugia.id))["reference_id"]

    listed = await client.get(f"{API}/scan/references", headers=admin.headers)
    assert [r["id"] for r in listed.json()] == [reference_id]
    assert listed.json()[0]["card"]["external_id"] == "PCG10-142"
    filtered = await client.get(
        f"{API}/scan/references", params={"card_id": str(uuid.uuid4())}, headers=admin.headers
    )
    assert filtered.json() == []

    image = await client.get(f"{API}/scan/references/{reference_id}/image", headers=admin.headers)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(image.content)).size) <= 800

    friend = await register_user("freund@example.com")
    for method, path in (
        ("GET", f"{API}/scan/references/{reference_id}/image"),
        ("DELETE", f"{API}/scan/references/{reference_id}"),
    ):
        response = await client.request(method, path, headers=friend.headers)
        assert response.status_code == 404

    deleted = await client.delete(f"{API}/scan/references/{reference_id}", headers=admin.headers)
    assert deleted.status_code == 204
    assert (await client.get(f"{API}/scan/references", headers=admin.headers)).json() == []
    assert not list((settings.scanner_data_dir / "references").glob("*/*"))
    missing = await client.get(f"{API}/scan/references/{reference_id}/image", headers=admin.headers)
    assert missing.status_code == 404


async def test_references_per_card_are_limited(
    client: AsyncClient,
    admin: Account,
    catalog: CardMap,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings.scanner_references_per_card = 2
    lugia = catalog[("PCG10-142", "ja")]
    for _ in range(3):
        scan = await _scan(client, admin, photo_bytes("06.jpg"))
        await _confirm(client, admin, scan["scan_id"], lugia.id)

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(CardReferenceImage))
    assert count == 2
    assert len(list((settings.scanner_data_dir / "references").glob("*/*.jpg"))) == 2


async def test_confirm_errors(
    client: AsyncClient, admin: Account, register_user: RegisterUser, catalog: CardMap
) -> None:
    lugia = catalog[("PCG10-142", "ja")]
    scan = await _scan(client, admin, photo_bytes("06.jpg"))
    friend = await register_user("freund@example.com")

    for user, scan_id, card_id in (
        (admin, str(uuid.uuid4()), lugia.id),  # unbekannter Scan
        (friend, scan["scan_id"], lugia.id),  # fremder Scan
        (admin, scan["scan_id"], uuid.uuid4()),  # unbekannte Karte
    ):
        response = await client.post(
            f"{API}/scan/{scan_id}/confirm", json={"card_id": str(card_id)}, headers=user.headers
        )
        assert response.status_code == 404, response.text

    without = await _confirm(client, admin, scan["scan_id"], lugia.id, save_reference=False)
    assert without["reference_saved"] is False
    assert without["note"] is None
    # Nochmal bestätigen: Ausschnitt wurde schon nicht verbraucht → jetzt speichern.
    saved = await _confirm(client, admin, scan["scan_id"], lugia.id)
    assert saved["reference_saved"] is True
    # Danach ist der Ausschnitt verbraucht.
    gone = await _confirm(client, admin, scan["scan_id"], lugia.id)
    assert gone["reference_saved"] is False
    assert gone["note"] == "Referenzbild nicht mehr verfügbar (Scan zu alt)."


async def test_orphaned_reference_files_are_pruned(
    client: AsyncClient,
    admin: Account,
    catalog: CardMap,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scan = await _scan(client, admin, photo_bytes("06.jpg"))
    await _confirm(client, admin, scan["scan_id"], catalog[("PCG10-142", "ja")].id)
    store = ReferenceStore(settings.scanner_data_dir)

    async with session_factory() as session:
        assert await prune_reference_files(session, store) == 0
        await session.execute(delete(CardReferenceImage))
        await session.commit()
        assert await prune_reference_files(session, store) == 2  # JPEG + Merkmale


# ------------------------------------------------------------------ Stapel und Binder


async def test_batch_scan(
    client: AsyncClient, admin: Account, reader: ScriptedReader, catalog: CardMap
) -> None:
    reader.script("06.jpg", lines("ルギア", "142/103"))
    response = await client.post(
        f"{API}/scan/batch",
        files=[
            ("files", ("a.jpg", photo_bytes("06.jpg"), "image/jpeg")),
            ("files", ("kaputt.jpg", b"kein bild", "image/jpeg")),
            ("files", ("b.jpg", photo_bytes("07.jpg"), "image/jpeg")),
        ],
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text
    items = response.json()

    assert [item["filename"] for item in items] == ["a.jpg", "kaputt.jpg", "b.jpg"]
    assert items[0]["result"]["best"]["card"]["external_id"] == "PCG10-142"
    assert items[1]["result"] is None
    assert items[1]["error"] == "Die Datei ist kein lesbares Bild."
    assert items[2]["result"]["best"] is None


async def test_batch_limits(client: AsyncClient, admin: Account, settings: Settings) -> None:
    settings.scan_batch_max = 2
    files = [("files", (f"{i}.jpg", b"x", "image/jpeg")) for i in range(3)]
    response = await client.post(f"{API}/scan/batch", files=files, headers=admin.headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "batch_too_large"


def _binder_page(names: list[str]) -> bytes:
    """2×2-Binderseite aus Kartenausschnitten der Testfotos (mit dunklen Stegen)."""
    cells = [
        np.asarray(Image.open(io.BytesIO(crop_jpeg(name))).convert("RGB").resize((420, 588)))
        for name in names
    ]
    page = np.full((2 * 588 + 60, 2 * 420 + 60, 3), 25, dtype=np.uint8)
    for index, cell in enumerate(cells):
        row, column = divmod(index, 2)
        y, x = 20 + row * (588 + 20), 20 + column * (420 + 20)
        page[y : y + 588, x : x + 420] = cell
    return encode_jpeg(page[:, :, ::-1].copy(), quality=92)


async def test_binder_scan_grid(client: AsyncClient, admin: Account, catalog: CardMap) -> None:
    page = _binder_page(["03.jpg", "02.jpg", "05.jpg", "06.jpg"])
    response = await client.post(
        f"{API}/scan/binder",
        files={"file": ("seite.jpg", page, "image/jpeg")},
        params={"layout": "2x2"},
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["beta"] is True
    assert body["method"] == "2x2"
    assert [(c["row"], c["column"]) for c in body["cells"]] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    # Ohne OCR-Text bleibt nur der Rettungsweg über eigene Referenzbilder → nichts erkannt,
    # aber jede Zelle hat einen eigenen bestätigbaren Scan.
    scan_ids = {cell["result"]["scan_id"] for cell in body["cells"]}
    assert len(scan_ids) == 4


async def test_binder_cells_use_text_and_images(
    client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    catalog: CardMap,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Jede Zelle liest „ルギアV“ → Kandidaten S12-110/S12-079, Bild entscheidet.
    monkeypatch.setattr(reader, "read", lambda image, korean=False: lines("ルギアV"))
    page = _binder_page(["03.jpg", "07.jpg", "03.jpg", "07.jpg"])
    response = await client.post(
        f"{API}/scan/binder",
        files={"file": ("seite.jpg", page, "image/jpeg")},
        params={"layout": "auto"},
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["method"] == "konturen"
    winners = [c["result"]["best"]["card"]["external_id"] for c in body["cells"]]
    assert winners == ["S12-110", "S12-079", "S12-110", "S12-079"]


# ------------------------------------------------------------------ Grenzen und Schutz


async def test_rate_limit(
    client: AsyncClient, admin: Account, settings: Settings, catalog: CardMap
) -> None:
    settings.scan_rate_limit_per_hour = 2
    await _scan(client, admin, photo_bytes("07.jpg"))
    await _scan(client, admin, photo_bytes("07.jpg"))

    response = await client.post(
        f"{API}/scan",
        files={"file": ("foto.jpg", photo_bytes("07.jpg"), "image/jpeg")},
        headers=admin.headers,
    )
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 3600

    batch = await client.post(
        f"{API}/scan/batch",
        files=[("files", ("a.jpg", photo_bytes("07.jpg"), "image/jpeg"))],
        headers=admin.headers,
    )
    assert batch.status_code == 429


async def test_upload_validation(client: AsyncClient, admin: Account, settings: Settings) -> None:
    invalid = await _scan(client, admin, b"GIF89a....", expected=400)
    assert invalid["error"]["code"] == "invalid_image"

    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    unsupported = await _scan(client, admin, gif.getvalue(), expected=400)
    assert "GIF wird nicht unterstützt" in unsupported["error"]["message"]

    settings.scan_max_upload_mb = 1
    too_large = await _scan(client, admin, b"\xff" * (1024 * 1024 + 1), expected=400)
    assert too_large["error"]["code"] == "file_too_large"

    binder = await client.post(
        f"{API}/scan/binder",
        files={"file": ("x.jpg", b"\xff" * (1024 * 1024 + 1), "image/jpeg")},
        headers=admin.headers,
    )
    assert binder.status_code == 400


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/scan"),
        ("POST", "/scan/batch"),
        ("POST", "/scan/binder"),
        ("POST", f"/scan/{uuid.uuid4()}/confirm"),
        ("GET", "/scan/references"),
        ("GET", f"/scan/references/{uuid.uuid4()}/image"),
        ("DELETE", f"/scan/references/{uuid.uuid4()}"),
    ],
)
async def test_scan_endpoints_require_login(client: AsyncClient, method: str, path: str) -> None:
    response = await client.request(method, f"{API}{path}")
    assert response.status_code == 401


# ------------------------------------------------------------------ echte OCR


async def test_real_ocr_identifies_lugia(
    settings: Settings,
    engine: AsyncEngine,
    images: FakeImages,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    """Ende-zu-Ende mit RapidOCR auf Testfoto 04 (Slab, Nummer verdeckt)."""
    await build_scan_catalog(session_factory, images)
    app = create_app(
        settings,
        engine=engine,
        price_providers=[price_provider],
        image_transport=images.transport(),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        async with session_factory() as session:
            await AdminService(session, settings).create_user(
                email="ocr@example.com",
                password="richtig-gutes-passwort",
                display_name="OCR",
                role=Role.ADMIN,
            )
            await session.commit()
        tokens = await _login(http, "ocr@example.com", "richtig-gutes-passwort")
        response = await http.post(
            f"{API}/scan",
            files={"file": ("04.jpg", photo_bytes("04.jpg"), "image/jpeg")},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert _best(result) == ("S12-110", "ja")
    assert result["confident"] is True
    assert result["grading"] == {"company": "PSA", "grade": "10", "cert": "73270136"}
    assert (result["psa"], result["psa_warning"]) == (None, None)  # ohne PSA-Token
    assert photo("04.jpg").shape[0] == 1280


async def test_worker_housekeeping(
    client: AsyncClient,
    admin: Account,
    catalog: CardMap,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scan = await _scan(client, admin, photo_bytes("06.jpg"))
    await _confirm(client, admin, scan["scan_id"], catalog[("PCG10-142", "ja")].id)
    orphan = settings.scanner_data_dir / "references" / str(uuid.uuid4()) / f"{uuid.uuid4()}.jpg"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"x")
    async with session_factory() as session:
        await session.execute(
            update(ScanLog).values(created_at=datetime.now(UTC) - timedelta(days=91))
        )
        await session.commit()

    summary = await scanner_housekeeping(session_factory, settings)

    assert (summary.scan_logs_deleted, summary.reference_files_deleted) == (1, 1)
    assert not orphan.exists()
    listed = await client.get(f"{API}/scan/references", headers=admin.headers)
    assert len(listed.json()) == 1  # Referenz bleibt, nur der Protokolleintrag ist weg


async def test_oversized_uploads_are_cut_off_early(
    client: AsyncClient, admin: Account, settings: Settings
) -> None:
    settings.scan_max_upload_mb = 1
    big = b"\xff" * (3 * 1024 * 1024)

    declared = await client.post(
        f"{API}/scan", files={"file": ("x.jpg", big, "image/jpeg")}, headers=admin.headers
    )
    assert declared.status_code == 413
    assert declared.json()["error"]["code"] == "file_too_large"

    async def chunks() -> AsyncIterator[bytes]:  # ohne Content-Length (chunked)
        yield (
            b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\n'
            b"Content-Type: image/jpeg\r\n\r\n"
        )
        for _ in range(3):
            yield b"\xff" * (1024 * 1024)

    streamed = await client.post(
        f"{API}/scan",
        content=chunks(),
        headers={**admin.headers, "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert streamed.status_code == 413

    # Andere Pfade sind nicht betroffen; Stapel dürfen größer sein.
    settings.scan_batch_max = 4
    batch = await client.post(
        f"{API}/scan/batch",
        files=[("files", ("a.jpg", b"\xff" * (900 * 1024), "image/jpeg"))] * 3,
        headers=admin.headers,
    )
    assert batch.status_code == 200
    assert [item["error"] for item in batch.json()] == ["Die Datei ist kein lesbares Bild."] * 3


# ------------------------------------------------------------- PSA-Zertifikat

LUGIA_LINES = (
    "#110",
    "2022 POKEMON JPN.SWSH",
    "MINT",
    "FA/LUGIA V",
    "PARADIGMTRIGGER",
    "73270136",
    "ルギアV",
    "PSA.",
)


def psa_handler(card_number: str = "110") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "bearer psa-test-token"
        if request.url.path.endswith("/cert/GetByCertNumber/73270136"):
            return httpx.Response(
                200,
                json={
                    "PSACert": {
                        "CertNumber": "73270136",
                        "Year": "2022",
                        "Brand": "POKEMON JAPANESE SWORD & SHIELD PARADIGM TRIGGER",
                        "CardNumber": card_number,
                        "Subject": "FA/LUGIA V",
                        "Variety": "",
                        "CardGrade": "GEM MT 10",
                        "GradeDescription": "GEM MT 10",
                        "TotalPopulation": 1234,
                        "PopulationHigher": 0,
                    }
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def psa_number() -> str:
    return "110"


@pytest.fixture
async def psa_client(
    settings: Settings,
    engine: AsyncEngine,
    price_provider: FakeProvider,
    reader: ScriptedReader,
    images: FakeImages,
    psa_number: str,
) -> AsyncIterator[AsyncClient]:
    """Scanner wie oben, zusätzlich mit PSA-Token und simulierter PSA-API."""
    configured = settings.model_copy(update={"psa_token": SecretStr("psa-test-token")})
    app = create_app(
        configured,
        engine=engine,
        price_providers=[price_provider],
        text_reader=reader,
        image_transport=images.transport(),
        psa_transport=psa_handler(psa_number),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client,
    ):
        yield http_client


async def test_psa_confirms_slab_and_grade(
    psa_client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    catalog: CardMap,
) -> None:
    # Label ohne Notenzahl („MINT“ → 9 laut Tabelle) – PSA sagt 10 und gilt.
    reader.script("04.jpg", lines(*LUGIA_LINES))

    result = await _scan(psa_client, admin, photo_bytes("04.jpg"))

    assert _best(result) == ("S12-110", "ja")
    assert result["grading"] == {"company": "PSA", "grade": "10", "cert": "73270136"}
    assert result["psa"]["subject"] == "FA/LUGIA V"
    assert (result["psa"]["population"], result["psa"]["population_higher"]) == (1234, 0)
    assert result["psa_warning"] is None

    lookup = await psa_client.get(f"{API}/scan/psa/73270136", headers=admin.headers)
    unknown = await psa_client.get(f"{API}/scan/psa/99999999", headers=admin.headers)
    assert lookup.json()["grade_description"] == "GEM MT 10"
    assert unknown.status_code == 404


@pytest.mark.parametrize("psa_number", ["079"])
async def test_psa_warns_when_number_differs(
    psa_client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    catalog: CardMap,
) -> None:
    reader.script("04.jpg", lines(*LUGIA_LINES))

    result = await _scan(psa_client, admin, photo_bytes("04.jpg"))

    assert result["psa_warning"] == (
        "Laut PSA ist es Nr. 079 (FA/LUGIA V) – bitte die Karte prüfen."
    )


def _stamped(name: str, stamp_from: str) -> bytes:
    """Kartenausschnitt mit eingesetztem „Jubiläums-Stempel“ (Ausschnitt eines anderen Fotos)."""
    card = decode_image(crop_jpeg(name))
    other = decode_image(crop_jpeg(stamp_from))
    height, width = card.shape[:2]
    size = int(width * 0.12)
    stamp = cv2.resize(other[: other.shape[0] // 3, : other.shape[1] // 3], (size, size))
    top, left = int(height * 0.42), int(width * 0.75)
    card[top : top + size, left : left + size] = stamp
    return encode_jpeg(card)


async def test_reprint_with_same_number_is_told_apart_by_stamp(
    client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    images: FakeImages,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    original, reprint = crop_jpeg("02.jpg"), _stamped("02.jpg", "05.jpg")
    async with session_factory() as session:
        for external_id, official, released, image in (
            ("dp6", 146, date(2007, 11, 1), original),
            ("me55c", 30, date(2026, 9, 16), reprint),
        ):
            card_set = CardSet(
                external_id=external_id,
                language="de",
                name=external_id,
                card_count_official=official,
                release_date=released,
            )
            session.add(card_set)
            await session.flush()
            url = f"https://assets.tcgdex.net/de/{external_id}/43"
            images.add(url, image)
            session.add(
                Card(
                    external_id=f"{external_id}-43",
                    language="de",
                    set_id=card_set.id,
                    number="43",
                    number_norm="43",
                    name="Selfe",
                    image_url=url,
                )
            )
        await session.commit()
    ocr = lines("Selfe", "BASIS", "43/146")  # Nachdrucke tragen die Nummer des Originals
    for data in (original, reprint):
        reader.by_image[fingerprint(decode_image(data))] = ocr

    stamped = await _scan(client, admin, reprint)
    plain = await _scan(client, admin, original)

    assert _best(stamped) == ("me55c-43", "de")
    assert "Druck per Bildvergleich bestimmt" in " | ".join(stamped["best"]["reasons"])
    assert stamped["confident"] is True
    assert _best(plain) == ("dp6-43", "de")


# ------------------------------------------------------------------ One Piece


async def _onepiece_cards(
    session_factory: async_sessionmaker[AsyncSession], *, parallel: bool
) -> None:
    """Zoro OP01-001 (EN) – auf Wunsch zusätzlich die Parallel-Fassung (gleiche Nummer)."""
    async with session_factory() as session:
        card_set = CardSet(
            external_id="op-OP01",
            language="en",
            game="onepiece",
            name="Romance Dawn",
            card_count_official=121,
            release_date=date(2022, 12, 2),
        )
        session.add(card_set)
        await session.flush()
        for suffix in ("", "_p1") if parallel else ("",):
            session.add(
                Card(
                    external_id=f"op-OP01-001{suffix}",
                    language="en",
                    set_id=card_set.id,
                    number="OP01-001",
                    number_norm="OP1001",
                    name="Roronoa Zoro" + (" (Parallel)" if suffix else ""),
                )
            )
        await session.commit()


async def test_one_piece_card_found_by_its_printed_number(
    client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    catalog: CardMap,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _onepiece_cards(session_factory, parallel=False)
    reader.script(
        "06.jpg", lines("Roronoa Zoro", "LEADER", "Supernovas/Straw Hat Crew", "0P01-001")
    )

    result = await _scan(client, admin, photo_bytes("06.jpg"))

    assert _best(result) == ("op-OP01-001", "en")
    assert result["confident"] is True
    assert "Kartennummer OP01-001 passt" in result["best"]["reasons"]


async def test_one_piece_parallel_needs_the_image(
    client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    catalog: CardMap,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Normale und Parallel-Fassung haben Nummer und Namen gemeinsam – ohne Bildabgleich
    darf der Scanner nicht raten, bietet aber beide an."""
    await _onepiece_cards(session_factory, parallel=True)
    reader.script("06.jpg", lines("Roronoa Zoro", "OP01-001"))

    result = await _scan(client, admin, photo_bytes("06.jpg"))

    offered = {result["best"]["card"]["external_id"]} | {
        alternative["card"]["external_id"] for alternative in result["alternatives"]
    }
    assert {"op-OP01-001", "op-OP01-001_p1"} <= offered
    assert result["confident"] is False


async def test_pokemon_scan_ignores_one_piece_numbers(
    client: AsyncClient,
    admin: Account,
    reader: ScriptedReader,
    catalog: CardMap,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _onepiece_cards(session_factory, parallel=True)
    reader.script("06.jpg", lines("ルギア", "HP80", "たねポケモン", "142/103"))

    result = await _scan(client, admin, photo_bytes("06.jpg"))

    assert _best(result) == ("PCG10-142", "ja")
    assert result["confident"] is True
