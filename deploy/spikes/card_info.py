"""Alle Katalogkarten eines Sets mit einer Nummer: Name, englischer Name, Bild (Quelle, Sprache,
Adresse), Cardmarket-Produkt mit Name und Ausgabe – um falsche Bilder oder Zuordnungen zu
finden. Nur lesend, im api-Container.

    docker compose exec -T -e SET=SV-P -e NUMBER=038 api python - < deploy/spikes/card_info.py
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory

SQL = """
SELECT s.external_id AS set_, s.language, s.name AS set_name, c.number, c.name, c.name_en,
       c.external_id, c.image_source, c.image_language, c.image_url,
       coalesce(c.cardmarket_product_override, c.cardmarket_product_id) AS cm,
       p.name AS cm_name, p.id_expansion, c.created_at
FROM cards c
JOIN card_sets s ON s.id = c.set_id
LEFT JOIN cm_products p
       ON p.id_product = coalesce(c.cardmarket_product_override, c.cardmarket_product_id)
WHERE replace(lower(s.external_id), '-', '') = replace(lower(:set_), '-', '')
  AND ltrim(c.number_norm, '0') = ltrim(:number, '0')
ORDER BY s.language, c.number
"""


async def main() -> None:
    engine = create_engine(get_settings().database_url)
    async with create_session_factory(engine)() as session:
        rows = (
            await session.execute(
                text(SQL), {"set_": os.environ["SET"], "number": os.environ["NUMBER"]}
            )
        ).all()
    await engine.dispose()
    print(f"# {os.environ['SET']} {os.environ['NUMBER']}: {len(rows)} Karten\n")
    for row in rows:
        print(
            f"- {row.set_} ({row.language}, {row.set_name}) {row.number} {row.name} / "
            f"{row.name_en or '–'} · ID {row.external_id} · angelegt {row.created_at:%Y-%m-%d}\n"
            f"  Bild: {row.image_source or '–'} ({row.image_language or '–'}) {row.image_url}\n"
            f"  CM: {row.cm or '–'} „{row.cm_name or '–'}“ Ausgabe {row.id_expansion or '–'}"
        )


asyncio.run(main())
