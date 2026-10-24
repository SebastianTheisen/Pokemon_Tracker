"""Spike: Warum ist die Kartensuche langsam? Zeit und Abfrageplan je Schreibweise.

Aufruf: ``docker compose exec -T api python - < deploy/spikes/search_explain.py``
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models import Card
from app.services.card_names import foreign_search_terms
from app.services.catalog_search import _name_condition, _name_score, search_cards


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        locale = (
            await session.execute(
                text(
                    "SELECT datcollate, datctype FROM pg_database "
                    "WHERE datname = current_database()"
                )
            )
        ).one()
        print(f"Datenbank-Locale: collate={locale[0]} ctype={locale[1]}")
        trigrams = await session.scalar(text("SELECT show_trgm('リザードン')"))
        print(f"Trigramme für 'リザードン': {trigrams}")
        threshold = await session.scalar(text("SHOW pg_trgm.word_similarity_threshold"))
        print(f"Trigramm-Schwelle: {threshold}")
        print()
        for query in ("glurak", "pikachu", "nachtara 215"):
            started = time.perf_counter()
            await search_cards(session, query)
            print(f"search_cards('{query}'): {(time.perf_counter() - started) * 1000:.0f} ms")
        print()
        terms = ["glurak", *foreign_search_terms("glurak")]
        print(f"Schreibweisen für 'glurak': {terms}")
        for term in terms:
            statement = (
                select(Card.external_id, func.max(_name_score(term)))
                .where(_name_condition(term), Card.external_id.is_not(None))
                .group_by(Card.external_id)
                .order_by(func.max(_name_score(term)).desc())
                .limit(30)
            )
            compiled = statement.compile(
                dialect=engine.dialect, compile_kwargs={"literal_binds": True}
            )
            started = time.perf_counter()
            plan = (await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {compiled}"))).all()
            elapsed = (time.perf_counter() - started) * 1000
            print(f"\n## '{term}': {elapsed:.0f} ms")
            for (line,) in plan[:14]:
                print("   ", line)
    await engine.dispose()


asyncio.run(main())
