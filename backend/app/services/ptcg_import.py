"""Englische Sets und Karten, die TCGdex (noch) nicht kennt, aus dem pokemontcg.io-Datensatz.

Quellen-Messung (``docs/phase5/quellen.md``): Der offene Datensatz auf GitHub
(``PokemonTCG/pokemon-tcg-data``) führt Sets, die bei TCGdex fehlen – etwa
„30th Celebration: Classic Collection“ (``me55c``, 30 Karten, September 2026) – und einzelne
Karten älterer Sets. Je Set gibt es eine Datei ``cards/en/<set>.json`` mit Name, Nummer,
Seltenheit, Illustrator und Bild (``images.scrydex.com``).

* Set bei uns unbekannt (weder gleiche ID noch gleicher Name) → Set und alle Karten anlegen
  (TCGdex-ID-Schema ``<set>-<nummer>`` wie im Datensatz).
* Set bekannt, aber mit weniger Karten → fehlende Karten (Nummer + Name) ergänzen.
* Vorhandene Karten werden nie verändert. Herkunft ``pokemontcg``.

Nachdruck-Sets wiederholen Nummern (``me55c``: dreimal „106“) – verglichen wird deshalb
über Nummer **und** Name.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CardSource, ImageSource
from app.services.catalog_numbers import normalize_number

log = structlog.get_logger(__name__)

DATA = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"


@dataclass
class SetChange:
    set_id: str
    name: str
    created: bool
    added: int


@dataclass
class PtcgReport:
    changes: list[SetChange] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(change.added for change in self.changes)


def set_key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()


def card_key(number: str, name: str) -> tuple[str, str]:
    return normalize_number(number), set_key(name)


def _release(value: object) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y/%m/%d").date()
    except ValueError:
        return None


async def _english_sets(session: AsyncSession) -> dict[str, tuple[CardSet, int]]:
    """Englische Sets mit Kartenzahl, auffindbar über ID und Namen."""
    counts = select(Card.set_id, func.count().label("cards")).group_by(Card.set_id).subquery()
    rows = (
        await session.execute(
            select(CardSet, func.coalesce(counts.c.cards, 0))
            .outerjoin(counts, counts.c.set_id == CardSet.id)
            .where(CardSet.language == "en")
        )
    ).all()
    found: dict[str, tuple[CardSet, int]] = {}
    for card_set, cards in rows:
        found[card_set.external_id.casefold()] = (card_set, int(cards))
        found.setdefault(f"name:{set_key(card_set.name)}", (card_set, int(cards)))
    return found


async def import_ptcg(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    dry_run: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PtcgReport:
    """Fehlende englische Sets/Karten anlegen (je Set ein Commit)."""
    report = PtcgReport()
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.http_user_agent},
        timeout=60,
        follow_redirects=True,
        transport=transport,
    ) as client:
        response = await client.get(f"{DATA}/sets/en.json")
        response.raise_for_status()
        reference: list[dict[str, Any]] = response.json()
        async with session_factory() as session:
            ours = await _english_sets(session)
        for ptcg_set in reference:
            mine = ours.get(str(ptcg_set["id"]).casefold()) or ours.get(
                f"name:{set_key(str(ptcg_set['name']))}"
            )
            total = int(ptcg_set.get("total") or 0)
            if mine is not None and mine[1] >= total:
                continue
            try:
                cards_response = await client.get(f"{DATA}/cards/en/{ptcg_set['id']}.json")
                cards_response.raise_for_status()
                cards: list[dict[str, Any]] = cards_response.json()
            except (httpx.HTTPError, ValueError) as exc:
                report.errors.append(f"{ptcg_set['id']}: {type(exc).__name__}")
                continue
            async with session_factory() as session:
                change = await _apply(
                    session, ptcg_set, cards, mine[0] if mine else None, dry_run=dry_run
                )
                if change.added:
                    report.changes.append(change)
                if not dry_run:
                    await session.commit()
    log.info("ptcg_import.done", added=report.added, sets=len(report.changes), dry_run=dry_run)
    return report


async def _apply(
    session: AsyncSession,
    ptcg_set: dict[str, Any],
    cards: list[dict[str, Any]],
    existing: CardSet | None,
    *,
    dry_run: bool,
) -> SetChange:
    card_set = existing
    if card_set is None:
        images = ptcg_set.get("images") or {}
        card_set = CardSet(
            external_id=str(ptcg_set["id"])[:64],
            language="en",
            name=str(ptcg_set.get("name") or ptcg_set["id"])[:200],
            series_name=str(ptcg_set.get("series") or "")[:200] or None,
            release_date=_release(ptcg_set.get("releaseDate")),
            card_count_official=ptcg_set.get("printedTotal"),
            card_count_total=ptcg_set.get("total"),
            logo_url=images.get("logo"),
            symbol_url=images.get("symbol"),
        )
        if not dry_run:
            session.add(card_set)
            await session.flush()
        present: set[tuple[str, str]] = set()
        used_ids: set[str] = set()
    else:
        rows = (
            await session.execute(
                select(Card.number, Card.name, Card.external_id).where(Card.set_id == card_set.id)
            )
        ).all()
        present = {card_key(row.number, row.name) for row in rows}
        used_ids = {row.external_id for row in rows if row.external_id}
    missing = [
        card
        for card in cards
        if card.get("number")
        and card_key(str(card["number"]), str(card.get("name"))) not in present
    ]
    change = SetChange(card_set.external_id, card_set.name, created=existing is None, added=0)
    for card in missing:
        # Neue Sets: ID des Datensatzes; bekannte Sets: TCGdex-Schema „<set>-<nummer>“.
        external_id = (
            str(card["id"]) if existing is None else f"{card_set.external_id}-{card['number']}"
        )[:64]
        if external_id in used_ids:
            continue  # gleiche Nummer, anderer Name – nicht raten
        used_ids.add(external_id)
        change.added += 1
        if dry_run:
            continue
        image = (card.get("images") or {}).get("large")
        session.add(
            Card(
                external_id=external_id,
                language="en",
                set_id=card_set.id,
                number=str(card["number"])[:32],
                number_norm=normalize_number(str(card["number"])),
                name=str(card.get("name") or "")[:200],
                rarity=(str(card["rarity"])[:100] if card.get("rarity") else None),
                illustrator=(str(card["artist"])[:120] if card.get("artist") else None),
                image_url=image,
                image_source=ImageSource.POKEMONTCG if image else None,
                source=CardSource.POKEMONTCG,
            )
        )
    return change


def render_report(report: PtcgReport, *, dry_run: bool) -> str:
    verb = "würden angelegt" if dry_run else "angelegt"
    lines = [f"Englische Karten aus pokemontcg.io: {report.added} {verb}"]
    lines += [
        f"  {change.set_id:<12} {'neues Set' if change.created else 'Lücken':<10} "
        f"+{change.added:<4} {change.name}"
        for change in report.changes
    ]
    lines += [f"  ! {error}" for error in report.errors]
    return "\n".join(lines)
