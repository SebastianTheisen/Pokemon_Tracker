"""Spike: Bilder für versiegelte Produkte aus tcgcsv.com (Spiegel des TCGplayer-Katalogs).

Prüft (kostenlos, ~250 Abrufe bei tcgcsv.com, je 4 gleichzeitig):

1. Kategorien: Welche Nummer haben „Pokemon“ und „Pokemon Japan“?
2. Produktfelder: Gibt es eine Bildadresse (``imageUrl``)? Wie erkennt man Versiegeltes?
3. Zuordnung: Wie viele versiegelte Produkte aus unserem Cardmarket-Katalog (``cm_products``)
   finden über den Namen ein TCGplayer-Produkt mit Bild?
4. Lädt das Bild (Statuscode, Typ, Größe)?

    docker compose exec -T api python - < deploy/spikes/sealed_images.py
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models import CmPrice, CmProduct

BASE = "https://tcgcsv.com/tcgplayer"
UA = "Kartenkiste/0.1 (private Sammel-App, Test)"
SINGLE_CATEGORY = 51


def emit(line: str = "") -> None:
    print(line, flush=True)


def short(value: object, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def normalize(name: str) -> str:
    """Vergleichsform: Kleinbuchstaben, ohne Satzzeichen, „Pokémon“/„TCG“/„SV:“ entfernt."""
    text = name.casefold().replace("é", "e")
    text = re.sub(r"\b(pokemon|tcg|the)\b", " ", text)
    text = re.sub(r"\b(sv|swsh|sm|xy|me)\d*[a-z]?\s*:", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


async def get_json(client: httpx.AsyncClient, path: str) -> Any:
    response = await client.get(f"{BASE}{path}")
    response.raise_for_status()
    data = response.json()
    return data.get("results", data) if isinstance(data, dict) else data


async def products_of(
    client: httpx.AsyncClient, category: int, semaphore: asyncio.Semaphore
) -> list[dict[str, Any]]:
    groups = await get_json(client, f"/{category}/groups")

    async def one(group: dict[str, Any]) -> list[dict[str, Any]]:
        async with semaphore:
            try:
                return list(await get_json(client, f"/{category}/{group['groupId']}/products"))
            except (httpx.HTTPError, ValueError):
                return []

    batches = await asyncio.gather(*(one(group) for group in groups))
    return [product for batch in batches for product in batch]


def is_sealed(product: dict[str, Any]) -> bool:
    """Karten haben in ``extendedData`` eine Nummer – Versiegeltes nicht."""
    names = {str(entry.get("name")) for entry in product.get("extendedData") or []}
    return "Number" not in names


async def main() -> None:
    emit("# Spike: Bilder für versiegelte Produkte (tcgcsv.com)\n")
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        rows = (
            await session.execute(
                select(
                    CmProduct.id_product, CmProduct.name, CmProduct.category_name, CmPrice.metrics
                )
                .outerjoin(CmPrice, CmPrice.id_product == CmProduct.id_product)
                .where(CmProduct.id_category.is_not(None), CmProduct.id_category != SINGLE_CATEGORY)
            )
        ).all()
    await engine.dispose()
    emit(f"- Versiegelte Produkte im Cardmarket-Katalog: {len(rows)}")
    emit(
        f"- Kategorien bei Cardmarket: {dict(Counter(r.category_name for r in rows).most_common(15))}\n"
    )

    semaphore = asyncio.Semaphore(4)
    async with httpx.AsyncClient(
        headers={"User-Agent": UA}, timeout=60, follow_redirects=True
    ) as client:
        categories = await get_json(client, "/categories")
        pokemon = [c for c in categories if "pokemon" in str(c.get("name", "")).casefold()]
        emit("## Kategorien mit „Pokemon“\n")
        for category in pokemon:
            emit(
                f"- {category.get('categoryId')}: {category.get('name')} ({category.get('displayName')})"
            )
        emit()

        all_products: dict[int, list[dict[str, Any]]] = {}
        for category in pokemon:
            category_id = int(category["categoryId"])
            products = await products_of(client, category_id, semaphore)
            all_products[category_id] = products
            sealed = [p for p in products if is_sealed(p)]
            with_image = [p for p in sealed if p.get("imageUrl")]
            emit(f"## Kategorie {category_id} {category.get('name')}\n")
            emit(
                f"- Produkte: {len(products)}, davon versiegelt: {len(sealed)}, mit Bild: {len(with_image)}"
            )
            if products:
                emit(f"- Felder: {sorted(products[0])}")
            for product in sealed[:5]:
                emit(
                    f"  - `{short({k: product.get(k) for k in ('productId', 'name', 'imageUrl', 'url')}, 400)}`"
                )
            emit()

        index: dict[str, dict[str, Any]] = {}
        for products in all_products.values():
            for product in products:
                if is_sealed(product) and product.get("imageUrl"):
                    index.setdefault(normalize(str(product.get("name", ""))), product)
        matched = [(row, index.get(normalize(row.name))) for row in rows]
        hits = [(row, product) for row, product in matched if product is not None]
        priced = [row for row in rows if row.metrics]
        priced_hits = [row for row, product in hits if row.metrics]
        emit("## Zuordnung Cardmarket → TCGplayer (gleicher Name)\n")
        emit(f"- Treffer: {len(hits)} von {len(rows)} ({len(hits) * 100 // max(len(rows), 1)} %)")
        emit(f"- Davon mit Cardmarket-Preis: {len(priced_hits)} von {len(priced)}")
        emit(
            f"- Treffer je Kategorie: {dict(Counter(r.category_name for r, _ in hits).most_common(10))}"
        )
        emit("- Beispiele Treffer:")
        for row, product in hits[:12]:
            emit(f"  - {row.name} → {product.get('name')} · {product.get('imageUrl')}")
        emit("- Beispiele ohne Treffer (mit Preis):")
        misses = [row for row, product in matched if product is None and row.metrics]
        for row in misses[:15]:
            emit(f"  - {row.name} ({row.category_name}) → `{normalize(row.name)}`")
        emit()

        if hits:
            image_url = str(hits[0][1]["imageUrl"])
            emit("## Bildabruf\n")
            for url in (image_url, image_url.replace("_200w", "_in_1000x1000")):
                try:
                    response = await client.get(url)
                    emit(
                        f"- `{url}` → HTTP {response.status_code}, "
                        f"{response.headers.get('content-type')}, {len(response.content)} Bytes"
                    )
                except httpx.HTTPError as exc:
                    emit(f"- `{url}` → {type(exc).__name__}")


asyncio.run(main())
