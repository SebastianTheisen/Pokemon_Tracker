"""Katalog-Import aus TCGdex (Sets und Karten, alle konfigurierten Sprachen).

* Erster Lauf: alle Sets aller Sprachen. Danach inkrementell: Ein Set wird nur neu geladen,
  wenn TCGdex eine andere Kartenzahl meldet als beim letzten Import (oder bei ``full=True``).
* Abrufe laufen parallel (begrenzt), Schreiben seriell; Commit nach jedem Set, damit ein
  Abbruch den bisherigen Fortschritt nicht verliert.
* Selbst angelegte Karten (``source = user``) werden nie angefasst.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, CardSource
from app.providers.tcgdex import SetBrief, SetDetail, TcgdexClient, TcgdexError
from app.services.catalog_numbers import normalize_number

log = structlog.get_logger(__name__)


@dataclass
class LanguageReport:
    """Ergebnis je Sprache."""

    language: str
    sets_total: int = 0
    sets_synced: int = 0
    sets_skipped: int = 0
    cards_upserted: int = 0
    errors: list[str] = field(default_factory=list)


async def _stored_set_totals(session: AsyncSession, language: str) -> dict[str, int | None]:
    """Beim letzten Import von TCGdex gemeldete Kartenzahl je Set (externe ID)."""
    rows = await session.execute(
        select(CardSet.external_id, CardSet.card_count_total).where(CardSet.language == language)
    )
    return {str(row[0]): row[1] for row in rows}


def _sets_to_fetch(
    briefs: Iterable[SetBrief], stored_totals: dict[str, int | None], *, full: bool
) -> tuple[list[SetBrief], int]:
    """Welche Sets müssen geladen werden? Gibt (zu laden, übersprungen) zurück.

    Maßstab ist die von TCGdex gemeldete Kartenzahl, nicht die Zahl gespeicherter Karten:
    Bei vielen asiatischen Sets meldet TCGdex mehr Karten, als es tatsächlich liefert –
    ein Vergleich mit den gespeicherten Karten würde diese Sets bei jedem Lauf neu laden.
    """
    to_fetch: list[SetBrief] = []
    skipped = 0
    for brief in briefs:
        remote_total = brief.card_count.total
        unchanged = (
            brief.id in stored_totals
            and remote_total is not None
            and stored_totals[brief.id] == remote_total
        )
        if unchanged and not full:
            skipped += 1
        else:
            to_fetch.append(brief)
    return to_fetch, skipped


async def _store_set(session: AsyncSession, language: str, detail: SetDetail) -> int:
    """Schreibt ein Set samt Karten (Upsert). Gibt die Anzahl geschriebener Karten zurück."""
    set_values = {
        "external_id": detail.id,
        "language": language,
        "name": detail.name,
        "series_name": detail.serie.name if detail.serie else None,
        "release_date": detail.release_date,
        "card_count_official": detail.card_count.official,
        "card_count_total": detail.card_count.total,
        "logo_url": detail.logo,
        "symbol_url": detail.symbol,
        "synced_at": func.now(),
    }
    set_stmt = insert(CardSet).values(set_values)
    set_id = await session.scalar(
        set_stmt.on_conflict_do_update(
            index_elements=[CardSet.external_id, CardSet.language],
            set_={
                k: set_stmt.excluded[k] for k in set_values if k not in ("external_id", "language")
            },
        ).returning(CardSet.id)
    )

    # Doppelte IDs innerhalb einer Antwort würden den Upsert sprengen – letzte gewinnt.
    unique_cards = {card.id: card for card in detail.cards}.values()
    rows = [
        {
            "external_id": card.id,
            "language": language,
            "set_id": set_id,
            "number": card.local_id,
            "number_norm": normalize_number(card.local_id),
            "name": card.name,
            "image_url": card.image,
            "source": CardSource.TCGDEX,
        }
        for card in unique_cards
    ]
    if rows:
        card_stmt = insert(Card).values(rows)
        await session.execute(
            card_stmt.on_conflict_do_update(
                index_elements=[Card.external_id, Card.language],
                index_where=Card.external_id.is_not(None),
                set_={
                    "set_id": card_stmt.excluded.set_id,
                    "number": card_stmt.excluded.number,
                    "number_norm": card_stmt.excluded.number_norm,
                    "name": card_stmt.excluded.name,
                    "image_url": card_stmt.excluded.image_url,
                    "image_language": None,  # Ersatzbild wird nach dem Import neu gesetzt
                    "updated_at": func.now(),
                },
            )
        )
    return len(rows)


async def sync_language(
    client: TcgdexClient,
    session_factory: async_sessionmaker[AsyncSession],
    language: str,
    *,
    full: bool = False,
    concurrency: int = 4,
) -> LanguageReport:
    """Importiert bzw. aktualisiert alle Sets einer Sprache."""
    report = LanguageReport(language=language)
    try:
        briefs = await client.list_sets(language)
    except TcgdexError as exc:
        report.errors.append(str(exc))
        return report
    report.sets_total = len(briefs)

    async with session_factory() as session:
        stored_totals = await _stored_set_totals(session, language)
    to_fetch, report.sets_skipped = _sets_to_fetch(briefs, stored_totals, full=full)

    semaphore = asyncio.Semaphore(concurrency)

    async def fetch(brief: SetBrief) -> SetDetail | TcgdexError:
        async with semaphore:
            try:
                return await client.get_set(language, brief.id)
            except TcgdexError as exc:
                return exc

    for next_result in asyncio.as_completed([fetch(brief) for brief in to_fetch]):
        result = await next_result
        if isinstance(result, TcgdexError):
            report.errors.append(str(result))
            continue
        async with session_factory() as session:
            report.cards_upserted += await _store_set(session, language, result)
            await session.commit()
        report.sets_synced += 1

    log.info(
        "catalog.sync.language_done",
        language=language,
        synced=report.sets_synced,
        skipped=report.sets_skipped,
        cards=report.cards_upserted,
        errors=len(report.errors),
    )
    return report


# Bevorzugte Sprache eines Ersatzbildes: Englisch (meist vollständig), dann Deutsch, …
IMAGE_FALLBACK_ORDER = ("en", "de", "ja", "zh-tw", "ko", "zh-cn")


async def fill_image_fallbacks(session: AsyncSession) -> int:
    """Karten ohne Bild bekommen das Bild einer anderen Sprachfassung derselben Karte.

    Internationale Sets teilen sich die TCGdex-ID (``swsh7-215`` auf Deutsch und Englisch) –
    das Artwork ist gleich, nur der Kartentext ist englisch. Gibt die Anzahl zurück.
    """
    priority = " ".join(
        f"WHEN '{language}' THEN {index}" for index, language in enumerate(IMAGE_FALLBACK_ORDER)
    )
    result = await session.execute(
        text(
            f"""
            UPDATE cards AS target
            SET image_url = source.image_url, image_language = source.language
            FROM (
                SELECT DISTINCT ON (external_id) external_id, image_url, language
                FROM cards
                WHERE external_id IS NOT NULL AND image_url IS NOT NULL
                  AND image_language IS NULL
                ORDER BY external_id, CASE language {priority} ELSE 99 END
            ) AS source
            WHERE target.external_id = source.external_id
              AND target.image_url IS NULL
              AND target.source = 'tcgdex'
            """  # noqa: S608 – nur feste Sprachcodes, keine Nutzereingaben
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def sync_catalog(
    client: TcgdexClient,
    session_factory: async_sessionmaker[AsyncSession],
    languages: Iterable[str],
    *,
    full: bool = False,
    concurrency: int = 4,
) -> list[LanguageReport]:
    """Synchronisiert alle angegebenen Sprachen nacheinander, danach Ersatzbilder."""
    reports = [
        await sync_language(client, session_factory, language, full=full, concurrency=concurrency)
        for language in languages
    ]
    async with session_factory() as session:
        filled = await fill_image_fallbacks(session)
        await session.commit()
    log.info("catalog.image_fallbacks", filled=filled)
    return reports
