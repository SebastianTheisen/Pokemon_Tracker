"""Sammlungskarten ohne Wert – gerechnet wie in der App (``value_item``), dazu Set, Nummer,
Namen, Cardmarket-Produkt, Slab, vorhandene Preis-Kennzahlen und was jede Preisquelle zuletzt
gemeldet hat. Nur lesend, im api-Container.

    docker compose exec -T api python - < deploy/spikes/missing_values.py
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models import CollectionItem, User
from app.services.price_health import SourceHealth
from app.services.pricing import PriceService
from app.services.valuation import value_item

INFO_SQL = """
SELECT c.id, f.name AS folder, s.external_id AS set_, s.language, s.card_count_official AS size,
       c.number, c.name, c.name_en, coalesce(c.cardmarket_product_override,
       c.cardmarket_product_id) AS cm,
       (SELECT string_agg(pc.source || '=' || CASE WHEN pc.ok THEN 'ok' ELSE 'fehler' END
               || coalesce(' (' || left(pc.message, 60) || ')', ''), '; ')
          FROM price_checks pc WHERE pc.card_id = c.id) AS checks
FROM collection_items i
JOIN folders f ON f.id = i.folder_id
JOIN cards c ON c.id = i.card_id
JOIN card_sets s ON s.id = c.set_id
WHERE i.id = :item_id
"""


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    health = SourceHealth(threshold=3, pause=timedelta(minutes=1))
    async with create_session_factory(engine)() as session:
        prices = PriceService(session, settings, [], health)
        for user in (await session.scalars(select(User))).all():
            items = (
                await session.scalars(
                    select(CollectionItem).where(
                        CollectionItem.user_id == user.id, CollectionItem.card_id.is_not(None)
                    )
                )
            ).all()
            if not items:
                continue
            by_card = await prices.prices_for_cards([i.card_id for i in items], user)
            missing = [i for i in items if not value_item(i, by_card).has_value]
            graded = sum(1 for i in items if i.grading_company)
            print(
                f"# {user.email}: {len(items)} Positionen ({graded} Slabs), "
                f"ohne Wert: {len(missing)}\n"
            )
            lines = []
            for item in missing:
                row = (await session.execute(text(INFO_SQL), {"item_id": item.id})).one()
                offers = by_card[item.card_id].offers
                metrics = ", ".join(
                    f"{o.source}/{o.variant}:{'+'.join(sorted(o.metrics))}" for o in offers
                )
                slab = f" · {item.grading_company} {item.grade}" if item.grading_company else ""
                lines.append(
                    f"- [{row.folder}] {row.set_} ({row.language}, Größe {row.size}) "
                    f"{row.number} {row.name} / {row.name_en or '–'}{slab} · "
                    f"CM {row.cm or '–'} · Kennzahlen: {metrics or 'keine'} · "
                    f"{row.checks or 'nie geprüft'}"
                )
            print("\n".join(sorted(lines)) + "\n")
    await engine.dispose()


asyncio.run(main())
