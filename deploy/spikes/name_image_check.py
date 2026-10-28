"""Warum gewinnt beim Binder-Scan die falsche Fassung einer Karte? (nur lesend, im api-Container)

1. Letzte Binder-Scans: was gelesen wurde, Treffer, sicher.
2. Alle Karten zu den Namen (Zeraora V, Galar-Lavados V): Set, Nummer, Sprache, Bild –
   liegt das Katalogbild im Merkmal-Cache (wie viele Merkmale) oder ist es als „fehlt“ gemerkt?
3. Falls ``/tmp/scan.jpg`` im Container liegt (siehe ``deploy/phase8_name_image_check.sh``):
   Binderzellen ausschneiden und jede Zelle per Bildabgleich gegen alle diese Karten
   messen (Inlier, höher = ähnlicher).

    docker compose exec -T api python - < deploy/spikes/name_image_check.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import cv2
import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.scanner.binder import binder_cells
from app.scanner.catalog_images import _features_from_bytes, download_url
from app.scanner.matching import extract_features, match_score
from app.scanner.storage import FeatureCache

NAME_PARTS = ("ゼラオラ", "フアイヤー")  # Schlüssel wie Card.name_key (kleine Kana groß)
SCAN = Path("/tmp/scan.jpg")  # noqa: S108 – vom Skript in den Container kopiert
HAS_SCAN = SCAN.exists()
out: list[str] = ["# Binder-Scan: Namen und Bildabgleich\n"]


async def rows(session: Any, sql: str, **params: Any) -> list[Any]:
    return list((await session.execute(text(sql), params)).all())


async def main() -> None:
    settings = get_settings()
    cache = FeatureCache(settings.scanner_data_dir)
    engine = create_engine(settings.database_url)
    async with create_session_factory(engine)() as session:
        out.append("## 1) Letzte Binder-Scans\n")
        for row in await rows(
            session,
            """
            SELECT l.created_at, l.duration_ms, l.detected->'numbers' AS numbers,
                   l.detected->'names' AS names, l.confident, l.confidence,
                   c.name, c.number, s.external_id AS set_
            FROM scan_log l LEFT JOIN cards c ON c.id = l.best_card_id
            LEFT JOIN card_sets s ON s.id = c.set_id
            WHERE l.mode = 'binder' ORDER BY l.created_at DESC LIMIT 4
            """,
        ):
            numbers = [n.get("raw") for n in row.numbers or []]
            out.append(
                f"- {row.created_at:%H:%M:%S} · {row.duration_ms} ms · Nummern {numbers} · "
                f"Namen {(row.names or [])[:3]} · Treffer {row.name} {row.number} ({row.set_}) · "
                f"sicher {row.confident} ({row.confidence})"
            )
        cards = await rows(
            session,
            """
            SELECT c.id, c.name, c.number, c.language, c.rarity, c.image_url,
                   s.external_id AS set_, s.name AS set_name
            FROM cards c JOIN card_sets s ON s.id = c.set_id
            WHERE s.game = 'pokemon' AND (c.name_key LIKE :a OR c.name_key LIKE :b)
              AND c.name_key LIKE '%v'
            ORDER BY c.name, s.release_date
            """,
            a=f"%{NAME_PARTS[0]}%",
            b=f"%{NAME_PARTS[1]}%",
        )
    await engine.dispose()

    out.append(f"\n## 2) Katalog: {len(cards)} Karten\n")
    features: dict[Any, Any] = {}
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.http_user_agent}, timeout=30, follow_redirects=True
    ) as client:
        for card in cards:
            url = card.image_url
            cached = cache.get(url) if url else None
            state = "kein Bild"
            if url:
                state = f"Cache {len(cached)} Merkmale" if cached is not None else "nicht im Cache"
                if cache.missing_since(url):
                    state += ", als fehlend gemerkt"
            feats = cached
            if feats is None and url and HAS_SCAN:
                try:
                    response = await client.get(download_url(url))
                    if response.status_code == 200:  # noqa: PLR2004
                        feats = _features_from_bytes(response.content)
                        state += f", frisch {len(feats)} Merkmale"
                    else:
                        state += f", frisch HTTP {response.status_code}"
                except Exception as exc:
                    state += f", frisch Fehler {type(exc).__name__}"
            if feats is not None:
                features[card.id] = feats
            out.append(
                f"- {card.name} {card.number} · {card.set_} ({card.set_name}) · {card.language}"
                f" · {card.rarity or '–'} · {state}"
            )

    if not HAS_SCAN:
        out.append("\n## 3) Bildabgleich: übersprungen (kein /tmp/scan.jpg)")
        print("\n".join(out))
        return
    image = cv2.imread(str(SCAN))
    cells, method = binder_cells(image, "auto")
    out.append(
        f"\n## 3) Bildabgleich ({method}, {len(cells)} Felder, "
        f"Foto {image.shape[1]}×{image.shape[0]})\n"
    )
    for cell in cells:
        query = extract_features(cell.image)
        scores = sorted(
            (
                (match_score(query, feats), card)
                for card in cards
                if (feats := features.get(card.id))
            ),
            key=lambda item: -item[0],
        )
        out.append(
            f"### Feld {cell.row + 1}/{cell.column + 1} "
            f"({cell.image.shape[1]}×{cell.image.shape[0]}, {len(query)} Merkmale)"
        )
        out.extend(
            f"- {score:>4} · {card.name} {card.number} ({card.set_})" for score, card in scores[:6]
        )
    print("\n".join(out))


asyncio.run(main())
