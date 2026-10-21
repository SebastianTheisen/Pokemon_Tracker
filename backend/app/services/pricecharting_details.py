"""Details einer Karte bei PriceCharting speichern und aufbereiten.

Die Produktseite (Apify-Dienst ``parsebird/pricecharting-product-scraper``) liefert mehr als
Preise – Spike ``docs/phase5/apify_runs_k.md``:

* ``populationReport``: je Firma und Note die Zahl gegradeter Exemplare (PSA, CGC),
* ``salesVolume``: Zahl der Verkäufe je Note (wie belastbar ist der Preis?),
* ``recentSales``: je Note die letzten Verkäufe (Datum, Titel, Preis in USD, Quelle, Link),
* ``priceHistory``: Verlauf (Format nicht dokumentiert – unverändert gespeichert),
* ``images``: Bilder in 1600 px.

Gespeichert wird gekürzt (je Note höchstens :data:`SALES_PER_GRADE` Verkäufe).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceChartingDetail

SALES_PER_GRADE = 10
SHOWN_SALES = 15
MAX_IMAGES = 4
_SALE_FIELDS = ("date", "title", "price", "source", "url")


def _counts(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) and value else None


def trim_sales(value: object) -> list[dict[str, Any]]:
    """Verkäufe aller Noten als flache Liste (Note in ``grade``), je Note gekürzt."""
    if not isinstance(value, dict):
        return []
    sales = []
    for grade, entries in value.items():
        for entry in (entries if isinstance(entries, list) else [])[:SALES_PER_GRADE]:
            if isinstance(entry, dict) and entry.get("price") is not None:
                sales.append({"grade": str(grade), **{key: entry.get(key) for key in _SALE_FIELDS}})
    return sales


async def store_details(
    session: AsyncSession, card_id: uuid.UUID, item: dict[str, Any], *, fetched_at: datetime
) -> None:
    """Details einer Karte speichern (ersetzt den vorigen Stand). Commit macht der Aufrufer."""
    images = [str(url) for url in item.get("images") or [] if isinstance(url, str)]
    values = {
        "card_id": card_id,
        "product_url": str(item.get("url") or "")[:500] or None,
        "population": _counts(item.get("populationReport")),
        "sales_volume": _counts(item.get("salesVolume")),
        "recent_sales": trim_sales(item.get("recentSales")),
        "price_history": item.get("priceHistory"),
        "images": images[:MAX_IMAGES] or None,
        "fetched_at": fetched_at,
    }
    statement = insert(PriceChartingDetail).values(values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[PriceChartingDetail.card_id],
            set_={key: statement.excluded[key] for key in values if key != "card_id"},
        )
    )


@dataclass(frozen=True)
class Sale:
    grade: str
    date: str | None
    title: str | None
    price_usd: float
    source: str | None
    url: str | None


def latest_sales(detail: PriceChartingDetail, limit: int = SHOWN_SALES) -> list[Sale]:
    """Die neuesten Verkäufe über alle Noten (für die Anzeige)."""
    sales = [
        Sale(
            grade=str(entry.get("grade") or ""),
            date=str(entry["date"]) if entry.get("date") else None,
            title=str(entry["title"])[:200] if entry.get("title") else None,
            price_usd=float(entry["price"]),
            source=str(entry["source"]) if entry.get("source") else None,
            url=str(entry["url"]) if entry.get("url") else None,
        )
        for entry in detail.recent_sales or []
        if isinstance(entry.get("price"), int | float)
    ]
    sales.sort(key=lambda sale: sale.date or "", reverse=True)
    return sales[:limit]
