"""Bild-Import: fehlende Kartenbilder aus weiteren Quellen ergänzen.

Reihenfolge je Lauf (jeder Schritt füllt nur, was danach noch fehlt):

1. **pokemontcg.io** (offener Datensatz auf GitHub): englische Bilder für Englisch und
   Deutsch – fast alle westlichen Sets, auch Shiny Vault, Trainer-/Galarian-Gallery, Promos.
2. **pokemon.com**: offizielle Bilder in der *eigenen* Sprache (vor allem Deutsch). Die
   Adresse wird erraten und vor dem Speichern geprüft; ersetzt englische Ersatzbilder.
3. **Offizielle Datenbanken Japan und Taiwan**: alle Karten samt Bild. Neue Karten der
   Liste lösen einmalig einen Abruf der Detailseite aus (Nummer, Setcode). Zuordnung zur
   Katalogkarte über Setcode + Nummer, sonst Nummer + Setgröße + Name. Fehlt eine Karte im
   Katalog (z. B. japanische Promos), wird sie angelegt. Japan: auch in Sets, die TCGdex
   noch nicht kennt (Set-Code wie bei TCGdex, z. B. ``MEZ``); Taiwan nur in bekannten Sets.
4. **Ersatzbilder** aus anderen Sprachfassungen für alles, was dann noch fehlt.

Regeln für das Setzen eines Bildes (:func:`_should_replace`):

* Ein Bild von TCGdex selbst wird nie ersetzt.
* Ein Bild in der Kartensprache ersetzt ein Ersatzbild aus einer anderen Sprache.
* Ein Bild in fremder Sprache wird nur gesetzt, wenn die Karte noch gar kein Bild hat.

Bilder werden nicht kopiert, gespeichert wird nur die Adresse. Alle Server werden sanft
abgefragt (:class:`~app.providers.card_images.http.PoliteClient`).
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import BigInteger, cast, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    Card,
    CardSet,
    CardSource,
    ImageImportRun,
    ImageProbe,
    ImageSource,
    OfficialCard,
)
from app.providers.card_images import pokemon_com
from app.providers.card_images.http import PoliteClient, SourceError
from app.providers.card_images.official import OfficialDatabase, OfficialDetail
from app.providers.card_images.pokemon_card_jp import PokemonCardJp
from app.providers.card_images.pokemon_card_tw import PokemonCardTw
from app.providers.card_images.pokemontcg import PokemontcgDataset, SetRef, match_sets
from app.scanner.text import compact_key
from app.services.catalog_numbers import normalize_number
from app.services.catalog_sync import fill_image_fallbacks

log = structlog.get_logger(__name__)

ALL_SOURCES = ("pokemontcg", "pokemon.com", "jp", "tw")
WESTERN_LANGUAGES = ("en", "de")
# pokemon.com: so viele Fehlschläge zu Beginn eines Sets, dann gilt das Set als „nicht dort“.
SET_PROBE_GIVE_UP = 5
# Plausibilitätsprüfung der Detailseiten: nach so vielen Abrufen muss die Hälfte passen.
DETAIL_SANITY_SAMPLE = 20
_COMMIT_EVERY = 100
_DETAIL_CHUNK = 20
MATCH_EVERY = 2000
# Abbruch, wenn so viele Pakete in Folge ganz ohne Erfolg bleiben (Sperre hält an).
MAX_FAILED_CHUNKS = 4
MAX_ERRORS_KEPT = 20
DRY_RUN_PROBES = 40
MAX_SAMPLES = 5
_LIST_EMPTY_PAGES_TO_STOP = 2


@dataclass
class SourceReport:
    """Ergebnis einer Quelle."""

    source: str
    requests: int = 0
    images_set: int = 0
    cards_matched: int = 0
    cards_created: int = 0
    unmatched: int = 0
    listed: int = 0
    details_fetched: int = 0
    details_without_number: int = 0
    detail_errors: int = 0
    details_unparsable: int = 0
    matched_by_name: int = 0
    aborted: bool = False
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ImageImportReport:
    sources: list[SourceReport] = field(default_factory=list)
    fallbacks: int = 0
    coverage: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImageCandidate:
    """Ein gefundenes Bild für eine Karte."""

    card_id: Any
    url: str
    language: str  # Sprache des Bildes
    source: ImageSource


def _should_replace(
    *,
    card_language: str,
    image_url: str | None,
    image_language: str | None,
    image_source: str | None,
    candidate: ImageCandidate,
) -> bool:
    """Siehe Modul-Doku: Wann ersetzt ein gefundenes Bild das vorhandene?"""
    if image_url is None:
        return True
    if image_source is None:  # Bild von TCGdex
        return False
    if image_source == candidate.source:  # dieselbe Quelle: Adresse aktualisieren
        return image_url != candidate.url
    native = candidate.language == card_language
    return native and image_language is not None  # vorhandenes Bild ist ein fremdsprachiges


async def _apply(
    session: AsyncSession, candidates: Sequence[ImageCandidate], *, dry_run: bool
) -> int:
    """Setzt die Bilder, wo :func:`_should_replace` es erlaubt. Gibt die Anzahl zurück."""
    if not candidates:
        return 0
    by_card = {candidate.card_id: candidate for candidate in candidates}
    rows = await session.execute(
        select(
            Card.id, Card.language, Card.image_url, Card.image_language, Card.image_source
        ).where(Card.id.in_(list(by_card)))
    )
    updates: list[dict[str, Any]] = []
    for card_id, language, image_url, image_language, image_source in rows:
        candidate = by_card[card_id]
        if _should_replace(
            card_language=language,
            image_url=image_url,
            image_language=image_language,
            image_source=image_source,
            candidate=candidate,
        ):
            updates.append(
                {
                    "id": card_id,
                    "image_url": candidate.url,
                    "image_language": (
                        None if candidate.language == language else candidate.language
                    ),
                    "image_source": candidate.source.value,
                }
            )
    if updates and not dry_run:
        await session.execute(update(Card), updates)
    return len(updates)


def _missing_native_image() -> Any:
    """Karten ohne Bild in eigener Sprache (kein Bild oder nur ein Ersatzbild)."""
    return (Card.image_url.is_(None) | Card.image_language.is_not(None)) & (
        Card.source != CardSource.USER
    )


# --------------------------------------------------------------------------- pokemontcg.io


async def import_pokemontcg(
    session_factory: async_sessionmaker[AsyncSession],
    dataset: PokemontcgDataset,
    *,
    dry_run: bool = False,
) -> SourceReport:
    """Englische Bilder aus dem pokemontcg.io-Datensatz für EN- und DE-Karten."""
    report = SourceReport(source=ImageSource.POKEMONTCG.value)
    async with session_factory() as session:
        set_rows = await session.execute(
            select(CardSet.external_id, CardSet.language, CardSet.name).where(
                CardSet.language.in_(WESTERN_LANGUAGES)
            )
        )
        english_names: dict[str, str | None] = {}
        for external_id, language, name in set_rows:
            if language == "en" or external_id not in english_names:
                english_names[external_id] = name if language == "en" else None
        needed = await session.execute(
            select(Card.id, Card.number, CardSet.external_id)
            .join(CardSet, Card.set_id == CardSet.id)
            .where(Card.language.in_(WESTERN_LANGUAGES), _missing_native_image())
        )
        by_set: defaultdict[str, list[tuple[Any, str]]] = defaultdict(list)
        for card_id, number, set_external_id in needed:
            by_set[set_external_id].append((card_id, number))
    if not by_set:
        report.notes.append("Keine Karte ohne Bild.")
        return report

    try:
        their_sets = await dataset.sets()
        report.requests += 1
    except SourceError as exc:
        report.errors.append(str(exc))
        return report
    mapping = match_sets(
        (SetRef(external_id, name) for external_id, name in english_names.items()), their_sets
    )
    unmapped = sorted(set_id for set_id in by_set if set_id not in mapping)
    if unmapped:
        report.notes.append(f"Ohne pokemontcg.io-Set: {', '.join(unmapped[:40])}")

    for set_external_id, cards in sorted(by_set.items()):
        their_id = mapping.get(set_external_id)
        if their_id is None:
            report.unmatched += len(cards)
            continue
        try:
            their_cards = await dataset.cards(their_id)
            report.requests += 1
        except SourceError as exc:
            report.errors.append(str(exc))
            continue
        images = {
            normalize_number(card.number): card.image_url for card in their_cards if card.image_url
        }
        candidates: list[ImageCandidate] = []
        for card_id, number in cards:
            url = images.get(normalize_number(number))
            if url is None:
                report.unmatched += 1
                continue
            candidates.append(ImageCandidate(card_id, url, "en", ImageSource.POKEMONTCG))
        report.cards_matched += len(candidates)
        async with session_factory() as session:
            report.images_set += await _apply(session, candidates, dry_run=dry_run)
            await session.commit()
    return report


# --------------------------------------------------------------------------- pokemon.com


async def probe_pokemon_com(
    session_factory: async_sessionmaker[AsyncSession],
    client: PoliteClient,
    *,
    retry_after: timedelta,
    max_probes: int,
    dry_run: bool = False,
) -> SourceReport:
    """Offizielle DE/EN-Bilder von pokemon.com für Karten ohne Bild in eigener Sprache."""
    report = SourceReport(source=ImageSource.POKEMON_COM.value)
    source = ImageSource.POKEMON_COM.value
    since = datetime.now(UTC) - retry_after
    async with session_factory() as session:
        recent = (
            select(ImageProbe.card_id)
            .where(ImageProbe.source == source, ImageProbe.checked_at >= since)
            .scalar_subquery()
        )
        rows = (
            await session.execute(
                select(Card.id, Card.language, Card.number, Card.number_norm, CardSet.external_id)
                .join(CardSet, Card.set_id == CardSet.id)
                .where(
                    Card.language.in_(WESTERN_LANGUAGES),
                    _missing_native_image(),
                    Card.id.not_in(recent),
                )
                .order_by(CardSet.external_id, Card.language, Card.number_norm)
            )
        ).all()
        # Sets, in denen es zuletzt nur Fehlschläge gab, gar nicht erst versuchen.
        hopeless = await _hopeless_sets(session, since)

    groups: defaultdict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in rows:
        groups[(row.external_id, row.language)].append(row)
    skipped_sets = 0
    probes = 0
    for (set_external_id, language), cards in groups.items():
        if (set_external_id, language) in hopeless:
            skipped_sets += 1
            continue
        found_any = False
        failures = 0
        results: list[tuple[Any, str, bool]] = []
        for row in cards:
            if probes >= max_probes:
                break
            url = pokemon_com.official_image_url(set_external_id, row.number, language)
            if url is None:
                continue
            try:
                exists = await client.image_exists(url)
            except SourceError as exc:
                report.errors.append(str(exc))
                if len(report.errors) >= SET_PROBE_GIVE_UP:
                    report.notes.append("Abbruch: pokemon.com antwortet nicht zuverlässig.")
                    await _store_probes(session_factory, results, dry_run=dry_run, report=report)
                    report.requests = probes
                    return report
                continue
            probes += 1
            results.append((row.id, url, exists))
            found_any = found_any or exists
            failures = 0 if exists else failures + 1
            if not found_any and failures >= SET_PROBE_GIVE_UP:
                break  # Set gibt es dort (in dieser Sprache) offenbar nicht
        await _store_probes(session_factory, results, dry_run=dry_run, report=report)
        if probes >= max_probes:
            report.notes.append(f"Grenze von {max_probes} Prüfungen erreicht, Rest folgt.")
            break
    report.requests = probes
    if skipped_sets:
        report.notes.append(f"{skipped_sets} Sets übersprungen (zuletzt kein Bild gefunden).")
    return report


async def _hopeless_sets(session: AsyncSession, since: datetime) -> set[tuple[str, str]]:
    rows = await session.execute(
        select(CardSet.external_id, Card.language)
        .join(Card, Card.set_id == CardSet.id)
        .join(ImageProbe, ImageProbe.card_id == Card.id)
        .where(ImageProbe.source == ImageSource.POKEMON_COM.value, ImageProbe.checked_at >= since)
        .group_by(CardSet.external_id, Card.language)
        .having(
            func.count().filter(ImageProbe.found.is_(True)) == 0,
            func.count() >= SET_PROBE_GIVE_UP,
        )
    )
    return {(external_id, language) for external_id, language in rows}


async def _store_probes(
    session_factory: async_sessionmaker[AsyncSession],
    results: Sequence[tuple[Any, str, bool]],
    *,
    dry_run: bool,
    report: SourceReport,
) -> None:
    if not results:
        return
    async with session_factory() as session:
        candidates: list[ImageCandidate] = []
        language_rows = await session.execute(
            select(Card.id, Card.language).where(Card.id.in_([r[0] for r in results]))
        )
        languages = {row.id: row.language for row in language_rows}
        for card_id, url, exists in results:
            if exists:
                candidates.append(
                    ImageCandidate(card_id, url, languages[card_id], ImageSource.POKEMON_COM)
                )
        report.cards_matched += len(candidates)
        report.images_set += await _apply(session, candidates, dry_run=dry_run)
        free = MAX_SAMPLES - len(report.samples)
        report.samples.extend({"url": url, "found": found} for _, url, found in results[:free])
        if not dry_run:
            statement = insert(ImageProbe).values(
                [
                    {
                        "card_id": card_id,
                        "source": ImageSource.POKEMON_COM.value,
                        "url": url,
                        "found": exists,
                    }
                    for card_id, url, exists in results
                ]
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[ImageProbe.card_id, ImageProbe.source],
                    set_={
                        "url": statement.excluded.url,
                        "found": statement.excluded.found,
                        "checked_at": func.now(),
                    },
                )
            )
        await session.commit()


# --------------------------------------------------------------------------- Japan / Taiwan


def set_code_key(code: str) -> str:
    """Vergleichbarer Setcode: ``SV-P`` = ``svp``, ``M6a`` = ``m6a``."""
    return code.casefold().replace("-", "")


@dataclass(frozen=True)
class _CatalogCard:
    id: Any
    name: str
    number_norm: str
    set_key: str
    set_total: int | None


class _CatalogIndex:
    """Katalogkarten einer Sprache, auffindbar über Setcode + Nummer bzw. Nummer + Größe."""

    def __init__(self, cards: Iterable[_CatalogCard], set_ids: dict[str, Any]) -> None:
        self.by_set_number: dict[tuple[str, str], _CatalogCard] = {}
        self.by_number: defaultdict[str, list[_CatalogCard]] = defaultdict(list)
        for card in cards:
            self.by_set_number.setdefault((card.set_key, card.number_norm), card)
            self.by_number[card.number_norm].append(card)
        self.set_ids = set_ids  # Setcode-Schlüssel → CardSet.id

    def find(self, set_code: str | None, number: str, name: str) -> _CatalogCard | None:
        head, _, tail = number.partition("/")
        number_norm = normalize_number(head)
        if set_code:
            hit = self.by_set_number.get((set_code_key(set_code), number_norm))
            if hit is not None:
                return hit
        if tail and not set_code:
            # Promo-Kürzel hinter dem Schrägstrich („132/M-P“) ist der Setcode.
            hit = self.by_set_number.get((set_code_key(tail), number_norm))
            if hit is not None:
                return hit
        # Ohne (passenden) Setcode: gleiche Nummer, gleiche Setgröße und gleicher Name.
        total = int(tail) if tail.isdigit() else None
        wanted = compact_key(name)
        matches = [
            card
            for card in self.by_number.get(number_norm, [])
            if total is not None and card.set_total == total and compact_key(card.name) == wanted
        ]
        return matches[0] if len(matches) == 1 else None


async def _catalog_index(session: AsyncSession, language: str) -> _CatalogIndex:
    rows = await session.execute(
        select(
            Card.id,
            Card.name,
            Card.number_norm,
            CardSet.external_id,
            CardSet.card_count_official,
        )
        .join(CardSet, Card.set_id == CardSet.id)
        .where(Card.language == language, Card.source != CardSource.USER)
    )
    cards = [
        _CatalogCard(row.id, row.name, row.number_norm, set_code_key(row.external_id), row[4])
        for row in rows
    ]
    set_rows = await session.execute(
        select(CardSet.id, CardSet.external_id).where(CardSet.language == language)
    )
    set_ids = {set_code_key(external_id): set_id for set_id, external_id in set_rows}
    return _CatalogIndex(cards, set_ids)


async def import_official(
    session_factory: async_sessionmaker[AsyncSession],
    database: OfficialDatabase,
    *,
    max_pages: int | None = None,
    max_details: int | None = None,
    concurrency: int = 4,
    dry_run: bool = False,
) -> SourceReport:
    """Liste lesen, neue Detailseiten abrufen, Karten zuordnen und Bilder setzen."""
    report = SourceReport(source=database.source)
    if dry_run:
        return await _official_dry_run(database, report, max_pages or 1, max_details or 5)
    await _read_listing(session_factory, database, report, max_pages=max_pages)
    # Schnellweg: Karten, deren Name im Set eindeutig ist, brauchen keine Detailseite.
    await _match_by_name(session_factory, database, report)

    async def match_so_far() -> None:
        # Zwischendurch zuordnen, damit Bilder nicht erst am Ende des Laufs erscheinen.
        interim = SourceReport(source=database.source)
        await _match_official(session_factory, database, interim)
        report.images_set += interim.images_set

    if not report.errors or report.listed:
        await _fetch_details(
            session_factory,
            database,
            report,
            max_details=max_details,
            concurrency=concurrency,
            on_progress=match_so_far,
        )
    await _match_official(session_factory, database, report)
    return report


async def _read_listing(
    session_factory: async_sessionmaker[AsyncSession],
    database: OfficialDatabase,
    report: SourceReport,
    *,
    max_pages: int | None,
) -> None:
    """Alle Listenseiten lesen und neue Karten bzw. geänderte Bilder speichern."""
    page = 1
    seen: set[str] = set()
    empty_pages = 0
    failures_in_row = 0
    while max_pages is None or page <= max_pages:
        try:
            listing = await database.list_page(page)
            report.requests += 1
            failures_in_row = 0
        except SourceError as exc:
            failures_in_row += 1
            if len(report.errors) < MAX_ERRORS_KEPT:
                report.errors.append(f"Liste Seite {page}: {exc}")
            log.warning(
                "image_import.list_failed", source=database.source, page=page, error=str(exc)
            )
            if failures_in_row >= SET_PROBE_GIVE_UP:
                report.notes.append(f"Liste ab Seite {page} abgebrochen (Fehler in Folge).")
                return
            page += 1
            continue
        if page % 50 == 0:
            log.info("image_import.list_progress", source=database.source, page=page)
        fresh = [entry for entry in listing.entries if entry.official_id not in seen]
        if not fresh:
            empty_pages += 1
            if listing.max_page is None and empty_pages >= _LIST_EMPTY_PAGES_TO_STOP:
                break
        else:
            empty_pages = 0
        seen.update(entry.official_id for entry in fresh)
        report.listed += len(fresh)
        if fresh:
            statement = insert(OfficialCard).values(
                [
                    {
                        "source": database.source,
                        "official_id": entry.official_id,
                        "language": database.language,
                        "name": entry.name,
                        "image_url": entry.image_url,
                        "set_code": entry.set_code,
                    }
                    for entry in fresh
                ]
            )
            async with session_factory() as session:
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[OfficialCard.source, OfficialCard.official_id],
                        set_={"image_url": statement.excluded.image_url},
                    )
                )
                await session.commit()
        if listing.max_page is not None and page >= listing.max_page:
            break
        page += 1


async def _fetch_details(
    session_factory: async_sessionmaker[AsyncSession],
    database: OfficialDatabase,
    report: SourceReport,
    *,
    max_details: int | None,
    concurrency: int = 4,
    on_progress: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Detailseiten der Karten, deren Nummer noch fehlt (einmalig je Karte).

    Karten, die der Schnellweg (:func:`_match_by_name`) schon zugeordnet hat, werden
    übersprungen. Alle ``MATCH_EVERY`` Seiten wird ``on_progress`` aufgerufen.
    """
    async with session_factory() as session:
        query = (
            select(OfficialCard.id, OfficialCard.official_id)
            .where(
                OfficialCard.source == database.source,
                OfficialCard.detail_fetched_at.is_(None),
                OfficialCard.card_id.is_(None),
            )
            # Neueste Karten zuerst (höchste ID) – als Zahl sortiert, nicht als Text.
            .order_by(cast(OfficialCard.official_id, BigInteger).desc())
        )
        if max_details is not None:
            query = query.limit(max_details)
        pending = (await session.execute(query)).all()

    # Mehrere Seiten gleichzeitig unterwegs, gestartet wird trotzdem höchstens eine pro
    # Intervall (PoliteClient) – so bremst eine langsame Antwort nicht den ganzen Lauf.
    semaphore = asyncio.Semaphore(concurrency)
    failed_chunks = 0

    async def fetch(official_id: str) -> OfficialDetail | SourceError:
        async with semaphore:
            try:
                detail, _ = await database.detail(official_id)
            except SourceError as exc:
                return exc
            return detail

    batch: list[tuple[Any, OfficialDetail]] = []
    chunk_size = max(_DETAIL_CHUNK, concurrency * 4)
    for offset in range(0, len(pending), chunk_size):
        chunk = pending[offset : offset + chunk_size]
        results = await asyncio.gather(*(fetch(official_id) for _, official_id in chunk))
        for (row_id, official_id), result in zip(chunk, results, strict=True):
            report.requests += 1
            if isinstance(result, SourceError):
                report.detail_errors += 1
                if len(report.errors) < MAX_ERRORS_KEPT:
                    report.errors.append(f"Detail {official_id}: {result}")
                    log.warning(
                        "image_import.detail_failed", source=database.source, error=str(result)
                    )
                continue
            report.details_fetched += 1
            if result.number is None:
                report.details_without_number += 1
                if result.name is None:
                    report.details_unparsable += 1
            if len(report.samples) < MAX_SAMPLES:
                report.samples.append({"id": official_id, **asdict(result)})
            batch.append((row_id, result))
        # Alte Karten haben teils keine Nummer – das ist normal. Fehlen aber Name *und*
        # Nummer bei der Mehrheit, hat sich der Seitenaufbau geändert.
        if (
            report.details_fetched >= DETAIL_SANITY_SAMPLE
            and report.details_unparsable > report.details_fetched // 2
        ):
            report.errors.append(
                "Detailseiten liefern keine Kartennummer – Seitenaufbau geändert? "
                "Abbruch, damit nichts Falsches gespeichert wird."
            )
            log.error("image_import.details_unparsable", source=database.source)
            return  # nichts speichern: die Zeilen bleiben „nicht abgerufen“
        succeeded = any(not isinstance(result, SourceError) for result in results)
        failed_chunks = 0 if succeeded else failed_chunks + 1
        if failed_chunks >= MAX_FAILED_CHUNKS:
            report.aborted = True
            report.notes.append(
                "Abbruch: Server lehnt weiter ab – neuer Versuch in einigen Stunden."
            )
            log.error("image_import.details_aborted", source=database.source)
            break
        if len(batch) >= _COMMIT_EVERY:
            await _store_details(session_factory, batch)
            batch = []
            if on_progress is not None and report.details_fetched % MATCH_EVERY < chunk_size:
                await on_progress()
            log.info(
                "image_import.details_progress",
                source=database.source,
                fetched=report.details_fetched,
                pending=len(pending),
                errors=report.detail_errors,
            )
    await _store_details(session_factory, batch)


async def _store_details(
    session_factory: async_sessionmaker[AsyncSession],
    batch: Sequence[tuple[Any, OfficialDetail]],
) -> None:
    if not batch:
        return
    now = datetime.now(UTC)
    async with session_factory() as session:
        for row_id, detail in batch:
            values: dict[str, Any] = {"number": detail.number, "detail_fetched_at": now}
            if detail.set_code:
                values["set_code"] = detail.set_code
            if detail.name:
                values["name"] = detail.name
            if detail.image_url:
                values["image_url"] = detail.image_url
            await session.execute(
                update(OfficialCard).where(OfficialCard.id == row_id).values(**values)
            )
        await session.commit()


async def _match_official(
    session_factory: async_sessionmaker[AsyncSession],
    database: OfficialDatabase,
    report: SourceReport,
) -> None:
    """Ordnet alle Einträge mit Nummer einer Katalogkarte zu (legt fehlende an)."""
    source = ImageSource(database.source)
    async with session_factory() as session:
        index = await _catalog_index(session, database.language)
        records = (
            (
                await session.execute(
                    select(OfficialCard).where(
                        OfficialCard.source == database.source, OfficialCard.number.is_not(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        candidates: list[ImageCandidate] = []
        unknown_sets: defaultdict[str, int] = defaultdict(int)
        for record in records:
            number = record.number or ""
            hit = index.find(record.set_code, number, record.name)
            if hit is None:
                hit = await _create_card(session, index, record, database.language)
                if hit is None:
                    report.unmatched += 1
                    unknown_sets[record.set_code or "?"] += 1
                    continue
                report.cards_created += 1
            else:
                report.cards_matched += 1
            if record.card_id != hit.id:
                record.card_id = hit.id
            candidates.append(ImageCandidate(hit.id, record.image_url, database.language, source))
            if len(candidates) >= _COMMIT_EVERY:
                report.images_set += await _apply(session, candidates, dry_run=False)
                candidates = []
        report.images_set += await _apply(session, candidates, dry_run=False)
        await session.commit()
    if unknown_sets:
        top = sorted(unknown_sets.items(), key=lambda item: -item[1])[:25]
        report.notes.append(
            "Nicht zugeordnet (Setcode: Anzahl): " + ", ".join(f"{k}: {v}" for k, v in top)
        )


async def _match_by_name(
    session_factory: async_sessionmaker[AsyncSession],
    database: OfficialDatabase,
    report: SourceReport,
) -> None:
    """Zuordnung ohne Detailseite: Setcode (aus der Liste) + im Set eindeutiger Name.

    Nur wenn im Katalog *und* in der offiziellen Liste genau eine Karte dieses Namens im
    Set steht – bei mehreren Fassungen (z. B. normale und Sonder-Seltenheit) entscheidet
    später die Nummer von der Detailseite.
    """
    source = ImageSource(database.source)
    async with session_factory() as session:
        index = await _catalog_index(session, database.language)
        catalog: defaultdict[tuple[str, str], list[_CatalogCard]] = defaultdict(list)
        for cards in index.by_number.values():
            for card in cards:
                catalog[(card.set_key, compact_key(card.name))].append(card)
        records = (
            (
                await session.execute(
                    select(OfficialCard).where(
                        OfficialCard.source == database.source,
                        OfficialCard.card_id.is_(None),
                        OfficialCard.set_code.is_not(None),
                        OfficialCard.name != "",
                    )
                )
            )
            .scalars()
            .all()
        )
        listed: defaultdict[tuple[str, str], list[OfficialCard]] = defaultdict(list)
        for record in records:
            listed[(set_code_key(record.set_code or ""), compact_key(record.name))].append(record)
        candidates: list[ImageCandidate] = []
        for key, group in listed.items():
            matches = catalog.get(key, [])
            if len(group) != 1 or len(matches) != 1:
                continue
            group[0].card_id = matches[0].id
            candidates.append(
                ImageCandidate(matches[0].id, group[0].image_url, database.language, source)
            )
        report.matched_by_name = len(candidates)
        for start in range(0, len(candidates), _COMMIT_EVERY):
            report.images_set += await _apply(
                session, candidates[start : start + _COMMIT_EVERY], dry_run=False
            )
        await session.commit()
    log.info("image_import.matched_by_name", source=database.source, matched=report.matched_by_name)


async def _create_card(
    session: AsyncSession, index: _CatalogIndex, record: OfficialCard, language: str
) -> _CatalogCard | None:
    """Legt eine fehlende Karte an – in bekannten Sets, für Japan auch in neuen Sets.

    Die externe ID folgt dem Schema von TCGdex (``M6a-001``). Kennt TCGdex die Karte später,
    überschreibt der nächste Katalog-Import genau diese Zeile, statt eine doppelte anzulegen.
    """
    head, _, tail = (record.number or "").partition("/")
    set_code = record.set_code or (tail if tail and not tail.isdigit() else None)
    if not head or not set_code:
        return None
    set_key = set_code_key(set_code)
    set_id = index.set_ids.get(set_key)
    if set_id is None:
        set_id = await _create_set(session, index, set_code, language)
    if set_id is None:
        return None
    card_set = await session.get(CardSet, set_id)
    if card_set is None:
        return None
    number_norm = normalize_number(head)
    external_id = f"{card_set.external_id}-{head}"
    statement = (
        insert(Card)
        .values(
            external_id=external_id,
            language=language,
            set_id=set_id,
            number=head,
            number_norm=number_norm,
            name=record.name,
            source=CardSource.OFFICIAL,
        )
        .on_conflict_do_nothing(
            index_elements=[Card.external_id, Card.language],
            index_where=Card.external_id.is_not(None),
        )
        .returning(Card.id)
    )
    card_id = await session.scalar(statement)
    if card_id is None:  # gab es schon (z. B. doppelter Eintrag in der Datenbank)
        card_id = await session.scalar(
            select(Card.id).where(Card.external_id == external_id, Card.language == language)
        )
    if card_id is None:
        return None
    created = _CatalogCard(card_id, record.name, number_norm, set_key, None)
    index.by_set_number[(set_key, number_norm)] = created
    return created


# Japan: Set-Code im Bildpfad = Set-ID bei TCGdex (``M6a``, ``SV2a``). Taiwan liest den Code
# aus einem Markenbild – ob er zu TCGdex passt, ist offen, deshalb dort keine neuen Sets.
NEW_SET_LANGUAGES = frozenset({"ja", "zh-tw"})
_SET_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,15}$")


async def _create_set(
    session: AsyncSession, index: _CatalogIndex, set_code: str, language: str
) -> Any:
    """Neues Set aus der offiziellen Datenbank, bis TCGdex es kennt.

    Name und Erscheinungsdatum vom japanischen Set mit demselben Code (Taiwan übernimmt die
    japanischen Codes, z. B. „SV11B“, „M2a“), sonst der Code selbst.
    """
    if language not in NEW_SET_LANGUAGES or not _SET_CODE.match(set_code):
        return None
    japanese = None
    if language != "ja":
        japanese = (
            await session.execute(
                select(CardSet.name, CardSet.release_date)
                .where(
                    CardSet.language == "ja",
                    func.lower(CardSet.external_id) == set_code.casefold(),
                )
                .limit(1)
            )
        ).first()
    statement = (
        insert(CardSet)
        .values(
            external_id=set_code,
            language=language,
            name=japanese.name if japanese else set_code,
            release_date=japanese.release_date if japanese else None,
            series_name="Offizielle Datenbank",
        )
        .on_conflict_do_nothing(index_elements=[CardSet.external_id, CardSet.language])
        .returning(CardSet.id)
    )
    set_id = await session.scalar(statement)
    if set_id is None:
        set_id = await session.scalar(
            select(CardSet.id).where(CardSet.external_id == set_code, CardSet.language == language)
        )
    if set_id is not None:
        index.set_ids[set_code_key(set_code)] = set_id
    return set_id


async def _official_dry_run(
    database: OfficialDatabase, report: SourceReport, max_pages: int, max_details: int
) -> SourceReport:
    """Probe ohne Speichern: Liste und einige Detailseiten lesen, Ergebnis berichten."""
    entries = []
    for page in range(1, max_pages + 1):
        try:
            listing = await database.list_page(page)
            report.requests += 1
        except SourceError as exc:
            report.errors.append(f"Liste Seite {page}: {exc}")
            return report
        entries.extend(listing.entries)
        if page == 1:
            report.notes.append(f"Seiten laut Quelle: {listing.max_page or 'unbekannt'}")
    report.listed = len(entries)
    for entry in entries[:max_details]:
        try:
            detail, html = await database.detail(entry.official_id)
            report.requests += 1
        except SourceError as exc:
            report.errors.append(f"Detail {entry.official_id}: {exc}")
            continue
        report.details_fetched += 1
        if detail.number is None:
            report.details_without_number += 1
        report.samples.append({"entry": asdict(entry), "detail": asdict(detail)})
        if report.details_fetched == 1:
            report.notes.append(f"HTML-Ausschnitt: {_html_excerpt(html)}")
    return report


def _html_excerpt(html: str, size: int = 4000) -> str:
    """Der interessante Teil einer Detailseite (ab der Überschrift) für die Diagnose."""
    start = html.find("<h1")
    start = max(start - 500, 0) if start >= 0 else 0
    return " ".join(html[start : start + size].split())


# --------------------------------------------------------------------------- Lauf


async def catalog_coverage(session: AsyncSession) -> dict[str, str]:
    """Bilder je Sprache: „mit Bild / gesamt (davon eigene Sprache)“."""
    rows = await session.execute(
        select(
            Card.language,
            func.count(),
            func.count(Card.image_url),
            func.count(Card.image_url).filter(Card.image_language.is_(None)),
        )
        .group_by(Card.language)
        .order_by(Card.language)
    )
    return {
        language: f"{with_image}/{total} (eigene Sprache {native})"
        for language, total, with_image, native in rows
    }


async def last_finished_run(session: AsyncSession) -> datetime | None:
    return await session.scalar(select(func.max(ImageImportRun.finished_at)))


async def last_run_incomplete(session: AsyncSession) -> bool:
    """Hat im letzten fertigen Lauf eine Quelle abgebrochen (z. B. wegen Sperre)?"""
    report = await session.scalar(
        select(ImageImportRun.report)
        .where(ImageImportRun.finished_at.is_not(None))
        .order_by(ImageImportRun.finished_at.desc())
        .limit(1)
    )
    sources = report.get("sources", []) if isinstance(report, dict) else []
    return any(isinstance(item, dict) and item.get("aborted") for item in sources)


async def run_image_import(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    sources: Sequence[str] = ALL_SOURCES,
    max_pages: int | None = None,
    max_details: int | None = None,
    dry_run: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ImageImportReport:
    """Ein kompletter Lauf über die gewählten Quellen; Protokoll in ``image_import_runs``.

    Die Quellen laufen parallel, weil sie verschiedene Server betreffen – die Anfragen an
    *einen* Server bleiben dabei sanft getaktet.
    """
    report = ImageImportReport(dry_run=dry_run)
    run_id = None
    if not dry_run:
        async with session_factory() as session:
            run = ImageImportRun(report={"status": "läuft", "sources": list(sources)})
            session.add(run)
            await session.commit()
            run_id = run.id

    async with PoliteClient(
        user_agent=settings.image_import_user_agent,
        min_interval=settings.image_import_request_interval_seconds,
        start_intervals=settings.image_import_start_intervals,
        transport=transport,
    ) as client:
        western: list[SourceReport] = []
        if "pokemontcg" in sources:  # zuerst: macht viele pokemon.com-Prüfungen überflüssig
            dataset = PokemontcgDataset(client, settings.pokemontcg_data_url)
            western.append(await import_pokemontcg(session_factory, dataset, dry_run=dry_run))

        tasks = []
        if "pokemon.com" in sources:
            tasks.append(
                probe_pokemon_com(
                    session_factory,
                    client,
                    retry_after=timedelta(days=settings.image_probe_retry_days),
                    max_probes=DRY_RUN_PROBES if dry_run else settings.image_probe_max_per_run,
                    dry_run=dry_run,
                )
            )
        databases: list[OfficialDatabase] = []
        if "jp" in sources:
            databases.append(PokemonCardJp(client))
        if "tw" in sources:
            databases.append(PokemonCardTw(client))
        tasks.extend(
            import_official(
                session_factory,
                database,
                max_pages=max_pages,
                max_details=max_details,
                concurrency=settings.image_import_host_concurrency.get(
                    database.host, settings.image_import_concurrency
                ),
                dry_run=dry_run,
            )
            for database in databases
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)
    report.sources = western
    for result in results:
        if isinstance(result, BaseException):
            log.error("image_import.source_failed", error=repr(result), exc_info=result)
            report.sources.append(SourceReport(source="?", errors=[repr(result)]))
        else:
            report.sources.append(result)

    async with session_factory() as session:
        if not dry_run:
            report.fallbacks = await fill_image_fallbacks(session)
            await session.commit()
        report.coverage = await catalog_coverage(session)
        if run_id is not None:
            stored = await session.get(ImageImportRun, run_id)
            if stored is not None:
                stored.finished_at = datetime.now(UTC)
                stored.report = report.as_dict()
                await session.commit()
    log.info(
        "image_import.done",
        dry_run=dry_run,
        images={item.source: item.images_set for item in report.sources},
        fallbacks=report.fallbacks,
    )
    return report


def render_report(report: ImageImportReport) -> str:
    """Bericht als Markdown (für die Kommandozeile und ``docs/``)."""
    title = "Bild-Import (Probelauf, nichts gespeichert)" if report.dry_run else "Bild-Import"
    lines = [f"# {title}", ""]
    lines += [
        "| Quelle | Anfragen | zugeordnet | Bilder gesetzt | angelegt | ohne Treffer | Fehler |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report.sources:
        lines.append(
            f"| {item.source} | {item.requests} | {item.cards_matched} | {item.images_set} "
            f"| {item.cards_created} | {item.unmatched} | {len(item.errors)} |"
        )
    lines.append("")
    for item in report.sources:
        details = item.notes + [f"Fehler: {error}" for error in item.errors[:8]]
        if item.listed or item.details_fetched:
            details.insert(
                0,
                f"Liste: {item.listed} Karten, Detailseiten: {item.details_fetched} "
                f"(ohne Nummer: {item.details_without_number})",
            )
        if not details and not item.samples:
            continue
        lines += [f"## {item.source}", ""]
        lines += [f"- {detail}" for detail in details]
        lines += [f"- Beispiel: `{sample}`" for sample in item.samples[:MAX_SAMPLES]]
        lines.append("")
    if not report.dry_run:
        lines += [f"Ersatzbilder aus anderen Sprachfassungen: {report.fallbacks}", ""]
    lines += ["## Abdeckung (mit Bild / gesamt)", ""]
    lines += [f"- {language}: {value}" for language, value in report.coverage.items()]
    return "\n".join(lines) + "\n"
