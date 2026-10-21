"""Spike: Warum bekommen versiegelte Produkte kein Bild? Plus Stichprobe der Treffer.

Lädt die TCGplayer-Produkte wie der echte Abgleich (tcgcsv.com, ~500 kleine Abrufe) und
ordnet jedem versiegelten Cardmarket-Produkt ohne Bild einen Grund zu:

* ``kein Kandidat`` – kein TCGplayer-Produkt hat ein gemeinsames Wort
* ``andere Art``    – ein guter Name existiert, aber die Produktart weicht ab
* ``zu unähnlich``  – bester passender Kandidat unter der Schwelle (mit Verteilung)
* ``zweideutig``    – zwei fast gleich gute Kandidaten

Dazu eine zufällige Stichprobe von Treffern zum Gegenlesen (falsches Bild?). Ändert nichts.

    docker compose exec -T api python - < deploy/spikes/sealed_images_misses.py
"""

from __future__ import annotations

import asyncio
import random
from collections import Counter, defaultdict

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models import CmPrice, CmProduct
from app.services.cardmarket_catalog import SINGLE_CATEGORY
from app.services.sealed import kind_for
from app.services.sealed_images import (
    MIN_LEAD,
    MIN_SIMILARITY,
    MIN_SIMILARITY_ANY_KIND,
    Candidate,
    Matcher,
    _asian_expansions,
    download_products,
    tokens,
)

EXAMPLES_PER_REASON = 12
SAMPLE = 30


def emit(line: str = "") -> None:
    print(line, flush=True)


def describe(candidates: list[Candidate]) -> str:
    return " | ".join(f"{c.score:.2f} {c.product.name} [{c.kind.value}]" for c in candidates) or "–"


def reason_for(candidates: list[Candidate], kinds_ok: list[Candidate]) -> str:
    if not candidates:
        return "kein Kandidat"
    if kinds_ok and kinds_ok[0].acceptable:
        return "zweideutig"
    if candidates[0].score >= MIN_SIMILARITY:
        return "andere Art"
    return "zu unähnlich"


async def main() -> None:  # noqa: PLR0915 – Spike, linear lesbar
    emit("# Spike: Sealed-Bilder – Fehlschläge und Stichprobe\n")
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
    names = {product.product_id: product.name for product in products}
    matcher = Matcher(products)
    emit(f"- TCGplayer-Produkte (versiegelt, mit Bild): {len(products)}")
    emit(
        f"- Schwelle {MIN_SIMILARITY} (unbekannte Art {MIN_SIMILARITY_ANY_KIND}), "
        f"Vorsprung {MIN_LEAD}\n"
    )

    totals: Counter[str] = Counter()
    hits: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = defaultdict(Counter)
    histogram: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    matched: list[str] = []
    for cm, metrics in rows:
        category = cm.category_name or "?"
        totals[category] += 1
        kind = kind_for(cm.category_name, cm.name)
        if cm.image_url:
            hits[category] += 1
            tcg_name = names.get(cm.tcgplayer_product_id or 0, "?")
            matched.append(f"- {cm.name} ({kind.value}) → {tcg_name} · {cm.image_url}")
            continue
        language = "ja" if cm.id_expansion in asian else "en"
        candidates = matcher.ranked(cm.name, kind, language, limit=0)
        kinds_ok = [c for c in candidates if c.same_kind or c.kind.value == "other"]
        reason = reason_for(candidates, kinds_ok)
        if reason == "zu unähnlich":
            score = kinds_ok[0].score if kinds_ok else 0.0
            histogram[f"{int(score * 10) / 10:.1f}"] += 1
        reasons[category][reason] += 1
        if metrics and len(examples[reason]) < EXAMPLES_PER_REASON:
            shown = kinds_ok if reason in {"zu unähnlich", "zweideutig"} else candidates
            examples[reason].append(
                f"- **{cm.name}** ({category}, {kind.value}) `{' '.join(sorted(tokens(cm.name)))}`"
                f"\n  → {describe(shown[:3])}"
            )

    total, found = sum(totals.values()), sum(hits.values())
    emit(f"**Mit Bild: {found} von {total} ({found * 100 // max(total, 1)} %)**\n")
    emit("## Je Cardmarket-Kategorie\n")
    emit(
        "| Kategorie | Produkte | mit Bild | kein Kandidat | andere Art | zu unähnlich "
        "| zweideutig |"
    )
    emit("|---|---|---|---|---|---|---|")
    for category, count in totals.most_common():
        r = reasons[category]
        emit(
            f"| {category} | {count} | {hits[category]} | {r['kein Kandidat']} | "
            f"{r['andere Art']} | {r['zu unähnlich']} | {r['zweideutig']} |"
        )
    emit()
    emit(f"Ähnlichkeit bei „zu unähnlich“: {dict(sorted(histogram.items()))}\n")
    emit(f"## Stichprobe Treffer ({SAMPLE}, zum Gegenlesen)\n")
    for line in random.Random(1).sample(matched, min(SAMPLE, len(matched))):  # noqa: S311
        emit(line)
    emit()
    for reason in ("andere Art", "zu unähnlich", "zweideutig", "kein Kandidat"):
        emit(f"## Beispiele „{reason}“ (mit Preis)\n")
        for line in examples[reason] or ["- keine"]:
            emit(line)
        emit()


asyncio.run(main())
