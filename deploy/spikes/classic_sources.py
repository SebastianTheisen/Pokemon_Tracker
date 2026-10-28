"""Quellen für die japanische Classic Collection (2023: CLL, CLF, CLK – je 32 Karten).

Die offizielle Datenbank pokemon-card.com führt sie nicht (Prüfung 28.10.2026). Gesucht:

1. tcgcsv.com (TCGplayer-Katalog, Pokémon Japan = Kategorie 85): Gruppen mit „Classic“/CL*,
   Anzahl Karten, Beispiel mit Nummer und Bild.
2. Cardmarket-Katalog (schon importiert): Produkte mit CLL/CLF/CLK oder „Classic“ im Namen.

Nur lesend.

    docker compose exec -T api python - < deploy/spikes/classic_sources.py
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory

PATTERN = re.compile(r"classic|\bCL[LFK]\b", re.IGNORECASE)
out: list[str] = ["# Classic Collection: Quellen\n"]


def extended(product: dict[str, Any], name: str) -> str:
    for entry in product.get("extendedData") or []:
        if entry.get("name") == name:
            return str(entry.get("value"))
    return ""


async def tcgcsv(base: str) -> None:
    out.append("## 1) tcgcsv.com, Kategorie 85 (Pokémon Japan)\n")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        groups = (await client.get(f"{base}/85/groups")).json()["results"]
        hits = [g for g in groups if PATTERN.search(f"{g['name']} {g.get('abbreviation') or ''}")]
        out.append(f"{len(groups)} Gruppen, davon passend: {len(hits)}\n")
        for group in hits:
            products = (await client.get(f"{base}/85/{group['groupId']}/products")).json()
            items = products.get("results") or []
            cards = [p for p in items if extended(p, "Number")]
            out.append(
                f"- **{group['name']}** (ID {group['groupId']}, Kürzel "
                f"{group.get('abbreviation')}, {str(group.get('publishedOn'))[:10]}): "
                f"{len(items)} Produkte, {len(cards)} mit Nummer"
            )
            for product in cards[:3]:
                out.append(
                    f"  - {product['name']} · Nr. {extended(product, 'Number')} · "
                    f"Seltenheit {extended(product, 'Rarity')} · Bild {product.get('imageUrl')}"
                )
        out.append("")


async def cardmarket() -> None:
    out.append("## 2) Cardmarket-Katalog (Pokémon)\n")
    engine = create_engine(get_settings().database_url)
    async with create_session_factory(engine)() as session:
        result = await session.execute(
            text(
                """
                SELECT id_expansion, count(*) AS n, min(name) AS beispiel, max(name) AS bis
                FROM cm_products
                WHERE game = 'pokemon' AND (name ~* '\\mCL[LFK]\\M' OR name ILIKE '%classic%')
                GROUP BY id_expansion ORDER BY n DESC LIMIT 15
                """
            )
        )
        rows = result.all()
        out.append(f"{len(rows)} Ausgaben mit passenden Produkten\n")
        for row in rows:
            out.append(
                f"- Ausgabe {row.id_expansion}: {row.n} Produkte, "
                f"z. B. „{row.beispiel}“ … „{row.bis}“"
            )
    await engine.dispose()


async def main() -> None:
    try:
        await tcgcsv(get_settings().sealed_images_url.rstrip("/"))
    except Exception as exc:  # Spike: Fehler nur melden
        out.append(f"tcgcsv: Fehler {exc!r}\n")
    try:
        await cardmarket()
    except Exception as exc:
        out.append(f"Cardmarket: Fehler {exc!r}\n")
    print("\n".join(out))


asyncio.run(main())
