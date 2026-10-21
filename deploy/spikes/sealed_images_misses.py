"""Spike: Warum bekommen versiegelte Produkte kein Bild? (Analyse der Fehlschläge)

Lädt die TCGplayer-Produkte wie der echte Abgleich (tcgcsv.com, ~500 kleine Abrufe) und
ordnet jedem versiegelten Cardmarket-Produkt ohne Bild einen Grund zu:

* ``kein Kandidat``     – kein TCGplayer-Produkt hat ein gemeinsames Wort
* ``andere Art``        – ein gutes Namens-Paar existiert, aber die Produktart weicht ab
* ``zu unähnlich``      – bestes Paar gleicher Art unter der Schwelle (mit Verteilung)
* ``zweideutig``        – zwei fast gleich gute Kandidaten

Je Cardmarket-Kategorie Anzahl, Treffer und Gründe, dazu Beispiele mit dem besten Kandidaten.
Ändert nichts an der Datenbank.

    docker compose exec -T api python - < deploy/spikes/sealed_images_misses.py
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models import CmPrice, CmProduct
from app.services.cardmarket_catalog import SINGLE_CATEGORY
from app.services.sealed import kind_for
from app.services.sealed_images import (
    MIN_LEAD,
    MIN_SIMILARITY,
    TcgProduct,
    _asian_expansions,
    _similarity,
    download_products,
    tokens,
)

EXAMPLES_PER_REASON = 12


def emit(line: str = "") -> None:
    print(line, flush=True)


def best_pairs(
    words: frozenset[str], pool: list[tuple[TcgProduct, frozenset[str], Any]]
) -> list[tuple[float, TcgProduct, Any]]:
    scored = [(_similarity(words, w), product, kind) for product, w, kind in pool if words & w]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:3]


async def main() -> None:  # noqa: PLR0915 – Spike, linear lesbar
    emit("# Spike: Sealed-Bilder – warum kein Treffer?\n")
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        rows = (
            await session.execute(
                select(CmProduct, CmPrice.metrics)
                .outerjoin(CmPrice, CmPrice.id_product == CmProduct.id_product)
                .where(CmProduct.id_category.is_not(None), CmProduct.id_category != SINGLE_CATEGORY)
            )
        ).all()
        asian = await _asian_expansions(session)
    await engine.dispose()

    products = await download_products(settings)
    emit(f"- TCGplayer-Produkte (versiegelt, mit Bild): {len(products)}")
    pools: dict[str, list[tuple[TcgProduct, frozenset[str], Any]]] = defaultdict(list)
    for product in products:
        pools[product.language].append(
            (product, tokens(product.name), kind_for(None, product.name))
        )
    emit(f"- je Sprache: { {lang: len(pool) for lang, pool in pools.items()} }")
    emit(f"- Arten bei TCGplayer: {dict(Counter(k.value for p in pools.values() for *_, k in p))}")
    emit()

    totals: Counter[str] = Counter()
    hits: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = defaultdict(Counter)
    histogram: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    kinds_cm: Counter[str] = Counter()
    for cm, metrics in rows:
        category = cm.category_name or "?"
        totals[category] += 1
        kind = kind_for(cm.category_name, cm.name)
        kinds_cm[f"{category} → {kind.value}"] += 1
        if cm.image_url:
            hits[category] += 1
            continue
        words = tokens(cm.name)
        languages = ("ja", "en") if cm.id_expansion in asian else ("en", "ja")
        pool = pools.get(languages[0], [])
        top_any = best_pairs(words, pool)
        top_same = best_pairs(words, [entry for entry in pool if entry[2] == kind])
        if not top_any:
            reason = "kein Kandidat"
        elif top_same and top_same[0][0] >= MIN_SIMILARITY:
            reason = "zweideutig"
        elif top_any[0][0] >= MIN_SIMILARITY:
            reason = "andere Art"
        else:
            reason = "zu unähnlich"
            score = top_same[0][0] if top_same else 0.0
            histogram[f"{int(score * 10) / 10:.1f}"] += 1
        reasons[category][reason] += 1
        if metrics and len(examples[reason]) < EXAMPLES_PER_REASON:
            shown = top_same if reason in {"zu unähnlich", "zweideutig"} else top_any
            candidates = " | ".join(
                f"{score:.2f} {cand.name} [{cand_kind.value}]" for score, cand, cand_kind in shown
            )
            examples[reason].append(
                f"- **{cm.name}** ({category}, {kind.value}) `{' '.join(sorted(words))}`"
                f"\n  → {candidates or '–'}"
            )

    emit("## Je Cardmarket-Kategorie\n")
    emit(
        "| Kategorie | Produkte | mit Bild | kein Kandidat | andere Art | zu unähnlich "
        "| zweideutig |"
    )
    emit("|---|---|---|---|---|---|---|")
    for category, total in totals.most_common():
        r = reasons[category]
        emit(
            f"| {category} | {total} | {hits[category]} | {r['kein Kandidat']} | "
            f"{r['andere Art']} | {r['zu unähnlich']} | {r['zweideutig']} |"
        )
    emit()
    emit(f"Schwelle {MIN_SIMILARITY}, Vorsprung {MIN_LEAD}.")
    emit(f"Ähnlichkeit bei „zu unähnlich“ (beste gleiche Art): {dict(sorted(histogram.items()))}\n")
    emit("## Erkannte Art je Cardmarket-Kategorie\n")
    for entry, count in kinds_cm.most_common(40):
        emit(f"- {entry}: {count}")
    emit()
    for reason in ("andere Art", "zu unähnlich", "zweideutig", "kein Kandidat"):
        emit(f"## Beispiele „{reason}“ (mit Preis)\n")
        for line in examples[reason] or ["- keine"]:
            emit(line)
        emit()


asyncio.run(main())
