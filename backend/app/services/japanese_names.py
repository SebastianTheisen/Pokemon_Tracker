"""Englische Namen asiatischer Pokémon-Karten aus Cardmarket (Trainer, Items, Stadien).

Pokémon-Namen übersetzt die App selbst („エーフィV“ → „Psiana-V“), Trainer und Items nicht
(„ナンジャモ“). Cardmarket führt jede Karte unter englischem Namen („Iono (V.2)“) – der landet
ohne Fassungszusatz in ``cards.name_en`` und wird angezeigt, wenn es keine Übersetzung gibt.
Nur leere ``name_en`` werden gefüllt (TCGplayer-Karten haben schon einen).
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = structlog.get_logger(__name__)

FILL_SQL = r"""
UPDATE cards AS c
SET name_en = left(regexp_replace(p.name, '\s*[\(\[][^\)\]]*[\)\]]\s*$', ''), 200)
FROM card_sets AS s, cm_products AS p
WHERE s.id = c.set_id AND s.game = 'pokemon' AND c.language IN ('ja', 'ko', 'zh-tw', 'zh-cn')
  AND c.name_en IS NULL
  AND p.id_product = coalesce(c.cardmarket_product_override, c.cardmarket_product_id)
  AND p.name ~ '[A-Za-z]'
"""


async def fill_english_names(session: AsyncSession) -> int:
    """Leere englische Namen asiatischer Karten aus Cardmarket füllen (Anzahl)."""
    result = await session.execute(text(FILL_SQL))
    return int(getattr(result, "rowcount", 0) or 0)


async def refresh_japanese_names(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Für den Worker nach dem Cardmarket-Import; Fehler nur protokollieren."""
    try:
        async with session_factory() as session:
            filled = await fill_english_names(session)
            await session.commit()
    except Exception:
        log.exception("japanese_names.failed")
        return 0
    log.info("japanese_names.filled", cards=filled)
    return filled
