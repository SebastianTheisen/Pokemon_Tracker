"""Deutsche Karten, die TCGdex nicht kennt, aus dem PokéWiki ergänzen.

Quellen-Messung (``docs/phase5/quellen.md``): Zu einigen englischen Sets fehlt das deutsche
Gegenstück oder ein Teil davon – vor allem Promos (XY, SW, HGSS), Drachengruft,
McDonald's-Kollektionen. Das PokéWiki führt für jedes Set eine Kartenliste mit deutscher
Nummer und deutschem Namen (Erkundung ``docs/phase5/quellen2.md``)::

    {{Setzeile|001|Meganie|Pflanze}}

Vorgehen je englischem Set mit Lücke:

1. PokéWiki-Seite finden: feste Zuordnung (:data:`PAGE_OVERRIDES`), sonst Suche nach dem
   englischen Namen und Prüfung über ``Englisch=…`` in der Infobox bzw. den Titel.
2. Zeilen der Kartenliste den englischen Karten über die Nummer zuordnen. Passt weniger als
   die Hälfte, gilt die Seite als falsch und wird übersprungen.
3. Fehlende deutsche Karten anlegen: gleiche TCGdex-ID und Nummer wie die englische Karte
   (→ Bild und Cardmarket-Produkt gelten gemeinsam, Cardmarket führt westliche Sprachen als
   ein Produkt), deutscher Name aus dem PokéWiki, Herkunft ``pokewiki``.

Vorhandene Karten werden nie verändert. Abrufe sanft (1 s Pause), über die MediaWiki-API.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CardSource, CollectionItem
from app.services.catalog_numbers import normalize_number
from app.services.catalog_sync import fill_image_fallbacks

log = structlog.get_logger(__name__)

WIKI_API = "https://www.pokewiki.de/api.php"
PAUSE_SECONDS = 1.0
MIN_MATCH_SHARE = 0.5
_ROW = re.compile(r"\{\{\s*Setzeile\s*\|\s*([^|}]+?)\s*\|\s*([^|}]+?)\s*[|}]")
_DIGITS = re.compile(r"\d+")

# TCGdex-Set (englisch) → PokéWiki-Seite, wo die Suche nicht eindeutig ist.
PAGE_OVERRIDES: dict[str, str] = {
    "basep": "Wizards Black Star Promos (TCG)",
    "np": "Nintendo Black Star Promos (TCG)",
    "dpp": "DP Black Star Promos (TCG)",
    "hgssp": "HGSS Black Star Promos (TCG)",
    "bwp": "BW Black Star Promos (TCG)",
    "xyp": "XY Black Star Promos (TCG)",
    "smp": "SM Black Star Promos (TCG)",
    "mep": "ME Black Star Promos (TCG)",
    "dv1": "Drachengruft (TCG)",
}
_MCDONALDS = re.compile(r"^(\d{4})[a-z]+$")  # TCGdex: 2021swsh, 2023sv, …


@dataclass
class SetResult:
    set_id: str
    english_name: str
    page: str | None
    rows: int = 0
    matched: int = 0
    added: int = 0
    note: str | None = None


@dataclass
class GermanReport:
    sets: list[SetResult] = field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(result.added for result in self.sets)


def parse_rows(wikitext: str) -> list[tuple[str, str]]:
    """``(Nummer, Name)`` je Kartenzeile; doppelte Nummern (z. B. zwei Deckhälften) fallen weg."""
    rows = [(number.strip(), name.strip()) for number, name in _ROW.findall(wikitext)]
    counts = Counter(number for number, _ in rows)
    return [(number, name) for number, name in rows if counts[number] == 1 and name]


def _keys(number: str) -> tuple[str, str]:
    """Vergleichsformen: normalisiert (``XY01`` → ``XY1``) und nur Ziffern (``XY01`` → ``1``)."""
    digits = _DIGITS.findall(number)
    return normalize_number(number), str(int(digits[-1])) if digits else ""


def match_rows(rows: Sequence[tuple[str, str]], cards: Sequence[Card]) -> list[tuple[Card, str]]:
    """Kartenzeilen den englischen Karten zuordnen – erst exakt, sonst über die Ziffern."""
    exact = {card.number_norm.upper(): card for card in cards}
    digit_groups: dict[str, list[Card]] = {}
    for english in cards:
        digit_groups.setdefault(_keys(english.number)[1], []).append(english)
    matched: dict[str, tuple[Card, str]] = {}
    for number, name in rows:
        norm, digits = _keys(number)
        hit = exact.get(norm.upper())
        if hit is None and len(digit_groups.get(digits, [])) == 1:
            hit = digit_groups[digits][0]
        if hit is not None and hit.external_id and hit.external_id not in matched:
            matched[hit.external_id] = (hit, name)
    return list(matched.values())


class PokeWiki:
    """Minimaler Client der PokéWiki-API (MediaWiki), mit Pause zwischen Abrufen."""

    def __init__(self, client: httpx.AsyncClient, *, pause: float = PAUSE_SECONDS) -> None:
        self._client = client
        self._pause = pause

    async def _get(self, **params: Any) -> dict[str, Any]:
        await asyncio.sleep(self._pause)
        response = await self._client.get(
            WIKI_API, params={"format": "json", "formatversion": 2, **params}
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    async def wikitext(self, title: str) -> str | None:
        data = await self._get(action="parse", page=title, prop="wikitext", redirects=1)
        text = (data.get("parse") or {}).get("wikitext")
        return text if isinstance(text, str) else None

    async def search(self, term: str, limit: int = 5) -> list[str]:
        data = await self._get(action="query", list="search", srsearch=term, srlimit=limit)
        return [hit["title"] for hit in (data.get("query") or {}).get("search") or []]


def _plain(text: str) -> str:
    apostrophe = "\u2019"  # typografischer Apostroph im Wiki, gerader bei TCGdex
    return re.sub(r"\s+", " ", text.replace(apostrophe, "'").casefold()).strip()


def _page_fits(title: str, wikitext: str, english_name: str) -> bool:
    core = _plain(re.sub(r"\s*\(TCG\)\s*$", "", title))
    english = _plain(english_name)
    if core == english:
        return True
    declared = re.search(r"\|\s*Englisch\s*=\s*([^|\n}]+)", wikitext)
    return declared is not None and _plain(declared.group(1)) == english


async def find_page(wiki: PokeWiki, set_id: str, english_name: str) -> tuple[str, str] | None:
    """Passende PokéWiki-Seite samt Wikitext oder ``None``."""
    candidates: list[str] = []
    if set_id in PAGE_OVERRIDES:
        candidates.append(PAGE_OVERRIDES[set_id])
    elif (year := _MCDONALDS.match(set_id)) is not None:
        candidates.append(f"McDonald's Kollektion {year.group(1)} (TCG)")
    trusted = bool(candidates)
    if not trusted:
        candidates = await wiki.search(f"{english_name} (TCG)")
    for title in candidates[:5]:
        text = await wiki.wikitext(title)
        if text and (trusted or _page_fits(title, text, english_name)):
            return title, text
    return None


async def _targets(session: AsyncSession) -> list[tuple[CardSet, int, int]]:
    """Englische Sets (ohne Pocket) mit fehlendem oder kleinerem deutschem Gegenstück."""
    counts = select(Card.set_id, func.count().label("cards")).group_by(Card.set_id).subquery()
    english_sets = (
        await session.execute(
            select(CardSet, counts.c.cards)
            .join(counts, counts.c.set_id == CardSet.id)
            .where(
                CardSet.language == "en",
                CardSet.series_name.is_(None) | CardSet.series_name.not_ilike("%pocket%"),
            )
        )
    ).all()
    german = dict(
        (
            await session.execute(
                select(CardSet.external_id, func.count(Card.id))
                .outerjoin(Card, Card.set_id == CardSet.id)
                .where(CardSet.language == "de")
                .group_by(CardSet.external_id)
            )
        ).all()
    )
    return [
        (card_set, int(cards), int(german.get(card_set.external_id, 0)))
        for card_set, cards in english_sets
        if german.get(card_set.external_id, 0) < cards
    ]


async def _german_set(session: AsyncSession, english: CardSet, title: str) -> CardSet:
    existing = await session.scalar(
        select(CardSet).where(CardSet.external_id == english.external_id, CardSet.language == "de")
    )
    if existing is not None:
        return existing
    created = CardSet(
        external_id=english.external_id,
        language="de",
        name=re.sub(r"\s*\(TCG\)\s*$", "", title)[:200],
        series_name=english.series_name,
        release_date=english.release_date,
        card_count_official=english.card_count_official,
        card_count_total=english.card_count_total,
        logo_url=english.logo_url,
        symbol_url=english.symbol_url,
    )
    session.add(created)
    await session.flush()
    return created


async def import_german(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    pause: float = PAUSE_SECONDS,
) -> GermanReport:
    """Fehlende deutsche Karten aus dem PokéWiki anlegen (je Set ein Commit)."""
    report = GermanReport()
    async with session_factory() as session:
        targets = await _targets(session)
    targets.sort(key=lambda target: target[1] - target[2], reverse=True)
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.http_user_agent},
        timeout=30,
        follow_redirects=True,
        transport=transport,
    ) as client:
        wiki = PokeWiki(client, pause=pause)
        for english, _english_count, _german_count in targets[:limit]:
            result = SetResult(english.external_id, english.name, page=None)
            report.sets.append(result)
            try:
                found = await find_page(wiki, english.external_id, english.name)
            except (httpx.HTTPError, ValueError) as exc:
                result.note = f"PokéWiki: {type(exc).__name__}"
                continue
            if found is None:
                result.note = "keine PokéWiki-Seite"
                continue
            title, wikitext = found
            result.page = title
            async with session_factory() as session:
                await _apply(session, english, title, result, parse_rows(wikitext), dry_run=dry_run)
    if report.added and not dry_run:
        async with session_factory() as session:
            await fill_image_fallbacks(session)  # Bild der englischen Fassung
            await session.commit()
    log.info(
        "german_import.done",
        sets=len(report.sets),
        added=report.added,
        dry_run=dry_run,
    )
    return report


async def _apply(
    session: AsyncSession,
    english: CardSet,
    title: str,
    result: SetResult,
    rows: Sequence[tuple[str, str]],
    *,
    dry_run: bool,
) -> None:
    cards = (await session.scalars(select(Card).where(Card.set_id == english.id))).all()
    matched = match_rows(rows, cards)
    result.rows, result.matched = len(rows), len(matched)
    if not rows or len(matched) < MIN_MATCH_SHARE * len(rows):
        result.note = "Seite passt nicht zu den Nummern"
        return
    existing = set(
        (
            await session.scalars(
                select(Card.external_id).where(
                    Card.language == "de",
                    Card.external_id.in_([card.external_id for card, _ in matched]),
                )
            )
        ).all()
    )
    missing = [(card, name) for card, name in matched if card.external_id not in existing]
    result.added = len(missing)
    if dry_run or not missing:
        return
    german_set = await _german_set(session, english, title)
    session.add_all(
        Card(
            external_id=card.external_id,
            language="de",
            set_id=german_set.id,
            number=card.number,
            number_norm=card.number_norm,
            name=name[:200],
            rarity=card.rarity,
            cardmarket_product_id=card.cardmarket_product_id,
            source=CardSource.POKEWIKI,
        )
        for card, name in missing
    )
    await session.commit()


def render_report(report: GermanReport, *, dry_run: bool) -> str:
    verb = "würden angelegt" if dry_run else "angelegt"
    lines = [
        f"Deutsche Karten aus dem PokéWiki: {report.added} {verb} "
        f"({sum(1 for s in report.sets if s.added)} von {len(report.sets)} Sets)",
        "",
        f"{'Set':<12} {'Zeilen':>6} {'passend':>8} {'neu':>5}  PokéWiki-Seite / Hinweis",
    ]
    for result in report.sets:
        lines.append(
            f"{result.set_id:<12} {result.rows:>6} {result.matched:>8} {result.added:>5}  "
            f"{result.page or '–'}{f' – {result.note}' if result.note else ''}"
        )
    return "\n".join(lines)


@dataclass
class RemovalReport:
    cards_removed: int = 0
    cards_kept: int = 0  # liegen in einer Sammlung
    sets_removed: int = 0


async def remove_imported(
    session: AsyncSession, set_ids: Sequence[str], *, dry_run: bool = False
) -> RemovalReport:
    """PokéWiki-Karten dieser Sets wieder entfernen (z. B. nie auf Deutsch erschienen).

    Nur Karten mit Herkunft ``pokewiki``; Karten in Sammlungen bleiben, leere deutsche Sets
    werden gelöscht. Commit macht der Aufrufer.
    """
    report = RemovalReport()
    german_sets = select(CardSet.id).where(
        CardSet.language == "de", CardSet.external_id.in_(list(set_ids))
    )
    imported = (Card.source == CardSource.POKEWIKI) & Card.set_id.in_(german_sets)
    in_collection = exists().where(CollectionItem.card_id == Card.id)
    report.cards_kept = int(
        await session.scalar(select(func.count()).where(imported, in_collection)) or 0
    )
    report.cards_removed = int(
        await session.scalar(select(func.count()).where(imported, ~in_collection)) or 0
    )
    empty_sets = select(CardSet.id).where(
        CardSet.id.in_(german_sets), ~exists().where(Card.set_id == CardSet.id)
    )
    if dry_run:
        return report
    await session.execute(delete(Card).where(imported, ~in_collection))
    report.sets_removed = len((await session.scalars(empty_sets)).all())
    await session.execute(delete(CardSet).where(CardSet.id.in_(empty_sets)))
    return report
