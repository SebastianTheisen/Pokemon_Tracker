"""Sammlungskarten ohne Wert: Set, Nummer, Namen, Cardmarket-Produkt, Slab und was jede
Preisquelle zuletzt gemeldet hat. Nur lesend, im api-Container.

    docker compose exec -T api python - < deploy/spikes/missing_values.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory

SQL = """
SELECT f.name AS folder, s.external_id AS set_, s.language, s.card_count_official AS size,
       c.number, c.name, c.name_en, coalesce(c.cardmarket_product_override,
       c.cardmarket_product_id) AS cm, i.grading_company AS company, i.grade,
       (SELECT string_agg(pc.source || '=' || CASE WHEN pc.ok THEN 'ok' ELSE 'fehler' END
               || coalesce(' (' || left(pc.message, 60) || ')', ''), '; ')
          FROM price_checks pc WHERE pc.card_id = c.id) AS checks,
       (SELECT count(*) FROM price_points pp WHERE pp.card_id = c.id) AS points
FROM collection_items i
JOIN folders f ON f.id = i.folder_id
JOIN cards c ON c.id = i.card_id
JOIN card_sets s ON s.id = c.set_id
WHERE i.card_id IS NOT NULL
ORDER BY f.name, s.external_id, c.number
"""


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    async with create_session_factory(engine)() as session:
        rows = (await session.execute(text(SQL))).all()
        # Wert wie in der App: Positionen ohne Preis haben keine Preispunkte der passenden Art.
    await engine.dispose()
    print(f"# Sammlungskarten: {len(rows)}\n")
    for row in rows:
        if row.points and row.cm and not row.company:
            continue  # Rohkarte mit Cardmarket-Produkt und Preisen – vermutlich mit Wert
        slab = f" · {row.company} {row.grade}" if row.company else ""
        print(
            f"- [{row.folder}] {row.set_} ({row.language}, Größe {row.size}) {row.number} "
            f"{row.name} / {row.name_en or '–'}{slab} · CM {row.cm or '–'} · "
            f"Preise {row.points} · {row.checks or 'nie geprüft'}"
        )


asyncio.run(main())
