"""Warum findet der Collectr-Import eine Karte nicht? (nur lesend, im api-Container)

Sucht einen Namen bei Cardmarket (englische Produktnamen) und zeigt je Treffer: Ausgabe,
ob ein Kartenkiste-Set mit dieser Ausgabe verknüpft ist, und ob eine Katalogkarte auf das
Produkt zeigt. Dazu alle Katalogkarten mit der gesuchten Nummer in Sets der Größe.

    docker compose exec -T -e NAME="Pokemon Ranger" -e NUMBER=58 -e SIZE=54 \
        api python - < deploy/spikes/collectr_missing.py
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory

NAME = os.environ.get("NAME", "Pokemon Ranger")
NUMBER = os.environ.get("NUMBER", "")
SIZE = os.environ.get("SIZE", "")


async def main() -> None:
    engine = create_engine(get_settings().database_url)
    async with create_session_factory(engine)() as session:
        print(f"## Cardmarket: „{NAME}“\n")
        products = (
            await session.execute(
                text(
                    """
                    SELECT p.id_product, p.name, p.id_expansion, e.label,
                           (SELECT string_agg(s.external_id || ' (' || s.language || ')', ', ')
                              FROM card_sets s WHERE s.cardmarket_expansion_id = p.id_expansion)
                             AS sets,
                           (SELECT string_agg(s.external_id || ' ' || c.number, ', ')
                              FROM cards c JOIN card_sets s ON s.id = c.set_id
                             WHERE coalesce(c.cardmarket_product_override,
                                            c.cardmarket_product_id) = p.id_product) AS cards
                    FROM cm_products p
                    LEFT JOIN cm_expansions e ON e.id_expansion = p.id_expansion
                    WHERE p.game = 'pokemon' AND p.name ILIKE :name
                    ORDER BY p.id_expansion DESC LIMIT 25
                    """
                ),
                {"name": f"%{NAME}%"},
            )
        ).all()
        for row in products:
            print(
                f"- Produkt {row.id_product} „{row.name}“ · Ausgabe {row.id_expansion}"
                f" ({row.label or 'ohne Bezeichnung'}) · Kartenkiste-Set: {row.sets or '—'}"
                f" · verknüpfte Karte: {row.cards or '—'}"
            )
        if NUMBER:
            print(f"\n## Katalog: Nummer {NUMBER}" + (f", Setgröße {SIZE}" if SIZE else ""))
            cards = (
                await session.execute(
                    text(
                        """
                        SELECT s.external_id, s.name, s.language, s.card_count_official AS official,
                               s.card_count_total AS total, c.number, c.name AS card
                        FROM cards c JOIN card_sets s ON s.id = c.set_id
                        WHERE c.number_norm = :number AND s.game = 'pokemon'
                          AND s.language IN ('ja', 'en')
                          AND (:size = '' OR s.card_count_official = CAST(NULLIF(:size, '') AS int)
                               OR s.card_count_total = CAST(NULLIF(:size, '') AS int)
                               OR s.card_count_official IS NULL)
                        ORDER BY s.release_date DESC NULLS LAST LIMIT 40
                        """
                    ),
                    {"number": NUMBER.lstrip("0"), "size": SIZE},
                )
            ).all()
            for row in cards:
                print(
                    f"- {row.external_id} ({row.language}) {row.name} · Größe "
                    f"{row.official}/{row.total} · {row.number} {row.card}"
                )
        print("\n## Neueste japanische Sets im Katalog\n")
        for row in (
            await session.execute(
                text(
                    "SELECT external_id, name, release_date, card_count_official FROM card_sets "
                    "WHERE game = 'pokemon' AND language = 'ja' "
                    "ORDER BY release_date DESC NULLS LAST LIMIT 8"
                )
            )
        ).all():
            print(f"- {row.external_id} {row.name} ({row.release_date}, {row.card_count_official})")
    await engine.dispose()


asyncio.run(main())
