"""Passen die Setkürzel von TCGplayer (tcgcsv.com) zu den Sets in Kartenkiste? Nur lesend.

docker compose exec -T api python - < deploy/spikes/tcgplayer_sets_check.py
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.tcgplayer_sets import name_key, set_aliases, set_key

EXAMPLES = (
    "Hot Air Arena", "Sky Legend", "Thunderclap Spark", "Amazing Volt", "Eevee Heroes",
    "Scarlet & Violet Promo JP", "Sun & Moon Promos (JP)", "XY Promos", "Inferno X",
    "Ultra Shiny GX", "Miracle Twins", "Clay Burst", "Paldean Fates", "Glory of Team Rocket",
)  # fmt: skip


if extra := os.environ.get("NAMES", "").strip():  # z. B. NAMES="Megalo Cannon;Hot Air Arena"
    EXAMPLES = tuple(name.strip() for name in extra.split(";") if name.strip())


async def main() -> None:
    settings = get_settings()
    aliases = await set_aliases(settings)
    print(f"TCGplayer: {len(aliases)} Setnamen mit Kürzel\n")
    engine = create_engine(settings.database_url)
    async with create_session_factory(engine)() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT external_id, code, language, name FROM card_sets "
                    "WHERE game = 'pokemon' AND language IN ('ja', 'en')"
                )
            )
        ).all()
    await engine.dispose()
    ours: dict[str, list[str]] = {}
    for row in rows:
        for code in {row.external_id, row.code or ""} - {""}:
            ours.setdefault(set_key(row.language, code), []).append(
                f"{row.external_id} ({row.language})"
            )
    codes = {code for group in aliases.values() for code in group}
    hit = sum(1 for code in codes if code in ours)
    print(f"Kürzel bei TCGplayer: {len(codes)}, davon in Kartenkiste: {hit}\n")
    for example in EXAMPLES:
        found = sorted(aliases.get(name_key(example), ()))
        mapped = [f"{code} → {', '.join(ours.get(code, ['fehlt']))}" for code in found]
        print(f"- {example}: {'; '.join(mapped) or 'Name bei TCGplayer unbekannt'}")
    missing = sorted(code for code in codes if code not in ours)[:40]
    print(f"\nKürzel ohne Set in Kartenkiste (Auszug): {', '.join(missing)}")


asyncio.run(main())
