"""Warum gewinnt beim Classic-Binder noch das Grundset? (nur lesend, im api-Container)

1. Letzter Binder-Scan: was je Zelle gelesen wurde, Treffer, sicher, Dauer.
2. Katalogbilder der Classic-Karten und ihrer Doppelgänger mit gleicher Grafik (Grundset 1996,
   Promo S8a-P): im Merkmal-Cache? als „fehlt“ gemerkt? frisch ladbar? wie viele Merkmale?
3. Wie ähnlich sich Classic- und Grundset-Bild sind (Bildabgleich untereinander).

    docker compose exec -T api python - < deploy/spikes/classic_scan_check.py
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.scanner.catalog_images import _features_from_bytes, download_url
from app.scanner.matching import match_score
from app.scanner.storage import FeatureCache

NAMES = ("ヒトカゲ", "リザード", "リザードン", "フシギダネ", "フシギソウ", "フシギバナ",
         "ゼニガメ", "カメール", "カメックス")  # fmt: skip
out: list[str] = ["# Classic-Binder: Prüfung\n"]


async def rows(session: Any, sql: str, **params: Any) -> list[Any]:
    return list((await session.execute(text(sql), params)).all())


async def main() -> None:
    settings = get_settings()
    cache = FeatureCache(settings.scanner_data_dir)
    engine = create_engine(settings.database_url)
    async with create_session_factory(engine)() as session:
        out.append("## 1) Letzter Binder-Scan\n")
        for row in await rows(
            session,
            """
            SELECT l.duration_ms, l.detected->'numbers' AS numbers,
                   l.detected->'names' AS names, l.confident, c.external_id,
                   s.external_id AS set_
            FROM scan_log l LEFT JOIN cards c ON c.id = l.best_card_id
            LEFT JOIN card_sets s ON s.id = c.set_id
            WHERE l.mode = 'binder' ORDER BY l.created_at DESC LIMIT 9
            """,
        ):
            numbers = [n.get("raw") for n in row.numbers or []]
            names = (row.names or [])[:2]
            out.append(
                f"- {row.duration_ms} ms · Nummern {numbers} · Namen {names} · "
                f"Treffer {row.external_id} ({row.set_}) · sicher {row.confident}"
            )
        cards = await rows(
            session,
            """
            SELECT c.external_id, c.name, s.external_id AS set_, c.image_url
            FROM cards c JOIN card_sets s ON s.id = c.set_id
            WHERE c.language = 'ja' AND c.name = ANY(:names)
              AND (s.external_id IN ('CLL', 'CLF', 'CLK', 'S8a-P')
                   OR s.external_id LIKE 'pc-pokemon-japanese-expansion-pack%')
            ORDER BY c.name, s.external_id
            """,
            names=list(NAMES),
        )
    await engine.dispose()

    out.append("\n## 2) Katalogbilder\n")
    features: dict[str, Any] = {}
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.http_user_agent}, timeout=30, follow_redirects=True
    ) as client:
        for card in cards:
            url = card.image_url
            cached = cache.get(url) if url else None
            missing = cache.missing_since(url) if url else None
            state = (
                f"Cache {len(cached)} Merkmale"
                if cached is not None
                else (f"als fehlend gemerkt vor {int((time.time() - missing) / 60)} min"
                      if missing else "nicht im Cache")
            )  # fmt: skip
            fresh = "–"
            if url:
                try:
                    response = await client.get(download_url(url))
                    fresh = f"HTTP {response.status_code}, {len(response.content) // 1024} KB"
                    if response.status_code == 200:  # noqa: PLR2004
                        feats = _features_from_bytes(response.content)
                        features[card.external_id] = feats
                        fresh += f", {len(feats)} Merkmale"
                except Exception as exc:
                    fresh = f"Fehler {type(exc).__name__}: {exc}"
            out.append(f"- {card.name} {card.external_id} ({card.set_}): {state} · frisch {fresh}")
            out.append(f"  {url}")

    out.append("\n## 3) Classic gegen Doppelgänger (Bildabgleich, Inlier)\n")
    for card in cards:
        if card.set_ not in ("CLL", "CLF", "CLK") or card.external_id not in features:
            continue
        twins = [
            other
            for other in cards
            if other.name == card.name and other.set_ != card.set_ and other.external_id in features
        ]
        for other in twins:
            score = match_score(features[card.external_id], features[other.external_id])
            out.append(f"- {card.name}: {card.external_id} ↔ {other.external_id} = {score}")
    print("\n".join(out))


asyncio.run(main())
