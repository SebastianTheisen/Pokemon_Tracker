"""Katalog-Import aus TCGdex (Sets und Karten, alle konfigurierten Sprachen).

* Erster Lauf: alle Sets aller Sprachen. Danach inkrementell: Ein Set wird nur neu geladen,
  wenn TCGdex eine andere Kartenzahl meldet als beim letzten Import (oder bei ``full=True``).
* Abrufe laufen parallel (begrenzt), Schreiben seriell; Commit nach jedem Set, damit ein
  Abbruch den bisherigen Fortschritt nicht verliert.
* Selbst angelegte Karten (``source = user``) werden nie angefasst.
* „Pokémon TCG Pocket“ (Serie ``tcgp``) ist ein reines Handyspiel ohne gedruckte Karten –
  solche Sets werden nicht importiert und vorhandene entfernt (:func:`remove_digital_sets`),
  außer Karten, die schon in einer Sammlung liegen.
* Bilder aus anderen Quellen (:mod:`app.services.image_import`) bleiben erhalten, solange
  TCGdex selbst kein Bild liefert. Ersatzbilder aus anderen Sprachfassungen werden nach
  jedem Import neu bestimmt.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import case, delete, exists, func, null, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, CardSource, CollectionItem, ImageSource
from app.providers.tcgdex import SetBrief, SetDetail, TcgdexClient, TcgdexError
from app.services.catalog_numbers import normalize_number

log = structlog.get_logger(__name__)

# TCGdex-Serien ohne gedruckte Karten (Pokémon TCG Pocket, Handyspiel).
DIGITAL_SERIES = frozenset({"tcgp"})
# Erkennung schon gespeicherter Pocket-Sets (gespeichert ist nur der Serienname).
DIGITAL_SERIES_NAME = "%pocket%"


@dataclass
class LanguageReport:
    """Ergebnis je Sprache."""

    language: str
    sets_total: int = 0
    sets_synced: int = 0
    sets_skipped: int = 0
    sets_digital: int = 0
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
        new_image = card_stmt.excluded.image_url
        # Ohne TCGdex-Bild: Bild einer anderen Quelle behalten, Ersatzbild (andere
        # Sprachfassung) verwerfen – es wird nach dem Import neu bestimmt.
        keep_other = Card.image_source.is_not(None) & (Card.image_source != ImageSource.FALLBACK)

        def image_column(column: Any, from_tcgdex: Any) -> Any:
            return case((new_image.is_not(None), from_tcgdex), (keep_other, column), else_=null())

        await session.execute(
            card_stmt.on_conflict_do_update(
                index_elements=[Card.external_id, Card.language],
                index_where=Card.external_id.is_not(None),
                set_={
                    "set_id": card_stmt.excluded.set_id,
                    "number": card_stmt.excluded.number,
                    "number_norm": card_stmt.excluded.number_norm,
                    "name": card_stmt.excluded.name,
                    "image_url": image_column(Card.image_url, new_image),
                    "image_language": image_column(Card.image_language, null()),
                    "image_source": image_column(Card.image_source, null()),
                    # Aus einer offiziellen Datenbank angelegte Karte: jetzt kennt TCGdex sie.
                    "source": card_stmt.excluded.source,
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
        if result.serie is not None and result.serie.id in DIGITAL_SERIES:
            report.sets_digital += 1  # Handyspiel – nicht importieren
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
        digital=report.sets_digital,
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
            SET image_url = source.image_url, image_language = source.language,
                image_source = 'fallback'
            FROM (
                SELECT DISTINCT ON (external_id) external_id, image_url, language
                FROM cards
                WHERE external_id IS NOT NULL AND image_url IS NOT NULL
                  AND image_language IS NULL
                ORDER BY external_id, CASE language {priority} ELSE 99 END
            ) AS source
            WHERE target.external_id = source.external_id
              AND target.image_url IS NULL
              AND target.source <> 'user'
            """  # noqa: S608 – nur feste Sprachcodes, keine Nutzereingaben
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


@dataclass
class DigitalCleanup:
    """Ergebnis von :func:`remove_digital_sets`."""

    sets: list[tuple[str, str, str]] = field(default_factory=list)  # Sprache, ID, Name
    cards_removed: int = 0
    cards_kept: int = 0  # liegen in einer Sammlung


async def remove_digital_sets(session: AsyncSession, *, dry_run: bool = False) -> DigitalCleanup:
    """Pocket-Sets samt Karten löschen; Karten in Sammlungen bleiben (mit ihrem Set).

    Commit macht der Aufrufer. ``dry_run`` zählt nur.
    """
    report = DigitalCleanup()
    digital_sets = (
        await session.execute(
            select(CardSet.id, CardSet.language, CardSet.external_id, CardSet.name)
            .where(CardSet.series_name.ilike(DIGITAL_SERIES_NAME))
            .order_by(CardSet.language, CardSet.external_id)
        )
    ).all()
    report.sets = [(row.language, row.external_id, row.name) for row in digital_sets]
    if not digital_sets:
        return report
    set_ids = [row.id for row in digital_sets]
    in_collection = exists().where(CollectionItem.card_id == Card.id)
    in_digital_set = Card.set_id.in_(set_ids)
    report.cards_kept = int(
        await session.scalar(select(func.count()).where(in_digital_set, in_collection)) or 0
    )
    report.cards_removed = int(
        await session.scalar(select(func.count()).where(in_digital_set, ~in_collection)) or 0
    )
    if dry_run:
        return report
    await session.execute(delete(Card).where(in_digital_set, ~in_collection))
    await session.execute(
        delete(CardSet).where(CardSet.id.in_(set_ids), ~exists().where(Card.set_id == CardSet.id))
    )
    log.info(
        "catalog.digital_removed",
        sets=len(report.sets),
        cards=report.cards_removed,
        kept=report.cards_kept,
    )
    return report


async def sync_catalog(
    client: TcgdexClient,
    session_factory: async_sessionmaker[AsyncSession],
    languages: Iterable[str],
    *,
    full: bool = False,
    concurrency: int = 4,
) -> list[LanguageReport]:
    """Synchronisiert alle Sprachen nacheinander, entfernt Pocket-Sets, danach Ersatzbilder."""
    reports = [
        await sync_language(client, session_factory, language, full=full, concurrency=concurrency)
        for language in languages
    ]
    async with session_factory() as session:
        await remove_digital_sets(session)
        filled = await fill_image_fallbacks(session)
        await session.commit()
    log.info("catalog.image_fallbacks", filled=filled)
    return reports
