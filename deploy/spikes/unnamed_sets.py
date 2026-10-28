"""Japanische Sets ohne Namen (Name = Kürzel, z. B. „XY11-Bb“) über ihre Karten einem
TCGplayer-Set zuordnen. Nur lesend, im api-Container.

Vergleich: Kartennummer + englischer Name (Pokémon übersetzt, sonst Cardmarket-Name) gegen
die Produkte der TCGplayer-Gruppen (tcgcsv.com, Kategorie 85 = Pokémon Japan).

    docker compose exec -T api python - < deploy/spikes/unnamed_sets.py
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.card_names import translate_card_name
from app.services.catalog_numbers import normalize_number

KEY = re.compile(r"[^a-z0-9]+")
VERSION = re.compile(r"\s*[\(\[].*?[\)\]]")


def key(name: str) -> str:
    return KEY.sub("", VERSION.sub("", name).casefold().replace("é", "e"))


def number_of(product: dict[str, Any]) -> str | None:
    for entry in product.get("extendedData") or []:
        if entry.get("name") == "Number":
            return normalize_number(str(entry.get("value") or ""))
    return None


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    async with create_session_factory(engine)() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT s.external_id, c.number_norm, c.name, m.name AS cm_name
                    FROM card_sets s JOIN cards c ON c.set_id = s.id
                    LEFT JOIN cm_products m ON m.id_product =
                        coalesce(c.cardmarket_product_override, c.cardmarket_product_id)
                    WHERE s.game = 'pokemon' AND s.language = 'ja' AND s.name = s.external_id
                    """
                )
            )
        ).all()
    await engine.dispose()
    ours: dict[str, set[tuple[str, str]]] = {}
    for row in rows:
        english = translate_card_name(row.name, "ja", "en") or row.cm_name or ""
        if english:
            ours.setdefault(row.external_id, set()).add((row.number_norm, key(english)))
    print(f"Namenlose japanische Sets mit Karten: {len(ours)}\n")

    base = settings.sealed_images_url.rstrip("/")
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.http_user_agent}, timeout=60, follow_redirects=True
    ) as client:
        groups = (await client.get(f"{base}/85/groups")).json()["results"]
        semaphore = asyncio.Semaphore(6)

        async def products(group: dict[str, Any]) -> tuple[dict[str, Any], set[tuple[str, str]]]:
            async with semaphore:
                response = await client.get(f"{base}/85/{group['groupId']}/products")
            items = (
                response.json().get("results", []) if response.status_code == httpx.codes.OK else []
            )
            cards = {(n, key(p.get("name") or "")) for p in items if (n := number_of(p))}
            return group, cards

        tcg = await asyncio.gather(*(products(g) for g in groups))

    for code in sorted(ours):
        cards = ours[code]
        scored = sorted(
            ((len(cards & tcg_cards), group) for group, tcg_cards in tcg if tcg_cards),
            key=lambda item: -item[0],
        )[:2]
        best = " · ".join(
            f"{hits}/{len(cards)} „{g['name']}“ ({g.get('abbreviation')})" for hits, g in scored
        )
        print(f"- {code}: {best}")


asyncio.run(main())
