"""Spike: Bilder japanischer Vintage-Karten (1996–2006) von PriceCharting – speichert nichts.

Die offizielle Datenbank (pokemon-card.com) beginnt erst 2006; ~2.300 ältere japanische Karten
haben kein Bild (``docs/phase5/jp_check.md``). Geprüft wird:

1. Welche japanischen Sets führt PriceCharting (Set-Liste über Apify-Cheerio, ~0,005 $)?
2. Zwei Sets laden (Collection-Scraper, ~0,02 $): Produktnamen, Nummern, Bilder.
3. Zuordnung zu unseren Karten: japanischer Name → englischer Name (Pokédex), dann Name
   (+ Nummer, falls eindeutig nötig). Ergebnis: wie viele Karten bekämen ein Bild?

Aufruf (im api-Container): ``python - < deploy/spikes/jp_vintage.py``
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models import Card, CardSet
from app.providers.apify import ApifyClient
from app.providers.fx import EcbRates
from app.services.card_names import translate_card_name
from app.services.pricecharting_catalog import CONSOLE_URL, PriceChartingCatalog, parse_product

# Unser Set (TCGdex-ID) → Stichwörter im PriceCharting-Slug (das erste passende gewinnt).
TEST_SETS = {
    "PMCG1": ("japanese-expansion-pack", "japanese-base-set", "japanese-base"),
    "neo1": ("japanese-gold-silver", "japanese-neo-genesis", "japanese-neo"),
}
SAMPLES = 12
_JAPANESE = re.compile(r"/console/(pokemon-japanese-[a-z0-9&%._-]+)", re.I)


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def emit(line: str = "") -> None:
    print(line, flush=True)


async def main() -> None:  # noqa: PLR0912, PLR0915 – Spike, linear
    settings = get_settings()
    token = settings.apify_token
    if token is None or not token.get_secret_value():
        emit("PT_APIFY_TOKEN fehlt")
        return
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)

    def apify() -> ApifyClient:
        return ApifyClient(token.get_secret_value(), user_agent=settings.http_user_agent)

    catalog = PriceChartingCatalog(
        factory,
        settings,
        EcbRates(user_agent=settings.http_user_agent, url=settings.ecb_rates_url),
        apify,
    )
    emit("# Spike: japanische Vintage-Bilder von PriceCharting")
    emit()
    links = await catalog._links_via_apify()
    slugs = sorted({slug.lower() for slug in _JAPANESE.findall(links)})
    emit(f"## Japanische Sets bei PriceCharting ({len(slugs)})")
    emit()
    emit(", ".join(slugs) or "–")
    emit()

    chosen: dict[str, str] = {}
    for set_id, needles in TEST_SETS.items():
        for needle in needles:
            hit = next((slug for slug in slugs if needle in slug), None)
            if hit:
                chosen[set_id] = hit
                break
    emit(f"Test-Sets: {chosen or 'keins gefunden'}")
    if not chosen:
        await engine.dispose()
        return

    async with apify() as client:
        run = await client.run_actor(
            settings.pricecharting_catalog_actor,
            {
                "collections": [CONSOLE_URL + slug for slug in chosen.values()],
                "includeProducts": True,
                "maxItems": len(chosen),
            },
            max_charge_usd=0.05,
            timeout_seconds=600,
            max_items=len(chosen),
        )
    emit(f"Kosten Collection-Scraper: {run.cost_usd or 0:.3f} $")
    by_slug = {
        str(item.get("collectionUrl") or "").rstrip("/").rpartition("/")[2].lower(): item
        for item in run.items
    }

    for set_id, slug in chosen.items():
        collection = by_slug.get(slug) or {}
        products = [p for p in collection.get("products") or [] if isinstance(p, dict)]
        emit()
        emit(f"## {set_id} ↔ {slug}")
        emit()
        with_image = sum(bool(p.get("imageUrl")) for p in products)
        emit(f"- Produkte: {len(products)}, mit Bild: {with_image}")
        emit("- Beispiele: " + " | ".join(str(p.get("productName")) for p in products[:15]))
        if products:
            emit(f"- Beispiel-Bild: {products[0].get('imageUrl')}")

        pc: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for product in products:
            parsed = parse_product(product)
            name = parsed[0] if parsed else str(product.get("productName") or "")
            number = parsed[1] if parsed else ""
            if product.get("imageUrl"):
                pc[key(re.sub(r"\[.*?\]", "", name))].append((number, str(product["imageUrl"])))

        async with factory() as session:
            rows = (
                await session.execute(
                    select(Card.number, Card.name, Card.image_url)
                    .join(CardSet, Card.set_id == CardSet.id)
                    .where(CardSet.external_id == set_id, Card.language == "ja")
                )
            ).all()
        unique = ambiguous = by_number = 0
        missing: list[str] = []
        pairs: list[str] = []
        for number, name, _image in rows:
            english = translate_card_name(name, "ja", target="en") or ""
            hits = pc.get(key(english), [])
            if len(hits) == 1:
                unique += 1
                if len(pairs) < SAMPLES:
                    pairs.append(f"{number} {name} → {english}")
            elif len(hits) > 1:
                if any(hit_number.lstrip("0") == number.lstrip("0") for hit_number, _ in hits):
                    by_number += 1
                else:
                    ambiguous += 1
            else:
                missing.append(f"{number} {name} ({english or '?'})")
        emit(
            f"- Unsere Karten: {len(rows)}; eindeutig per Name: {unique}, "
            f"per Name+Nummer: {by_number}, mehrdeutig: {ambiguous}, ohne Treffer: {len(missing)}"
        )
        emit("- Zuordnungen (Beispiele): " + " | ".join(pairs))
        emit("- Ohne Treffer (Beispiele): " + " | ".join(missing[:20]))
    await engine.dispose()


asyncio.run(main())
