"""Prüfung nach dem ersten One-Piece-Import (nur lesend, Datenbank im api-Container).

1. Wo englische und japanische Fassung eines Sets mit **verschiedenen** Cardmarket-Ausgaben
   verknüpft sind: Erscheinungsdatum, Größe, Zwillinge, typischer Preis und je ein
   Beispiel-Link – öffnet man ihn, zeigt Cardmarket den Namen der Ausgabe
   (z. B. „… (Japanese)“). So lässt sich belegen, ob Cardmarket eigene japanische
   Ausgaben führt.
2. Karten ohne Cardmarket-Produkt: normal vs. Parallel/Nachdruck, die größten Sets.

    docker compose exec -T api python - < deploy/spikes/onepiece_check.py
"""

from __future__ import annotations

import asyncio
from statistics import median
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory

CM = "https://www.cardmarket.com/de/OnePiece/Products?idProduct="
out: list[str] = ["# One Piece: Prüfung der Cardmarket-Verknüpfung\n"]


async def rows(session: Any, sql: str, **params: Any) -> list[Any]:
    return list((await session.execute(text(sql), params)).all())


async def main() -> None:
    engine = create_engine(get_settings().database_url)
    async with create_session_factory(engine)() as session:
        links = await rows(
            session,
            """
            SELECT external_id, language, name, cardmarket_expansion_id AS exp
            FROM card_sets WHERE game = 'onepiece' AND cardmarket_expansion_id IS NOT NULL
            ORDER BY external_id, language
            """,
        )
        by_set: dict[str, dict[str, Any]] = {}
        for row in links:
            by_set.setdefault(row.external_id, {})[row.language] = row
        expansions = {
            r.id_expansion: r
            for r in await rows(
                session,
                "SELECT id_expansion, first_added, product_count, twin_ids FROM cm_expansions "
                "WHERE game = 'onepiece'",
            )
        }

        async def describe(expansion_id: int) -> str:
            info = expansions.get(expansion_id)
            trends = [
                float(r.trend)
                for r in await rows(
                    session,
                    """
                    SELECT (p.metrics->>'trend')::numeric AS trend
                    FROM cm_products c JOIN cm_prices p ON p.id_product = c.id_product
                    WHERE c.id_expansion = :e AND c.id_category = 1621
                      AND p.metrics ? 'trend'
                    """,
                    e=expansion_id,
                )
            ]
            sample = await rows(
                session,
                "SELECT id_product, name FROM cm_products WHERE id_expansion = :e "
                "AND id_category = 1621 ORDER BY id_product LIMIT 1",
                e=expansion_id,
            )
            link = f"[{sample[0].name}]({CM}{sample[0].id_product})" if sample else "–"
            if info is None:
                return f"{expansion_id}: unbekannt"
            return (
                f"{expansion_id}: ab {info.first_added}, {info.product_count} Produkte, "
                f"Zwillinge {list(info.twin_ids) or '–'}, Median-Trend "
                f"{f'{median(trends):.2f} €' if trends else '–'} ({len(trends)} Preise), "
                f"Beispiel {link}"
            )

        out.append("## 1. Englisch und Japanisch mit verschiedenen Ausgaben\n")
        different = [
            (external_id, langs)
            for external_id, langs in by_set.items()
            if "en" in langs and "ja" in langs and langs["en"].exp != langs["ja"].exp
        ]
        out.append(f"{len(different)} von {len(by_set)} Sets.\n")
        for external_id, langs in different:
            out.append(f"### {external_id} – {langs['en'].name}")
            out.append(f"- EN → {await describe(langs['en'].exp)}")
            out.append(f"- JA → {await describe(langs['ja'].exp)}")
            out.append("")
        same = [e for e, langs in by_set.items() if len({r.exp for r in langs.values()}) == 1]
        out.append(f"Gleiche Ausgabe für alle Sprachen: {len(same)} Sets, z. B. {same[:8]}\n")

        out.append("## 2. Karten ohne Cardmarket-Produkt\n")
        unlinked = await rows(
            session,
            """
            SELECT s.language, s.external_id,
                   count(*) FILTER (WHERE c.external_id !~ '_[pr][0-9]+$') AS normal,
                   count(*) FILTER (WHERE c.external_id ~ '_[pr][0-9]+$') AS variants
            FROM cards c JOIN card_sets s ON s.id = c.set_id
            WHERE s.game = 'onepiece' AND c.cardmarket_product_id IS NULL
              AND c.cardmarket_product_override IS NULL
            GROUP BY s.language, s.external_id
            ORDER BY count(*) DESC
            """,
        )
        normal = sum(r.normal for r in unlinked)
        variants = sum(r.variants for r in unlinked)
        out.append(f"- normal: {normal}, Parallel/Nachdruck: {variants}")
        for r in unlinked[:15]:
            out.append(f"  - {r.language}/{r.external_id}: {r.normal} normal, {r.variants} Fassungen")
    await engine.dispose()
    print("\n".join(out))


asyncio.run(main())
