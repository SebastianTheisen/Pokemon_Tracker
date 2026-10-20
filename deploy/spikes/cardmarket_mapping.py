"""Spike 2: Lassen sich falsche TCGdex→Cardmarket-Verknüpfungen über den Katalog erkennen?

Erkenntnis aus Spike 1: Produktnamen enthalten weder Setkürzel noch Nummer, aber jedes Produkt
hat ``idExpansion`` (Ausgabe/Set bei Cardmarket) und ``idMetacard`` (dieselbe Karte über alle
Ausgaben und Sprachen hinweg). Idee:

1. Für ein TCGdex-Set alle Cardmarket-IDs holen → deren ``idExpansion`` zählen.
   Die Mehrheit ist die richtige Cardmarket-Ausgabe für dieses Set.
2. Karten, deren Produkt in einer anderen Ausgabe liegt, sind verdächtig.
3. Ersatz: Produkt mit derselben ``idMetacard`` in der Mehrheits-Ausgabe.

Dieser Spike prüft das an echten Sets und zeigt alle Ausgaben von Metakarte 211560 (Glurak).

    docker compose exec -T api python - < deploy/spikes/cardmarket_mapping.py
"""

from __future__ import annotations

import asyncio
import traceback
from collections import Counter, defaultdict
from typing import Any

import httpx

UA = "Kartenkiste/0.1 (private Sammel-App, Test der Cardmarket-Verknüpfung)"
CATALOG = "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
GUIDE = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"
TCGDEX = "https://api.tcgdex.net/v2"
# (Sprache, Set-ID bei TCGdex) – das Problem-Set und zwei Vergleichs-Sets.
SETS = [("ja", "M6a"), ("ja", "SV2a"), ("en", "sv03.5"), ("de", "sv03.5")]
GLURAK_METACARD = 211560


def emit(line: str = "") -> None:
    """Sofort ausgeben – bricht etwas ab, steht alles Bisherige schon im Bericht."""
    print(line, flush=True)


emit("# Spike 2: Cardmarket-Verknüpfung über Katalog prüfen\n")


async def tcgdex_json(client: httpx.AsyncClient, path: str) -> Any:
    response = await client.get(f"{TCGDEX}{path}")
    response.raise_for_status()
    return response.json()


async def set_products(
    client: httpx.AsyncClient, language: str, set_id: str
) -> list[tuple[str, str, int | None]]:
    """(lokale Nummer, Name, idProduct) je Karte des Sets."""
    data = await tcgdex_json(client, f"/{language}/sets/{set_id}")
    cards = data.get("cards") or []
    semaphore = asyncio.Semaphore(4)

    async def one(card: dict[str, Any]) -> tuple[str, str, int | None]:
        async with semaphore:
            try:
                detail = await tcgdex_json(client, f"/{language}/cards/{card['id']}")
            except httpx.HTTPError:
                return (str(card.get("localId")), str(card.get("name")), None)
        cardmarket = (detail.get("pricing") or {}).get("cardmarket") or {}
        product = cardmarket.get("idProduct")
        return (
            str(detail.get("localId")),
            str(detail.get("name")),
            product if isinstance(product, int) and product > 0 else None,
        )

    return list(await asyncio.gather(*(one(card) for card in cards)))


async def main() -> None:
    async with httpx.AsyncClient(
        headers={"User-Agent": UA}, timeout=120, follow_redirects=True
    ) as client:
        catalog = (await client.get(CATALOG)).json()["products"]
        guide = (await client.get(GUIDE)).json()["priceGuides"]
        by_id: dict[int, dict[str, Any]] = {row["idProduct"]: row for row in catalog}
        trend = {row["idProduct"]: row.get("trend") for row in guide}
        by_meta: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in catalog:
            by_meta[row["idMetacard"]].append(row)
        expansion_sizes = Counter(row["idExpansion"] for row in catalog)
        emit(f"- Katalog: {len(catalog)} Produkte, {len(expansion_sizes)} Ausgaben\n")

        emit(f"## Metakarte {GLURAK_METACARD} (alle Ausgaben dieser Glurak-Karte)\n")
        for row in sorted(by_meta[GLURAK_METACARD], key=lambda r: r["idExpansion"]):
            emit(
                f"- idProduct {row['idProduct']}, Ausgabe {row['idExpansion']} "
                f"({expansion_sizes[row['idExpansion']]} Karten), hinzugefügt "
                f"{row['dateAdded']}, Trend {trend.get(row['idProduct'])} €, `{row['name']}`"
            )
        emit()

        for language, set_id in SETS:
            emit(f"## TCGdex {language}/{set_id}\n")
            try:
                rows = await set_products(client, language, set_id)
            except Exception as exc:
                emit(f"- ❌ {type(exc).__name__}: {exc}\n")
                continue
            linked = [(num, name, pid) for num, name, pid in rows if pid is not None]
            unknown = [pid for _, _, pid in linked if pid not in by_id]
            expansions = Counter(by_id[pid]["idExpansion"] for _, _, pid in linked if pid in by_id)
            emit(
                f"- Karten: {len(rows)}, mit Cardmarket-ID: {len(linked)}, "
                f"nicht im Katalog: {len(unknown)}"
            )
            emit(
                "- Ausgaben (idExpansion: Anzahl Karten des Sets / Größe der Ausgabe): "
                + ", ".join(f"{e}: {n}/{expansion_sizes[e]}" for e, n in expansions.most_common(8))
            )
            if not expansions:
                emit()
                continue
            majority = expansions.most_common(1)[0][0]
            outliers = [
                (num, name, pid)
                for num, name, pid in linked
                if pid in by_id and by_id[pid]["idExpansion"] != majority
            ]
            emit(f"- Mehrheits-Ausgabe: {majority}; abweichend: {len(outliers)}")
            for num, name, pid in sorted(outliers)[:25]:
                product = by_id[pid]
                siblings = [
                    s for s in by_meta[product["idMetacard"]] if s["idExpansion"] == majority
                ]
                fix = ", ".join(f"{s['idProduct']} `{s['name']}`" for s in siblings) or "keiner"
                emit(
                    f"  - {num} {name}: {pid} (Ausgabe {product['idExpansion']}, "
                    f"`{product['name']}`) → Ersatz in {majority}: {fix}"
                )
            emit()


try:
    asyncio.run(main())
except Exception:
    emit("\n## ❌ Abbruch\n\n```\n" + traceback.format_exc() + "```")
