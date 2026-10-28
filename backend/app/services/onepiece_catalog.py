"""One-Piece-Katalog aus den offiziellen Kartenlisten und Verknüpfung mit Cardmarket.

Quelle (Spike ``docs/phase5/onepiece.md``): ``https://en.onepiece-cardgame.com/cardlist/``
(Englisch) und ``https://www.onepiece-cardgame.com/cardlist/`` (Japanisch). Die Seite listet
die Sets in ``<select id="series">``; ``/cardlist/?series=<ID>`` liefert alle Karten eines
Sets serverseitig gerendert als ``<dl class="modalCol" id="OP01-001_p1">`` mit

* ``dt .infoCol span`` – Kartennummer | Seltenheit | Kategorie (LEADER, CHARACTER, …),
* ``dt .cardName`` – Name,
* Bild unter ``/images/cardlist/card/<ID>.png``.

Die ID trägt die Fassung: ohne Zusatz die normale Karte, ``_p1``/``_p2`` Parallel-Fassungen
(Alternate Art), ``_r1`` Nachdrucke. Jede Fassung wird eine eigene Karte (wie bei
Cardmarket ein eigenes Produkt). Ein Abruf je Set, mit Pause dazwischen – rund 60 Sets je
Sprache.

**Cardmarket:** Produktnamen enthalten die Kartennummer („Roronoa Zoro (OP01-001)“). Ein
Set gehört zu der Ausgabe, die die meisten seiner Nummern enthält; innerhalb der Ausgabe
werden gleiche Nummern in Produkt-ID-Reihenfolge den Fassungen zugeordnet (normal, dann
Parallel 1, 2, …) – aber nur, wenn die Anzahl übereinstimmt. Sonst bekommt nur die normale
Karte das erste Produkt; die übrigen wählt man in der App selbst („Ausgabe wählen“).
"""

from __future__ import annotations

import asyncio
import html
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from sqlalchemy import delete, exists, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    Card,
    CardSet,
    CardSource,
    CmExpansion,
    CmProduct,
    ExpansionLinkSource,
    Game,
    ImageSource,
)
from app.services.cardmarket_catalog import (
    CARDMARKET_GAMES,
    invalidate_cardmarket_prices,
    link_set,
)
from app.services.catalog_numbers import normalize_number

log = structlog.get_logger(__name__)

GAME = Game.ONEPIECE.value
SINGLE_CATEGORY = CARDMARKET_GAMES[GAME].single_category
CARDLIST_PATH = "/cardlist/"
IMAGE_PATH = "/images/cardlist/card/{card_id}.png"
EXTERNAL_PREFIX = "op-"

_SERIES_SELECT = re.compile(r'<select[^>]*\bid="series"[^>]*>(.*?)</select>', re.S | re.I)
_OPTION = re.compile(r'<option[^>]*\bvalue="(\d+)"[^>]*>(.*?)</option>', re.S | re.I)
_CARD_BLOCK = re.compile(r"<dl\b([^>]*)>(.*?)</dl>", re.S | re.I)
_ATTR_ID = re.compile(r'\bid="([^"]+)"')
_ATTR_CLASS = re.compile(r'\bclass="([^"]*)"')
_INFO_COL = re.compile(r'<div[^>]*class="infoCol"[^>]*>(.*?)</div>', re.S | re.I)
_SPAN = re.compile(r"<span[^>]*>(.*?)</span>", re.S | re.I)
_CARD_NAME = re.compile(r'<div[^>]*class="cardName"[^>]*>(.*?)</div>', re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
# „OP01-001“, „ST10-005“, „EB01-007“, „PRB01-001“, „P-001“ (Promos) – mit Fassung „_p1“/„_r1“.
_CARD_ID = re.compile(r"^(?P<number>[A-Z]{1,5}\d{0,2}-\d{3})(?:_(?P<kind>[pr])(?P<n>\d+))?$")
# Setkürzel am Ende der Bezeichnung: „… [OP-01]“ (englisch) oder „…【OP-01】“ (japanisch).
_SERIES_CODE = re.compile(r"\s*[\[【]\s*([A-Z0-9-]+)\s*[\]】]\s*$")
# Erstes Kürzel einer Angabe – Doppelsets heißen auf Englisch „[OP14-EB04]“, auf Japanisch
# nur „【OP-14】“: Beide sollen dasselbe Set (``op-OP14``) werden.
_FIRST_CODE = re.compile(r"[A-Z]+-?\d+")
_TITLE = re.compile(r"^(?P<kind>.*?)\s*-(?P<title>.+?)-\s*$")
# Kartennummer im Cardmarket-Produktnamen: „Roronoa Zoro (OP01-001)“.
_PRODUCT_CODE = re.compile(r"\(([A-Z]{1,5}\d{0,2}-\d{3})\)")

# Setgruppen nach Kürzel (für „Sets durchblättern“, sprachunabhängig).
SERIES_GROUPS: tuple[tuple[str, str], ...] = (
    ("PRB", "Premium-Booster"),
    ("OP", "Booster"),
    ("EB", "Extra-Booster"),
    ("ST", "Starter-Decks"),
)
OTHER_GROUP = "Promos & Sonstiges"
MIN_SET_SHARE = 0.5  # so viele Nummern des Sets muss die Cardmarket-Ausgabe enthalten
ONEPIECE_VARIANTS = {"normal": True, "reverse": False, "holo": False}

Sleep = Callable[[float], Awaitable[None]]


class OnePieceCatalogError(Exception):
    """Kartenliste nicht erreichbar oder Aufbau unbekannt."""


# ------------------------------------------------------------------ Einlesen


def _text(fragment: str) -> str:
    """HTML-Fragment → Text (Tags weg, Entities aufgelöst, Leerraum zusammengefasst)."""
    # Die Set-Bezeichnungen sind doppelt kodiert („&lt;br class=…&gt;“) – zweimal auflösen.
    unescaped = html.unescape(html.unescape(fragment))
    return " ".join(_TAG.sub(" ", unescaped).split())


# Kleine Wörter bleiben im Titel klein („Wings of the Captain“), außer am Anfang.
_SMALL_WORDS = frozenset({"a", "an", "and", "at", "for", "in", "of", "on", "the", "to"})


def _title_case(title: str) -> str:
    """Großbuchstaben-Wörter als Titel („WINGS OF THE CAPTAIN“ → „Wings of the Captain“,
    auch mit Apostroph wie „SEA'S“); gemischte Schreibweisen („vol.2“) und Japanisch bleiben."""
    words = []
    for index, raw in enumerate(title.split()):
        word = raw
        if raw.isupper():
            lower = raw.lower()
            word = lower if index and lower in _SMALL_WORDS else raw.capitalize()
        words.append(word)
    return " ".join(words)


@dataclass(frozen=True)
class Series:
    """Ein Eintrag der Set-Auswahl."""

    series_id: str
    label: str
    code: str | None  # „OP01“, „EB05“, „PRB02“ – ohne Bindestrich

    @property
    def external_id(self) -> str:
        # Ohne Kürzel (Promos, Sonderprodukte): die letzten 4 Ziffern der Auswahl sind in
        # allen Sprachen gleich (EN 569801 ↔ JP 550801).
        return f"{EXTERNAL_PREFIX}{self.code or 'S' + self.series_id[-4:]}"

    @property
    def name(self) -> str:
        """„BOOSTER PACK -ROMANCE DAWN- [OP-01]“ → „Romance Dawn“."""
        text = _SERIES_CODE.sub("", self.label).strip()
        match = _TITLE.match(text)
        title = match.group("title").strip() if match else text
        return _title_case(title)

    @property
    def group(self) -> str:
        for prefix, label in SERIES_GROUPS:
            if self.code and self.code.startswith(prefix):
                return label
        return OTHER_GROUP


def parse_series(page: str) -> list[Series]:
    """Set-Auswahl der Startseite (Reihenfolge der Seite: neueste zuerst)."""
    select_match = _SERIES_SELECT.search(page)
    options = _OPTION.findall(select_match.group(1) if select_match else page)
    series: list[Series] = []
    seen: set[str] = set()
    for series_id, raw_label in options:
        if series_id in seen:
            continue
        seen.add(series_id)
        label = _text(raw_label)
        code_match = _SERIES_CODE.search(label)
        first = _FIRST_CODE.search(code_match.group(1)) if code_match else None
        code = first.group(0).replace("-", "") if first else None
        series.append(Series(series_id=series_id, label=label, code=code))
    return series


@dataclass(frozen=True)
class ParsedCard:
    """Eine Karte (Fassung) aus der Kartenliste."""

    card_id: str  # „OP01-001_p1“
    number: str  # „OP01-001“
    name: str
    rarity: str | None
    category: str | None
    variant_kind: str | None  # None (normal), „p“ (Parallel), „r“ (Nachdruck)
    variant_number: int

    @property
    def display_name(self) -> str:
        if self.variant_kind == "p":
            return f"{self.name} (Parallel)"
        if self.variant_kind == "r":
            return f"{self.name} (Reprint)"
        return self.name

    @property
    def variant_rank(self) -> int:
        """Reihenfolge der Fassungen derselben Nummer: normal, Parallel 1, 2, …, Nachdrucke."""
        if self.variant_kind is None:
            return 0
        return self.variant_number + (100 if self.variant_kind == "r" else 0)


def parse_cards(page: str) -> list[ParsedCard]:
    """Alle Karten einer Set-Seite; Blöcke ohne gültige Kartennummer werden übersprungen."""
    cards: list[ParsedCard] = []
    for attributes, body in _CARD_BLOCK.findall(page):
        css = _ATTR_CLASS.search(attributes)
        card_id_match = _ATTR_ID.search(attributes)
        if css is None or "modalCol" not in css.group(1).split() or card_id_match is None:
            continue
        card_id = card_id_match.group(1).strip()
        parsed_id = _CARD_ID.match(card_id)
        name_match = _CARD_NAME.search(body)
        if parsed_id is None or name_match is None or not _text(name_match.group(1)):
            continue
        info = _INFO_COL.search(body)
        spans = [_text(span) for span in _SPAN.findall(info.group(1))] if info else []
        cards.append(
            ParsedCard(
                card_id=card_id,
                number=parsed_id.group("number"),
                name=_text(name_match.group(1))[:180],
                rarity=(spans[1][:100] or None) if len(spans) > 1 else None,
                category=(spans[2][:60] or None) if len(spans) > 2 else None,  # noqa: PLR2004
                variant_kind=parsed_id.group("kind"),
                variant_number=int(parsed_id.group("n") or 0),
            )
        )
    return cards


# ----------------------------------------------------------------- Import


@dataclass
class LanguageReport:
    language: str
    series: int = 0
    sets: int = 0
    cards: int = 0
    parallels: int = 0
    duplicates: int = 0
    empty_series: list[str] = field(default_factory=list)
    failed_series: list[str] = field(default_factory=list)
    samples: list[str] = field(default_factory=list)


@dataclass
class LinkReport:
    sets_linked: int = 0
    sets_unlinked: list[str] = field(default_factory=list)
    cards_linked: int = 0
    cards_unlinked: int = 0


@dataclass
class ImportReport:
    languages: list[LanguageReport] = field(default_factory=list)
    link: LinkReport | None = None
    dry_run: bool = False
    sets_removed: int = 0
    english_names: int = 0


async def remove_empty_sets(session: AsyncSession) -> int:
    """One-Piece-Sets ohne Karten löschen (z. B. nach geänderter Set-Zuordnung: Die Karten
    sind beim Upsert ins neue Set gewandert). Gibt die Anzahl zurück."""
    removed = await session.scalars(
        delete(CardSet)
        .where(CardSet.game == GAME, ~exists().where(Card.set_id == CardSet.id))
        .returning(CardSet.external_id)
    )
    return len(removed.all())


# Englische Namen für japanische Karten und Sets: gleiche Kartennummer (ohne Fassung _p1/_r1,
# die Zählung der Parallel-Fassungen weicht zwischen den Listen ab) bzw. gleiches Set-Kürzel.
# Der Zusatz „(Parallel)“/„(Reprint)“ der japanischen Karte bleibt erhalten.
# Gleiche Abfrage in Migration 0023 (Erstbefüllung).
ENGLISH_CARD_NAMES_SQL = r"""
UPDATE cards AS ja
SET name_en = en.base || coalesce(substring(ja.name from '( \((Parallel|Reprint)\))$'), '')
FROM card_sets AS ja_set,
     (SELECT DISTINCT ON (regexp_replace(c.external_id, '_[pr][0-9]+$', ''))
             regexp_replace(c.external_id, '_[pr][0-9]+$', '') AS code,
             regexp_replace(c.name, ' \((Parallel|Reprint)\)$', '') AS base
      FROM cards AS c JOIN card_sets AS s ON s.id = c.set_id
      WHERE s.game = 'onepiece' AND c.language = 'en' AND c.external_id IS NOT NULL
      ORDER BY regexp_replace(c.external_id, '_[pr][0-9]+$', ''), c.external_id) AS en
WHERE ja_set.id = ja.set_id AND ja_set.game = 'onepiece' AND ja.language <> 'en'
  AND regexp_replace(ja.external_id, '_[pr][0-9]+$', '') = en.code
  AND ja.name_en IS DISTINCT FROM
      en.base || coalesce(substring(ja.name from '( \((Parallel|Reprint)\))$'), '')
"""
ENGLISH_SET_NAMES_SQL = """
UPDATE card_sets AS ja SET name_en = en.name
FROM card_sets AS en
WHERE ja.game = 'onepiece' AND en.game = 'onepiece' AND ja.language <> 'en'
  AND en.language = 'en' AND en.external_id = ja.external_id
  AND ja.name_en IS DISTINCT FROM en.name
"""


async def fill_english_names(session: AsyncSession) -> int:
    """Englische Namen japanischer One-Piece-Karten und -Sets setzen. Gibt die Anzahl
    geänderter Karten zurück."""
    cards = await session.execute(text(ENGLISH_CARD_NAMES_SQL))
    await session.execute(text(ENGLISH_SET_NAMES_SQL))
    return int(getattr(cards, "rowcount", 0) or 0)


def _import_order(series: Sequence[Series]) -> list[Series]:
    """Älteste zuerst und Sets mit Kürzel vor Promo-Seiten: Eine Karte gehört zu dem Set, in
    dem sie zuerst auftaucht (spätere Premium-Booster und Promo-Seiten listen sie erneut)."""
    oldest_first = list(reversed(series))
    return [s for s in oldest_first if s.code] + [s for s in oldest_first if not s.code]


class OnePieceCatalog:
    """Liest die offiziellen Kartenlisten und schreibt Sets und Karten (Upsert)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._transport = transport
        self._sleep = sleep

    async def run(
        self, languages: Sequence[str] | None = None, *, dry_run: bool = False
    ) -> ImportReport:
        report = ImportReport(dry_run=dry_run)
        sources = self._settings.onepiece_sources
        async with httpx.AsyncClient(
            headers={"User-Agent": self._settings.image_import_user_agent},
            timeout=60,
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            for language in languages or list(sources):
                base = sources[language].rstrip("/")
                report.languages.append(
                    await self._import_language(client, base, language, dry_run=dry_run)
                )
        if not dry_run:
            async with self._session_factory() as session:
                report.sets_removed = await remove_empty_sets(session)
                report.link = await link_onepiece(session)
                report.english_names = await fill_english_names(session)
                await session.commit()
        return report

    async def _get(self, client: httpx.AsyncClient, url: str, **params: str) -> str:
        await self._sleep(self._settings.onepiece_request_interval_seconds)
        response = await client.get(url, params=params or None)
        response.raise_for_status()
        return response.text

    async def _import_language(
        self, client: httpx.AsyncClient, base: str, language: str, *, dry_run: bool
    ) -> LanguageReport:
        report = LanguageReport(language=language)
        try:
            series = parse_series(await self._get(client, f"{base}{CARDLIST_PATH}"))
        except httpx.HTTPError as exc:
            raise OnePieceCatalogError(f"{language}: Kartenliste: {exc}") from exc
        if not series:
            raise OnePieceCatalogError(f"{language}: keine Sets in der Auswahl – Aufbau geändert?")
        report.series = len(series)
        seen: set[str] = set()
        for entry in _import_order(series):
            try:
                page = await self._get(client, f"{base}{CARDLIST_PATH}", series=entry.series_id)
            except httpx.HTTPError as exc:
                report.failed_series.append(f"{entry.label}: {type(exc).__name__}")
                continue
            cards = parse_cards(page)
            fresh = [card for card in cards if card.card_id not in seen]
            report.duplicates += len(cards) - len(fresh)
            seen.update(card.card_id for card in fresh)
            if not cards:
                report.empty_series.append(entry.label)
                continue
            report.sets += 1
            report.cards += len(fresh)
            report.parallels += sum(card.variant_kind is not None for card in fresh)
            if len(report.samples) < 6:  # noqa: PLR2004 – Beispiele für den Bericht
                first = fresh[0] if fresh else cards[0]
                report.samples.append(
                    f"{entry.external_id} „{entry.name}“ ({entry.group}): {len(cards)} Karten, "
                    f"z. B. {first.card_id} {first.display_name} [{first.rarity}]"
                )
            if not dry_run and fresh:
                async with self._session_factory() as session:
                    await self._store(
                        session, entry, language=language, base=base, all_cards=cards, fresh=fresh
                    )
                    await session.commit()
        log.info(
            "onepiece.language_done",
            language=language,
            sets=report.sets,
            cards=report.cards,
            empty=len(report.empty_series),
            failed=len(report.failed_series),
        )
        return report

    async def _store(
        self,
        session: AsyncSession,
        entry: Series,
        *,
        language: str,
        base: str,
        all_cards: Sequence[ParsedCard],
        fresh: Sequence[ParsedCard],
    ) -> None:
        values: dict[str, Any] = {
            "external_id": entry.external_id[:64],
            "language": language,
            "game": GAME,
            "name": (entry.name or entry.label)[:200],
            "series_name": entry.group,
            "code": entry.code[:16] if entry.code else None,
            "card_count_official": sum(card.variant_kind is None for card in all_cards),
            "card_count_total": len(all_cards),
            "synced_at": func.now(),
        }
        statement = insert(CardSet).values(values)
        set_id = await session.scalar(
            statement.on_conflict_do_update(
                index_elements=[CardSet.external_id, CardSet.language],
                set_={
                    key: statement.excluded[key]
                    for key in (
                        "game",
                        "name",
                        "series_name",
                        "code",
                        "card_count_official",
                        "card_count_total",
                        "synced_at",
                    )
                },
            ).returning(CardSet.id)
        )
        for card in fresh:
            image = f"{base}{IMAGE_PATH.format(card_id=card.card_id)}"
            card_statement = insert(Card).values(
                external_id=f"{EXTERNAL_PREFIX}{card.card_id}"[:64],
                language=language,
                set_id=set_id,
                number=card.number[:32],
                number_norm=normalize_number(card.number),
                name=card.display_name[:200],
                rarity=card.rarity,
                # Kein Reverse Holo bei One Piece – Parallel-Fassungen sind eigene Karten.
                variants=ONEPIECE_VARIANTS,
                image_url=image[:500],
                image_source=ImageSource.ONEPIECE,
                source=CardSource.ONEPIECE,
            )
            await session.execute(
                card_statement.on_conflict_do_update(
                    index_elements=[Card.external_id, Card.language],
                    index_where=Card.external_id.is_not(None),
                    set_={
                        "set_id": card_statement.excluded.set_id,
                        "name": card_statement.excluded.name,
                        "number": card_statement.excluded.number,
                        "number_norm": card_statement.excluded.number_norm,
                        "rarity": card_statement.excluded.rarity,
                        "variants": card_statement.excluded.variants,
                        "image_url": card_statement.excluded.image_url,
                        "image_source": card_statement.excluded.image_source,
                        "updated_at": func.now(),
                    },
                )
            )


# ---------------------------------------------------------- Cardmarket


def product_code(name: str) -> str | None:
    """Kartennummer aus dem Cardmarket-Produktnamen (die letzte in Klammern)."""
    codes = _PRODUCT_CODE.findall(name)
    return codes[-1] if codes else None


def _variant_rank(external_id: str | None) -> int:
    card_id = (external_id or "").removeprefix(EXTERNAL_PREFIX)
    match = _CARD_ID.match(card_id)
    if match is None or match.group("kind") is None:
        return 0
    return int(match.group("n") or 0) + (100 if match.group("kind") == "r" else 0)


@dataclass
class _Products:
    """One-Piece-Einzelkarten bei Cardmarket, nach Ausgabe und Nummer."""

    codes_by_expansion: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))
    by_expansion_code: dict[tuple[int, str], list[int]] = field(
        default_factory=lambda: defaultdict(list)
    )
    by_code: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))


async def _load_products(session: AsyncSession) -> _Products:
    products = _Products()
    rows = await session.execute(
        select(CmProduct.id_product, CmProduct.id_expansion, CmProduct.name)
        .where(CmProduct.game == GAME, CmProduct.id_category == SINGLE_CATEGORY)
        .order_by(CmProduct.id_product)
    )
    for id_product, id_expansion, name in rows:
        code = product_code(name)
        if code is None:
            continue
        products.codes_by_expansion[id_expansion].add(code)
        products.by_expansion_code[(id_expansion, code)].append(id_product)
        products.by_code[code].append(id_product)
    return products


def best_expansion(numbers: set[str], products: _Products) -> int | None:
    """Ausgabe mit den meisten Nummern des Sets (Gleichstand: die kleinere Ausgabe, also die
    passgenauere); ``None``, wenn keine mindestens :data:`MIN_SET_SHARE` enthält."""
    if not numbers:
        return None
    best: tuple[float, int] | None = None
    for expansion_id, codes in products.codes_by_expansion.items():
        shared = len(numbers & codes)
        if not shared or shared / len(numbers) < MIN_SET_SHARE:
            continue
        score = shared / len(numbers | codes)
        if best is None or score > best[0]:
            best = (score, expansion_id)
    return best[1] if best else None


async def link_onepiece(session: AsyncSession) -> LinkReport:
    """Sets mit ihrer Cardmarket-Ausgabe und Karten mit ihrem Produkt verknüpfen.

    Von Nutzern gewählte Ausgaben und Produkte bleiben unangetastet. Commit macht der
    Aufrufer.
    """
    report = LinkReport()
    products = await _load_products(session)
    if not products.by_code:
        return report  # Cardmarket-Katalog für One Piece noch nicht importiert
    first_added = {
        expansion.id_expansion: expansion.first_added
        for expansion in await session.scalars(select(CmExpansion).where(CmExpansion.game == GAME))
    }
    sets = (await session.scalars(select(CardSet).where(CardSet.game == GAME))).all()
    for card_set in sets:
        cards = (await session.scalars(select(Card).where(Card.set_id == card_set.id))).all()
        numbers = {card.number for card in cards}
        expansion_id = card_set.cardmarket_expansion_id
        if card_set.cardmarket_expansion_source != ExpansionLinkSource.USER.value:
            found = best_expansion(numbers, products)
            if found is not None and await link_set(
                session, card_set, found, ExpansionLinkSource.MATCHED
            ):
                report.sets_linked += 1
            expansion_id = found if found is not None else expansion_id
        if expansion_id is None:
            report.sets_unlinked.append(f"{card_set.language}/{card_set.external_id}")
        elif card_set.release_date is None and first_added.get(expansion_id):
            card_set.release_date = first_added[expansion_id]
        await _link_cards(session, cards, expansion_id, products, report)
    log.info(
        "onepiece.linked",
        sets=report.sets_linked,
        unlinked_sets=len(report.sets_unlinked),
        cards=report.cards_linked,
        unlinked_cards=report.cards_unlinked,
    )
    return report


async def _link_cards(
    session: AsyncSession,
    cards: Sequence[Card],
    expansion_id: int | None,
    products: _Products,
    report: LinkReport,
) -> None:
    by_number: defaultdict[str, list[Card]] = defaultdict(list)
    for card in cards:
        by_number[card.number].append(card)
    for number, versions in by_number.items():
        versions.sort(key=lambda card: _variant_rank(card.external_id))
        candidates = (
            products.by_expansion_code.get((expansion_id, number), [])
            if expansion_id is not None
            else []
        )
        if not candidates and len(products.by_code.get(number, [])) == 1:
            candidates = products.by_code[number]  # z. B. Promo in eigener Ausgabe
        if len(candidates) == len(versions):
            pairs = list(zip(versions, candidates, strict=True))
        elif candidates and _variant_rank(versions[0].external_id) == 0:
            pairs = [(versions[0], candidates[0])]  # nur die normale Karte ist eindeutig
        else:
            pairs = []
        assigned = {card.id for card, _ in pairs}
        for card, product_id in pairs:
            if card.cardmarket_product_id != product_id:
                if card.cardmarket_product_id is not None:
                    await invalidate_cardmarket_prices(session, card_id=card.id)
                card.cardmarket_product_id = product_id
            report.cards_linked += 1
        report.cards_unlinked += sum(card.id not in assigned for card in versions)


# ---------------------------------------------------------------- Bericht


def render_report(report: ImportReport) -> str:
    lines = ["# One-Piece-Katalog" + (" (Probelauf, nichts gespeichert)" if report.dry_run else "")]
    for entry in report.languages:
        lines += [
            "",
            f"## {entry.language}",
            "",
            f"- Sets in der Auswahl: {entry.series}, mit Karten: {entry.sets}",
            f"- Karten: {entry.cards} (davon Parallel/Nachdruck: {entry.parallels}), "
            f"doppelt gelistet: {entry.duplicates}",
        ]
        if entry.empty_series:
            lines.append(f"- ⚠️ Sets ohne Karten: {', '.join(entry.empty_series[:10])}")
        if entry.failed_series:
            lines.append(f"- ❌ Fehler: {', '.join(entry.failed_series[:10])}")
        lines += [f"  - {sample}" for sample in entry.samples]
    if report.link is not None:
        link = report.link
        lines += [
            "",
            "## Cardmarket",
            "",
            f"- Sets neu verknüpft: {link.sets_linked}, ohne Ausgabe: {len(link.sets_unlinked)}"
            + (f" ({', '.join(link.sets_unlinked[:15])})" if link.sets_unlinked else ""),
            f"- Karten mit Produkt: {link.cards_linked}, ohne: {link.cards_unlinked}",
            f"- Leere Sets entfernt: {report.sets_removed}",
            f"- Englische Namen gesetzt/geändert: {report.english_names}",
        ]
    return "\n".join(lines) + "\n"
