"""Warum findet PriceCharting keinen eindeutigen Treffer? Für jede Sammlungskarte, deren
letzte PriceCharting-Prüfung „kein eindeutiger Treffer“ meldet: Suche wie die App, aber mit
bis zu 10 Ergebnissen, und je Ergebnis Name, Rubrik, Nummer, Datum und ob/wie es zählt.

Kostet Apify-Guthaben (~0,05 $ je Karte). Speichert nichts. Im api-Container:

    docker compose exec -T api python - < deploy/spikes/pricecharting_search.py
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models import Card, CollectionItem, PriceCheck
from app.providers.apify import ApifyClient
from app.providers.pricing.pricecharting import _candidates, choose, search_query
from app.services.price_health import SourceHealth
from app.services.pricing import PriceService

MAX_ITEMS = 10


async def main() -> None:
    settings = get_settings()
    token = settings.apify_token
    if token is None:
        raise SystemExit("Kein Apify-Token.")
    engine = create_engine(settings.database_url)
    health = SourceHealth(threshold=3, pause=timedelta(minutes=1))
    async with create_session_factory(engine)() as session:
        cards = (
            await session.scalars(
                select(Card)
                .join(PriceCheck, PriceCheck.card_id == Card.id)
                .where(
                    PriceCheck.source == "pricecharting",
                    PriceCheck.message.like("kein eindeutiger Treffer%"),
                    Card.id.in_(select(CollectionItem.card_id)),
                )
            )
        ).all()
        service = PriceService(session, settings, [], health)
        refs = [await service._context_ref(card) for card in cards]
    await engine.dispose()
    print(f"# {len(refs)} Karten ohne eindeutigen Treffer\n")
    async with ApifyClient(token.get_secret_value(), user_agent=settings.http_user_agent) as client:
        for ref in refs:
            query = search_query(ref)
            run = await client.run_actor(
                settings.pricecharting_actor,
                {"searchQueries": [query], "maxItems": MAX_ITEMS},
                max_charge_usd=0.1,
                timeout_seconds=settings.apify_run_timeout_seconds,
                max_items=MAX_ITEMS,
            )
            scores = {id(m.item): m.score for m in _candidates(ref, run.items)}
            chosen = choose(ref, run.items)
            print(
                f"## {ref.external_id} „{query}“ · Set „{ref.english_set_name or ref.set_name}“ "
                f"{ref.release_date} · {len(run.items)} Ergebnisse · "
                f"gewählt: {chosen.get('name') if chosen else '–'} · {run.cost_usd:.3f} $"
            )
            for item in run.items:
                score = scores.get(id(item))
                mark = f"zählt {score:.2f}" if score is not None else "passt nicht"
                ungraded = (item.get("prices") or {}).get("ungraded")
                print(
                    f"- {item.get('name')} · {item.get('console')} · Nr. "
                    f"{item.get('card_number')} · {item.get('release_date')} · {mark} · "
                    f"ungraded {ungraded}"
                )
            print()


asyncio.run(main())
