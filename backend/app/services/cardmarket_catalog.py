"""Cardmarket-Katalog: Import der offiziellen Downloads und richtige Verknüpfung der Karten.

Ablauf (täglich im Worker, von Hand mit ``python -m app.cli cardmarket-import``):

1. **Download** von Produktkatalog (Einzelkarten und Versiegeltes) und Preisführer
   (je ~15 MB JSON, kein Scraping).
2. **Ausgaben und Zwillinge**: Ausgaben mit fast denselben Karten (``idMetacard``), die
   innerhalb weniger Wochen angelegt wurden, sind Sprachfassungen desselben Sets –
   z. B. 30th Celebration japanisch (6602) und vereinfacht-chinesisch (6603).
3. **Ausgabe je Set**: Für jedes Set fragt der Import TCGdex nach der Cardmarket-ID einer
   Karte und merkt sich deren Ausgabe. Bekannte Fehler von TCGdex sind fest hinterlegt
   (:data:`KNOWN_SET_EXPANSIONS`), Nutzer können die Ausgabe in der App ändern.

Beim Preisabruf (:func:`correct_cardmarket_quotes`) wird das Produkt, das TCGdex meldet,
über ``idMetacard`` in die Ausgabe des Sets umgehängt. Liegt es dort nicht, gelten die Werte
des Preisführers für das richtige Produkt; gibt es dort keins, lieber gar kein Cardmarket-
Preis als ein falscher.

Ein Set mit Zwillingen, dessen Ausgabe nur von TCGdex stammt, gilt als **unsicher** – die
App zeigt dann einen Hinweis und die Auswahl der Sprachfassung.

**Mehrere Spiele:** Cardmarket bietet die Downloads je Spiel an (``…_6.json`` Pokémon,
``…_18.json`` One Piece, :data:`CARDMARKET_GAMES`). Jedes Spiel wird in einem eigenen Lauf
importiert; Preise werden nur innerhalb desselben Spiels aufgeräumt. Pokémon verknüpft
seine Sets über TCGdex und die Kartennamen, One Piece über die aufgedruckte Kartennummer
(:mod:`app.services.onepiece_catalog`).
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

import httpx
import structlog
from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    Card,
    CardPriceLink,
    CardSet,
    CardSource,
    CmExpansion,
    CmImport,
    CmPrice,
    CmProduct,
    ExpansionLinkSource,
    Game,
    PriceCheck,
    PricePoint,
)
from app.providers.pricing import CardRef, PriceQuote
from app.providers.pricing.tcgdex_prices import (
    CARDMARKET,
    CARDMARKET_URL_NAMES,
    parse_pricing,
    product_id_from_url,
)
from app.providers.tcgdex import TcgdexClient, TcgdexError
from app.services.audit import record_audit
from app.services.errors import NotFoundError

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CardmarketGame:
    """Ein Spiel bei Cardmarket: Nummer der Downloads, Kategorie der Einzelkarten, URL-Teil."""

    game: str
    id_game: int
    single_category: int
    url_name: str

    @property
    def products_path(self) -> str:
        return f"productList/products_singles_{self.id_game}.json"

    @property
    def sealed_path(self) -> str:
        return f"productList/products_nonsingles_{self.id_game}.json"

    @property
    def guide_path(self) -> str:
        return f"priceGuide/price_guide_{self.id_game}.json"


# Spike ``docs/phase5/onepiece.md`` (25.10.2026): One Piece = Spiel 18, Einzelkarten 1621.
CARDMARKET_GAMES: dict[str, CardmarketGame] = {
    Game.POKEMON.value: CardmarketGame(
        Game.POKEMON.value, 6, 51, CARDMARKET_URL_NAMES[Game.POKEMON.value]
    ),
    Game.ONEPIECE.value: CardmarketGame(
        Game.ONEPIECE.value, 18, 1621, CARDMARKET_URL_NAMES[Game.ONEPIECE.value]
    ),
}
SINGLE_CATEGORY = CARDMARKET_GAMES[Game.POKEMON.value].single_category  # „Pokémon Single“
# Kategorien der Einzelkarten aller Spiele; alles andere ist versiegelt.
SINGLE_CATEGORIES: tuple[int, ...] = tuple(g.single_category for g in CARDMARKET_GAMES.values())
GUIDE_METRICS = ("trend", "low", "avg", "avg1", "avg7", "avg30")
GUIDE_KEYS = (*GUIDE_METRICS, *(f"{metric}-holo" for metric in GUIDE_METRICS))
# Zwillinge: höchstens so viele Tage zwischen den ersten Einträgen beider Ausgaben und
# mindestens dieser Anteil gemeinsamer Karten (Jaccard über ``idMetacard``).
TWIN_MAX_DAYS = 45
TWIN_MIN_SIMILARITY = 0.75
# Zeilen je INSERT (asyncpg erlaubt höchstens 32 767 Parameter je Anweisung).
BATCH_SIZE = 4000
# Karten je Set, die TCGdex nach ihrer Cardmarket-ID gefragt werden (die erste mit ID zählt).
SET_SAMPLE_CARDS = 3
# Preisabruf erzwingen: so tun, als sei der letzte Abruf uralt (``last_viewed_at`` bleibt).
STALE_CHECK = datetime(2000, 1, 1, tzinfo=UTC)
CENT = Decimal("0.01")

# Bekannte Fehler von TCGdex: (Sprache, Set-ID) → richtige Cardmarket-Ausgabe.
# Geprüft vom Nutzer am 20.10.2026 auf cardmarket.com (Glurak M6a 137).
KNOWN_SET_EXPANSIONS: dict[tuple[str, str], int] = {("ja", "M6a"): 6602}
# Bezeichnungen, die der Download nicht kennt (Nutzer können weitere vergeben).
KNOWN_EXPANSION_LABELS: dict[int, str] = {
    6602: "Japanisch",
    6603: "Chinesisch (vereinfacht)",
    6604: "Indonesisch/Thailändisch",
}

# Nur hier kann TCGdex die Sprachfassung verwechseln: Westliche Karten (DE, EN, FR, …) führt
# Cardmarket in einer gemeinsamen Ausgabe; deren „Zwilling“ ist die asiatische Fassung.
# Spike 20.10.2026: alle 14 unsicheren DE/EN-Sets waren richtig verknüpft.
ASIAN_LANGUAGES = ("ja", "ko", "zh-tw", "zh-cn")

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CatalogError(Exception):
    """Download nicht erreichbar oder Format unbekannt."""


# -------------------------------------------------------------------- Einlesen


@dataclass(frozen=True)
class ProductRow:
    id_product: int
    id_expansion: int
    id_metacard: int
    name: str
    date_added: date | None
    id_category: int | None = SINGLE_CATEGORY
    category_name: str | None = None
    game: str = Game.POKEMON.value


@dataclass(frozen=True)
class GuideRow:
    id_product: int
    metrics: dict[str, float]


def _positive_int(value: object) -> int | None:
    # bool ist in Python ein int – ``true`` ist keine ID.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def parse_created_at(value: object) -> datetime | None:
    """``createdAt`` der Downloads, z. B. ``2026-10-20T14:24:46+0200``."""
    if not isinstance(value, str):
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_date(value: object) -> date | None:
    """``dateAdded`` (``2026-09-11 10:28:18``); alte Produkte haben ``0000-00-00 …``."""
    if not isinstance(value, str) or value.startswith("0000"):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _rows(data: object, key: str) -> tuple[datetime | None, list[dict[str, Any]]]:
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise CatalogError(f"Download: Liste „{key}“ fehlt")
    rows = [row for row in data[key] if isinstance(row, dict)]
    return parse_created_at(data.get("createdAt")), rows


def parse_products(
    data: object, *, game: str = Game.POKEMON.value
) -> tuple[datetime | None, list[ProductRow]]:
    """Produktkatalog einlesen; unvollständige Einträge werden übersprungen."""
    created_at, rows = _rows(data, "products")
    products: list[ProductRow] = []
    for row in rows:
        id_product = _positive_int(row.get("idProduct"))
        id_expansion = _positive_int(row.get("idExpansion"))
        name = row.get("name")
        if id_product is None or id_expansion is None or not isinstance(name, str):
            continue
        products.append(
            ProductRow(
                id_product=id_product,
                id_expansion=id_expansion,
                id_metacard=_positive_int(row.get("idMetacard")) or 0,
                name=name.strip()[:300],
                date_added=_parse_date(row.get("dateAdded")),
                id_category=_positive_int(row.get("idCategory")),
                category_name=str(row.get("categoryName") or "")[:60] or None,
                game=game,
            )
        )
    return created_at, products


def parse_price_guide(data: object) -> tuple[datetime | None, list[GuideRow]]:
    """Preisführer einlesen; nur Einträge mit mindestens einem Preis über 0."""
    created_at, rows = _rows(data, "priceGuides")
    guide: list[GuideRow] = []
    for row in rows:
        id_product = _positive_int(row.get("idProduct"))
        if id_product is None:
            continue
        metrics = {
            key: value
            for key in GUIDE_KEYS
            if (value := _positive_number(row.get(key))) is not None
        }
        if metrics:
            guide.append(GuideRow(id_product=id_product, metrics=metrics))
    return created_at, guide


# ------------------------------------------------------------- Zwillinge


@dataclass(frozen=True)
class ExpansionStats:
    id_expansion: int
    product_count: int
    first_added: date | None
    metacards: frozenset[int]


def expansion_stats(products: Iterable[ProductRow]) -> dict[int, ExpansionStats]:
    counts: defaultdict[int, int] = defaultdict(int)
    first: dict[int, date] = {}
    metacards: defaultdict[int, set[int]] = defaultdict(set)
    for product in products:
        counts[product.id_expansion] += 1
        if product.date_added is not None:
            known = first.get(product.id_expansion)
            first[product.id_expansion] = (
                min(known, product.date_added) if known else (product.date_added)
            )
        if product.id_metacard:
            metacards[product.id_expansion].add(product.id_metacard)
    return {
        expansion: ExpansionStats(
            id_expansion=expansion,
            product_count=count,
            first_added=first.get(expansion),
            metacards=frozenset(metacards[expansion]),
        )
        for expansion, count in counts.items()
    }


def find_twins(
    stats: dict[int, ExpansionStats],
    *,
    max_days: int = TWIN_MAX_DAYS,
    min_similarity: float = TWIN_MIN_SIMILARITY,
) -> dict[int, list[int]]:
    """Ausgaben mit fast denselben Karten, angelegt innerhalb von ``max_days`` Tagen.

    Nachdrucke Jahre später (Grundset ↔ Celebrations) sind keine Zwillinge – nur
    Sprachfassungen, die Cardmarket gleichzeitig anlegt.
    """
    dated = sorted(
        (s.first_added, s.id_expansion, s.metacards)
        for s in stats.values()
        if s.first_added is not None and s.metacards
    )
    twins: defaultdict[int, list[int]] = defaultdict(list)
    for index, (first_day, first_id, first_cards) in enumerate(dated):
        for second_day, second_id, second_cards in dated[index + 1 :]:
            if (second_day - first_day).days > max_days:
                break  # sortiert nach Datum: alle weiteren sind noch später
            shared = len(first_cards & second_cards)
            if shared and shared / len(first_cards | second_cards) >= min_similarity:
                twins[first_id].append(second_id)
                twins[second_id].append(first_id)
    return {expansion: sorted(ids) for expansion, ids in twins.items()}


# --------------------------------------------------------------- Speichern


def _batches[T](rows: Sequence[T], size: int = BATCH_SIZE) -> Iterable[Sequence[T]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


@dataclass
class StoreReport:
    products: int = 0
    prices: int = 0
    expansions: int = 0
    expansions_with_twins: int = 0


async def store_catalog(
    session: AsyncSession,
    products: Sequence[ProductRow],
    guide: Sequence[GuideRow],
    *,
    guide_created_at: datetime,
    game: str = Game.POKEMON.value,
) -> StoreReport:
    """Produkte, Preise und Ausgaben eines Spiels schreiben (Upsert). Commit macht der
    Aufrufer."""
    report = StoreReport(products=len(products), prices=len(guide))
    single_category = CARDMARKET_GAMES[game].single_category
    for chunk in _batches(products):
        statement = insert(CmProduct).values(
            [
                {
                    "id_product": p.id_product,
                    "game": game,
                    "id_expansion": p.id_expansion,
                    "id_metacard": p.id_metacard,
                    "name": p.name,
                    "date_added": p.date_added,
                    "id_category": p.id_category,
                    "category_name": p.category_name,
                }
                for p in chunk
            ]
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[CmProduct.id_product],
                set_={
                    column: statement.excluded[column]
                    for column in (
                        "game",
                        "id_expansion",
                        "id_metacard",
                        "name",
                        "date_added",
                        "id_category",
                        "category_name",
                    )
                },
            )
        )

    for guide_chunk in _batches(guide):
        price_statement = insert(CmPrice).values(
            [
                {
                    "id_product": g.id_product,
                    "game": game,
                    "metrics": g.metrics,
                    "updated_at": guide_created_at,
                }
                for g in guide_chunk
            ]
        )
        await session.execute(
            price_statement.on_conflict_do_update(
                index_elements=[CmPrice.id_product],
                set_={
                    "game": price_statement.excluded.game,
                    "metrics": price_statement.excluded.metrics,
                    "updated_at": price_statement.excluded.updated_at,
                },
            )
        )
    # Was im neuen Preisführer fehlt, hat keinen aktuellen Preis mehr – nur in diesem Spiel:
    # Die Preisführer der Spiele haben verschiedene Zeitstempel.
    await session.execute(
        delete(CmPrice)
        .where(CmPrice.game == game, CmPrice.updated_at < guide_created_at)
        .execution_options(synchronize_session=False)
    )

    # Ausgaben und Zwillinge nur aus Einzelkarten (Versiegeltes hat keine Metakarte).
    stats = expansion_stats(p for p in products if p.id_category in (None, single_category))
    twins = find_twins(stats)
    report.expansions = len(stats)
    report.expansions_with_twins = len(twins)
    rows = [
        {
            "id_expansion": s.id_expansion,
            "game": game,
            "product_count": s.product_count,
            "first_added": s.first_added,
            "twin_ids": twins.get(s.id_expansion, []),
        }
        for s in stats.values()
    ]
    for expansion_chunk in _batches(rows):
        expansion_statement = insert(CmExpansion).values(list(expansion_chunk))
        await session.execute(
            expansion_statement.on_conflict_do_update(
                index_elements=[CmExpansion.id_expansion],
                set_={
                    column: expansion_statement.excluded[column]
                    for column in ("game", "product_count", "first_added", "twin_ids")
                },
            )
        )
    for expansion_id, label in KNOWN_EXPANSION_LABELS.items():
        await session.execute(
            update(CmExpansion)
            .where(CmExpansion.id_expansion == expansion_id, CmExpansion.label.is_(None))
            .values(label=label)
            .execution_options(synchronize_session=False)
        )
    return report


async def download_catalog(
    settings: Settings,
    *,
    game: CardmarketGame = CARDMARKET_GAMES[Game.POKEMON.value],
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[object, object, object]:
    """Lädt Einzelkarten, versiegelte Produkte und Preisführer (gleichzeitig) als JSON."""
    base = settings.cardmarket_catalog_url.rstrip("/")
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.http_user_agent},
        timeout=180,
        follow_redirects=True,
        transport=transport,
    ) as client:
        try:
            responses = await asyncio.gather(
                client.get(f"{base}/{game.products_path}"),
                client.get(f"{base}/{game.sealed_path}"),
                client.get(f"{base}/{game.guide_path}"),
            )
            for response in responses:
                response.raise_for_status()
            return responses[0].json(), responses[1].json(), responses[2].json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CatalogError(f"Download: {type(exc).__name__}: {exc}") from exc


# ------------------------------------------------------- Ausgabe je Set


async def invalidate_cardmarket_prices(
    session: AsyncSession, *, set_id: uuid.UUID | None = None, card_id: uuid.UUID | None = None
) -> None:
    """Cardmarket-Werte eines Sets bzw. einer Karte verwerfen und Neuabruf erzwingen.

    Die alten Werte gehören zum falschen Produkt – auch im Verlauf. Angesehen-Markierungen
    (tägliche Aktualisierung) bleiben erhalten.
    """
    if card_id is not None:
        cards: Any = [card_id]
    elif set_id is not None:
        cards = select(Card.id).where(Card.set_id == set_id).scalar_subquery()
    else:
        raise ValueError("set_id oder card_id angeben")
    await session.execute(
        delete(PricePoint)
        .where(PricePoint.card_id.in_(cards), PricePoint.source == CARDMARKET)
        .execution_options(synchronize_session=False)
    )
    await session.execute(
        update(PriceCheck)
        .where(PriceCheck.card_id.in_(cards))
        .values(checked_at=STALE_CHECK)
        .execution_options(synchronize_session=False)
    )
    # Bereits geladene PriceCheck-Objekte sollen den neuen Stand sehen.
    for loaded in [o for o in session.identity_map.values() if isinstance(o, PriceCheck)]:
        await session.refresh(loaded)


async def link_set(
    session: AsyncSession,
    card_set: CardSet,
    expansion_id: int,
    source: ExpansionLinkSource,
    *,
    user_id: uuid.UUID | None = None,
) -> bool:
    """Ausgabe eines Sets setzen. ``True``, wenn sie sich geändert hat.

    Wechselt die Ausgabe (oder wird eine falsche Zuordnung von TCGdex erstmals korrigiert),
    werden die gespeicherten Cardmarket-Werte des Sets verworfen.
    """
    previous = card_set.cardmarket_expansion_id
    card_set.cardmarket_expansion_id = expansion_id
    card_set.cardmarket_expansion_source = source.value
    card_set.cardmarket_expansion_by_id = user_id
    if previous == expansion_id:
        return False
    if previous is not None or source != ExpansionLinkSource.TCGDEX:
        await invalidate_cardmarket_prices(session, set_id=card_set.id)
    log.info(
        "cardmarket.set_linked",
        set=card_set.external_id,
        language=card_set.language,
        expansion=expansion_id,
        previous=previous,
        source=source.value,
    )
    return True


async def apply_known_links(session: AsyncSession) -> int:
    """Fest hinterlegte Ausgaben setzen (außer ein Nutzer hat selbst gewählt)."""
    changed = 0
    for (language, external_id), expansion_id in KNOWN_SET_EXPANSIONS.items():
        card_set = await session.scalar(
            select(CardSet).where(CardSet.language == language, CardSet.external_id == external_id)
        )
        if card_set is None or card_set.cardmarket_expansion_source == ExpansionLinkSource.USER:
            continue
        if await link_set(session, card_set, expansion_id, ExpansionLinkSource.BUILTIN):
            changed += 1
    return changed


async def learn_tcgdex_product(session: AsyncSession, card: Card, product_id: int) -> None:
    """Merkt sich das von TCGdex gemeldete Produkt und – falls noch offen – die Ausgabe."""
    if card.cardmarket_product_id != product_id:
        card.cardmarket_product_id = product_id
    card_set = card.card_set
    if card_set.cardmarket_expansion_source in (
        ExpansionLinkSource.USER,
        ExpansionLinkSource.BUILTIN,
    ):
        return
    known = KNOWN_SET_EXPANSIONS.get((card_set.language, card_set.external_id))
    if known is not None:
        await link_set(session, card_set, known, ExpansionLinkSource.BUILTIN)
        return
    if card_set.cardmarket_expansion_id is None:
        product = await session.get(CmProduct, product_id)
        if product is not None:
            await link_set(session, card_set, product.id_expansion, ExpansionLinkSource.TCGDEX)


def tcgdex_product_id(card_data: dict[str, object]) -> int | None:
    """Cardmarket-ID aus den TCGdex-Kartendetails (``pricing.cardmarket.idProduct``)."""
    pricing = card_data.get("pricing")
    cardmarket = pricing.get("cardmarket") if isinstance(pricing, dict) else None
    return _positive_int(cardmarket.get("idProduct")) if isinstance(cardmarket, dict) else None


async def link_sets(
    session_factory: async_sessionmaker[AsyncSession],
    client: TcgdexClient,
    settings: Settings,
    *,
    now: datetime,
) -> int:
    """Ausgabe für alle Sets ohne Zuordnung bei TCGdex erfragen. Gibt die Anzahl zurück.

    Je Set werden bis zu :data:`SET_SAMPLE_CARDS` Karten abgefragt; Sets ohne Cardmarket-ID
    erst nach ``cardmarket_set_recheck_days`` Tagen erneut.
    """
    recheck_before = now - timedelta(days=settings.cardmarket_set_recheck_days)
    ranked = (
        select(
            Card.id,
            Card.set_id,
            Card.external_id,
            Card.language,
            func.row_number()
            .over(partition_by=Card.set_id, order_by=(Card.number_norm, Card.external_id))
            .label("rank"),
        )
        .join(CardSet, CardSet.id == Card.set_id)
        .where(
            Card.external_id.is_not(None),
            Card.source == CardSource.TCGDEX,
            CardSet.cardmarket_expansion_id.is_(None),
            or_(
                CardSet.cardmarket_checked_at.is_(None),
                CardSet.cardmarket_checked_at < recheck_before,
            ),
        )
        .subquery()
    )
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(ranked.c.id, ranked.c.set_id, ranked.c.external_id, ranked.c.language)
                .where(ranked.c.rank <= SET_SAMPLE_CARDS)
                .order_by(ranked.c.set_id, ranked.c.rank)
            )
        ).all()
    samples: defaultdict[uuid.UUID, list[tuple[uuid.UUID, str, str]]] = defaultdict(list)
    for row in rows:
        samples[row.set_id].append((row.id, row.external_id, row.language))
    semaphore = asyncio.Semaphore(settings.cardmarket_set_link_concurrency)

    async def probe(
        set_id: uuid.UUID, cards: list[tuple[uuid.UUID, str, str]]
    ) -> tuple[uuid.UUID, uuid.UUID | None, int | None]:
        async with semaphore:
            for card_id, external_id, language in cards:
                try:
                    data = await client.get_card(language, external_id)
                except TcgdexError:
                    continue
                if (product_id := tcgdex_product_id(data)) is not None:
                    return set_id, card_id, product_id
        return set_id, None, None

    linked = 0
    for next_result in asyncio.as_completed(
        [probe(set_id, cards) for set_id, cards in samples.items()]
    ):
        set_id, card_id, product_id = await next_result
        async with session_factory() as session:
            card_set = await session.get_one(CardSet, set_id)
            card_set.cardmarket_checked_at = now
            if card_id is not None and product_id is not None:
                await learn_tcgdex_product(
                    session, await session.get_one(Card, card_id), product_id
                )
                linked += card_set.cardmarket_expansion_id is not None
            await session.commit()
    log.info("cardmarket.sets_linked", checked=len(samples), linked=linked)
    return linked


# --------------------------------------------------------- Produkt je Karte


Reason = Literal["tcgdex", "set", "card", "unmapped", "none"]


@dataclass(frozen=True)
class ProductResolution:
    """Welches Cardmarket-Produkt gilt für eine Karte – und warum.

    ``tcgdex``: wie von TCGdex gemeldet · ``set``: über die Ausgabe des Sets umgehängt ·
    ``card``: vom Nutzer gewählt · ``unmapped``: in der Ausgabe des Sets nicht gefunden ·
    ``none``: kein Produkt bekannt.
    """

    product_id: int | None
    tcgdex_product_id: int | None
    reason: Reason

    @property
    def corrected(self) -> bool:
        return self.reason in ("set", "card", "unmapped")


async def remap_product(session: AsyncSession, product: CmProduct, expansion_id: int) -> int | None:
    """Dieselbe Karte (``idMetacard``) in einer anderen Ausgabe.

    Gibt es sie dort mehrfach (z. B. normale und alternative Version), entscheidet die
    Reihenfolge der Produkt-IDs in beiden Ausgaben.
    """
    if product.id_expansion == expansion_id:
        return product.id_product
    if product.id_metacard <= 0:
        return None
    rows = (
        await session.execute(
            select(CmProduct.id_product, CmProduct.id_expansion)
            .where(
                CmProduct.id_metacard == product.id_metacard,
                CmProduct.id_expansion.in_((product.id_expansion, expansion_id)),
            )
            .order_by(CmProduct.id_product)
        )
    ).all()
    origin: list[int] = [r.id_product for r in rows if r.id_expansion == product.id_expansion]
    targets: list[int] = [r.id_product for r in rows if r.id_expansion == expansion_id]
    if len(targets) == 1:
        return targets[0]
    if not targets or product.id_product not in origin:
        return None
    rank = origin.index(product.id_product)
    return targets[rank] if rank < len(targets) else None


async def are_twins(session: AsyncSession, first: int, second: int) -> bool:
    """Sind zwei Ausgaben Sprachfassungen desselben Sets?"""
    expansion = await session.get(CmExpansion, first)
    return expansion is not None and second in expansion.twin_ids


async def resolve_product(session: AsyncSession, card: Card) -> ProductResolution:
    tcgdex_id = card.cardmarket_product_id
    if card.cardmarket_product_override is not None:
        return ProductResolution(card.cardmarket_product_override, tcgdex_id, "card")
    if tcgdex_id is None:
        return ProductResolution(None, None, "none")
    expansion_id = card.card_set.cardmarket_expansion_id
    product = await session.get(CmProduct, tcgdex_id)
    if (
        expansion_id is None
        or product is None
        or product.id_expansion == expansion_id
        # Nur zwischen Sprachfassungen umhängen: Manche Sets liegen bei Cardmarket bewusst
        # in mehreren Ausgaben (z. B. Trainer Gallery) – deren Karten bleiben, wo sie sind.
        or not await are_twins(session, product.id_expansion, expansion_id)
    ):
        return ProductResolution(tcgdex_id, tcgdex_id, "tcgdex")
    mapped = await remap_product(session, product, expansion_id)
    return ProductResolution(mapped, tcgdex_id, "set" if mapped is not None else "unmapped")


async def guide_quotes(session: AsyncSession, ref: CardRef, product_id: int) -> list[PriceQuote]:
    """Cardmarket-Werte eines Produkts aus dem Preisführer (gleiches Format wie TCGdex)."""
    price = await session.get(CmPrice, product_id)
    if price is None:
        return []
    pricing = {
        CARDMARKET: {
            **price.metrics,
            "idProduct": product_id,
            "updated": price.updated_at.isoformat(),
            "unit": "EUR",
        }
    }
    return parse_pricing(ref, pricing, now=price.updated_at)


async def correct_cardmarket_quotes(
    session: AsyncSession, card: Card, ref: CardRef, quotes: Sequence[PriceQuote]
) -> list[PriceQuote]:
    """Cardmarket-Werte einer Preisquelle auf das richtige Produkt umstellen.

    Merkt sich dabei das von der Quelle gemeldete Produkt (und die Ausgabe des Sets).
    """
    reported = {
        product_id
        for q in quotes
        if q.source == CARDMARKET and (product_id := product_id_from_url(q.source_url))
    }
    if len(reported) == 1:
        await learn_tcgdex_product(session, card, reported.pop())
    resolution = await resolve_product(session, card)
    if not resolution.corrected:
        if resolution.product_id is None or any(q.source == CARDMARKET for q in quotes):
            return list(quotes)
        # Die Quelle kennt das Produkt nicht (z. B. Karte aus einer offiziellen Datenbank,
        # über den Namen verknüpft) – dann gelten die Werte des Preisführers.
        return [*quotes, *await guide_quotes(session, ref, resolution.product_id)]
    kept = [q for q in quotes if q.source != CARDMARKET]
    if resolution.product_id is None:
        return kept  # lieber kein Cardmarket-Preis als der eines falschen Produkts
    return kept + await guide_quotes(session, ref, resolution.product_id)


# ------------------------------------------------------- Auswahl in der App


@dataclass(frozen=True)
class ProductOption:
    product_id: int
    expansion_id: int
    expansion_label: str | None
    expansion_size: int | None
    name: str
    trend: Decimal | None
    low: Decimal | None
    url: str
    selected: bool
    from_tcgdex: bool


@dataclass(frozen=True)
class CardmarketChoice:
    card_id: uuid.UUID
    product_id: int | None
    expansion_id: int | None
    reason: Reason
    set_source: str | None
    uncertain: bool
    catalog_ready: bool
    url: str | None
    options: list[ProductOption] = field(default_factory=list)


def product_url(product_id: int, game: str = Game.POKEMON.value) -> str:
    url_name = CARDMARKET_GAMES.get(game, CARDMARKET_GAMES[Game.POKEMON.value]).url_name
    return f"https://www.cardmarket.com/de/{url_name}/Products?idProduct={product_id}"


def _euro(metrics: dict[str, float], key: str) -> Decimal | None:
    value = metrics.get(key)
    return Decimal(str(value)).quantize(CENT) if value else None


async def cardmarket_choice(session: AsyncSession, card: Card) -> CardmarketChoice:
    """Aktuelles Produkt und Alternativen (gleiche Karte in Zwillings-Ausgaben)."""
    resolution = await resolve_product(session, card)
    card_set = card.card_set
    catalog_ready = bool(await session.scalar(select(exists().where(CmProduct.id_product > 0))))
    base_id = resolution.product_id or resolution.tcgdex_product_id
    base = await session.get(CmProduct, base_id) if base_id is not None else None
    tcgdex_product = (
        await session.get(CmProduct, resolution.tcgdex_product_id)
        if resolution.tcgdex_product_id is not None
        else None
    )
    current = await session.get(CmProduct, resolution.product_id) if resolution.product_id else None
    expansion_id = current.id_expansion if current else card_set.cardmarket_expansion_id
    result = CardmarketChoice(
        card_id=card.id,
        product_id=resolution.product_id,
        expansion_id=expansion_id,
        reason=resolution.reason,
        set_source=card_set.cardmarket_expansion_source,
        uncertain=False,
        catalog_ready=catalog_ready,
        url=product_url(resolution.product_id, card_set.game) if resolution.product_id else None,
    )
    if base is None:
        return result

    expansion_ids = {base.id_expansion}
    if tcgdex_product is not None:
        expansion_ids.add(tcgdex_product.id_expansion)
    if card_set.cardmarket_expansion_id is not None:
        expansion_ids.add(card_set.cardmarket_expansion_id)
    known = {
        e.id_expansion: e
        for e in await session.scalars(
            select(CmExpansion).where(CmExpansion.id_expansion.in_(expansion_ids))
        )
    }
    for expansion in list(known.values()):
        expansion_ids.update(expansion.twin_ids)
    expansions = {
        e.id_expansion: e
        for e in await session.scalars(
            select(CmExpansion).where(CmExpansion.id_expansion.in_(expansion_ids))
        )
    }
    if base.id_metacard > 0:
        products = list(
            await session.scalars(
                select(CmProduct)
                .where(
                    CmProduct.id_metacard == base.id_metacard,
                    CmProduct.id_expansion.in_(expansion_ids),
                )
                .order_by(CmProduct.id_expansion, CmProduct.id_product)
            )
        )
    else:
        products = [base]
    prices = {
        p.id_product: p.metrics
        for p in await session.scalars(
            select(CmPrice).where(CmPrice.id_product.in_([p.id_product for p in products]))
        )
    }
    options: list[ProductOption] = []
    for p in products:
        info = expansions.get(p.id_expansion)
        metrics = prices.get(p.id_product, {})
        options.append(
            ProductOption(
                product_id=p.id_product,
                expansion_id=p.id_expansion,
                expansion_label=info.label if info else None,
                expansion_size=info.product_count if info else None,
                name=p.name,
                trend=_euro(metrics, "trend"),
                low=_euro(metrics, "low"),
                url=product_url(p.id_product, p.game),
                selected=p.id_product == resolution.product_id,
                from_tcgdex=p.id_product == resolution.tcgdex_product_id,
            )
        )
    base_expansion = expansions.get(base.id_expansion)
    uncertain = (
        resolution.reason != "card"
        and card_set.language in ASIAN_LANGUAGES
        and card_set.cardmarket_expansion_source
        in (None, ExpansionLinkSource.TCGDEX.value, ExpansionLinkSource.MATCHED.value)
        and base_expansion is not None
        and bool(base_expansion.twin_ids)
    )
    return replace(result, uncertain=uncertain or resolution.reason == "unmapped", options=options)


@dataclass(frozen=True)
class ChoiceResult:
    set_changed: bool
    cards_affected: int


async def choose_product(
    session: AsyncSession, card: Card, product_id: int, user_id: uuid.UUID
) -> ChoiceResult:
    """Nutzer wählt das richtige Cardmarket-Produkt einer Karte.

    Liegt es in einer anderen Sprachfassung (Zwillings-Ausgabe), gilt diese ab sofort für
    das **ganze Set** (alle Karten werden über ``idMetacard`` umgehängt). Weicht das Produkt
    sonst von der automatischen Zuordnung ab, gilt es nur für diese Karte.
    """
    product = await session.get(CmProduct, product_id)
    if product is None:
        raise NotFoundError("Cardmarket-Produkt unbekannt – Katalog noch nicht importiert?")
    card_set = card.card_set
    current = card_set.cardmarket_expansion_id
    set_changed = False
    if (
        current is None
        or current == product.id_expansion
        or await are_twins(session, current, product.id_expansion)
    ):
        # Andere Sprachfassung (oder Bestätigung): gilt für das ganze Set.
        set_changed = await link_set(
            session, card_set, product.id_expansion, ExpansionLinkSource.USER, user_id=user_id
        )
    previous_override = card.cardmarket_product_override
    card.cardmarket_product_override = None
    automatic = (await resolve_product(session, card)).product_id
    override = None if automatic == product_id else product_id
    card.cardmarket_product_override = override
    if previous_override != override and not set_changed:
        await invalidate_cardmarket_prices(session, card_id=card.id)
    # Die neue Auswahl ersetzt eine per Lesezeichen gemerkte Seite.
    await session.execute(
        delete(CardPriceLink)
        .where(CardPriceLink.card_id == card.id)
        .execution_options(synchronize_session=False)
    )
    cards_affected = 1
    if set_changed:
        cards_affected = int(
            await session.scalar(
                select(func.count()).select_from(Card).where(Card.set_id == card_set.id)
            )
            or 0
        )
    record_audit(
        session,
        action="cardmarket.product_chosen",
        actor_id=user_id,
        details={
            "card_id": str(card.id),
            "set": f"{card_set.language}/{card_set.external_id}",
            "product_id": product_id,
            "expansion_id": product.id_expansion,
            "set_changed": set_changed,
        },
    )
    return ChoiceResult(set_changed=set_changed, cards_affected=cards_affected)


async def set_expansion_label(
    session: AsyncSession, expansion_id: int, label: str | None, user_id: uuid.UUID
) -> CmExpansion:
    """Bezeichnung einer Ausgabe setzen (leer = entfernen)."""
    expansion = await session.get(CmExpansion, expansion_id)
    if expansion is None:
        raise NotFoundError("Cardmarket-Ausgabe unbekannt")
    expansion.label = " ".join((label or "").split())[:100] or None
    expansion.label_by_id = user_id
    record_audit(
        session,
        action="cardmarket.expansion_labeled",
        actor_id=user_id,
        details={"expansion_id": expansion_id, "label": expansion.label},
    )
    return expansion


# ----------------------------------------------------------------- Importlauf


@dataclass
class ImportSummary:
    run_id: int
    products: int = 0
    prices: int = 0
    expansions: int = 0
    expansions_with_twins: int = 0
    known_links: int = 0
    sets_linked: int = 0
    names_matched: int = 0  # Karten, die über den Namen ein Produkt bekamen
    catalog_created_at: datetime | None = None
    guide_created_at: datetime | None = None
    error: str | None = None


async def run_catalog_import(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    tcgdex: TcgdexClient | None,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Clock = _utc_now,
    game: str = Game.POKEMON.value,
) -> ImportSummary:
    """Ein Lauf für ein Spiel: herunterladen, speichern, Sets verknüpfen.

    Pokémon: feste Ausgaben, TCGdex, Kartennamen (``tcgdex=None`` überspringt TCGdex, z. B.
    für einen schnellen Test). One Piece: über die Kartennummer im Produktnamen.
    Fehler werden im Lauf protokolliert und als ``error`` zurückgegeben.
    """
    cm_game = CARDMARKET_GAMES[game]
    async with session_factory() as session:
        run = CmImport(game=game)
        session.add(run)
        await session.commit()
        summary = ImportSummary(run_id=run.id)
    try:
        products_data, sealed_data, guide_data = await download_catalog(
            settings, game=cm_game, transport=transport
        )
        summary.catalog_created_at, products = parse_products(products_data, game=game)
        _, sealed = parse_products(sealed_data, game=game)
        summary.guide_created_at, guide = parse_price_guide(guide_data)
        if not products:
            raise CatalogError("Produktkatalog ist leer")
        async with session_factory() as session:
            stored = await store_catalog(
                session,
                [*products, *sealed],
                guide,
                guide_created_at=summary.guide_created_at or clock(),
                game=game,
            )
            if game == Game.POKEMON.value:
                summary.known_links = await apply_known_links(session)
            await session.commit()
        summary.products, summary.prices = stored.products, stored.prices
        summary.expansions = stored.expansions
        summary.expansions_with_twins = stored.expansions_with_twins
        if game == Game.POKEMON.value:
            await _link_pokemon(session_factory, settings, tcgdex, summary, now=clock())
        else:
            from app.services.onepiece_catalog import link_onepiece  # noqa: PLC0415 – Zyklus

            async with session_factory() as session:
                linked = await link_onepiece(session)
                await session.commit()
            summary.sets_linked, summary.names_matched = linked.sets_linked, linked.cards_linked
    except Exception as exc:  # Lauf protokollieren statt den Worker zu stören
        summary.error = f"{type(exc).__name__}: {exc}"[:500]
        log.exception("cardmarket.import_failed")
    async with session_factory() as session:
        await session.execute(
            update(CmImport)
            .where(CmImport.id == summary.run_id)
            .values(
                finished_at=clock(),
                products=summary.products,
                prices=summary.prices,
                expansions=summary.expansions,
                sets_linked=summary.sets_linked,
                catalog_created_at=summary.catalog_created_at,
                guide_created_at=summary.guide_created_at,
                error=summary.error,
            )
        )
        await session.commit()
    log.info(
        "cardmarket.import_done",
        products=summary.products,
        prices=summary.prices,
        twins=summary.expansions_with_twins,
        linked=summary.sets_linked,
        error=summary.error,
    )
    return summary


async def _link_pokemon(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    tcgdex: TcgdexClient | None,
    summary: ImportSummary,
    *,
    now: datetime,
) -> None:
    """Pokémon-Sets verknüpfen: erst über TCGdex, dann über die Kartennamen."""
    if tcgdex is not None:
        summary.sets_linked = await link_sets(session_factory, tcgdex, settings, now=now)
    # Erst nach TCGdex: übernimmt nur, was TCGdex offen lässt.
    from app.services.cardmarket_matching import match_cardmarket  # noqa: PLC0415 – Zyklus
    from app.services.cardmarket_rescue import rescue_cardmarket  # noqa: PLC0415 – Zyklus

    async with session_factory() as session:
        matched = await match_cardmarket(session)
        await session.commit()
    summary.names_matched = sum(matched.cards_linked.values())
    # Zweiter Durchgang für Sammlungskarten (Name mehrfach, kleine Sets) – Regeln siehe Modul
    async with session_factory() as session:
        rescued = await rescue_cardmarket(session, dry_run=False, only_owned=True)
        await session.commit()
    summary.names_matched += len(rescued.cards)


async def last_successful_import(
    session: AsyncSession, game: str = Game.POKEMON.value
) -> datetime | None:
    return await session.scalar(
        select(func.max(CmImport.finished_at)).where(
            CmImport.error.is_(None), CmImport.game == game
        )
    )


# --------------------------------------------------------------------- Status


@dataclass(frozen=True)
class UncertainSet:
    language: str
    external_id: str
    name: str
    expansion_id: int
    expansion_label: str | None
    twins: list[tuple[int, str | None]]


@dataclass(frozen=True)
class CatalogStatus:
    last_run: CmImport | None
    products: int
    prices: int
    sets_total: int
    sets_by_source: dict[str, int]
    uncertain: list[UncertainSet]


async def catalog_status(session: AsyncSession) -> CatalogStatus:
    last_run = await session.scalar(
        select(CmImport)
        .where(CmImport.game == Game.POKEMON.value)
        .order_by(CmImport.id.desc())
        .limit(1)
    )
    products = int(await session.scalar(select(func.count()).select_from(CmProduct)) or 0)
    prices = int(await session.scalar(select(func.count()).select_from(CmPrice)) or 0)
    source_rows = await session.execute(
        select(CardSet.cardmarket_expansion_source, func.count()).group_by(
            CardSet.cardmarket_expansion_source
        )
    )
    by_source = {str(source or "offen"): int(count) for source, count in source_rows}
    labels = {
        e.id_expansion: e
        for e in await session.scalars(
            select(CmExpansion).where(func.cardinality(CmExpansion.twin_ids) > 0)
        )
    }
    candidates = await session.scalars(
        select(CardSet)
        .where(
            CardSet.cardmarket_expansion_source.in_(
                (ExpansionLinkSource.TCGDEX.value, ExpansionLinkSource.MATCHED.value)
            ),
            CardSet.cardmarket_expansion_id.in_(list(labels)),
            CardSet.language.in_(ASIAN_LANGUAGES),
        )
        .order_by(CardSet.language, CardSet.external_id)
    )
    uncertain = []
    for card_set in candidates:
        expansion = labels.get(card_set.cardmarket_expansion_id or 0)
        if expansion is None:
            continue
        uncertain.append(
            UncertainSet(
                language=card_set.language,
                external_id=card_set.external_id,
                name=card_set.name,
                expansion_id=expansion.id_expansion,
                expansion_label=expansion.label,
                twins=[
                    (twin, labels[twin].label if twin in labels else None)
                    for twin in expansion.twin_ids
                ],
            )
        )
    return CatalogStatus(
        last_run=last_run,
        products=products,
        prices=prices,
        sets_total=sum(by_source.values()),
        sets_by_source=by_source,
        uncertain=uncertain,
    )


def _expansion_text(expansion_id: int, label: str | None) -> str:
    return f"{expansion_id} ({label})" if label else str(expansion_id)


def render_status(status: CatalogStatus) -> str:
    lines = ["# Cardmarket-Katalog", ""]
    run = status.last_run
    if run is None:
        lines.append("- Noch kein Import.")
    else:
        lines.append(
            f"- Letzter Lauf: {run.started_at:%Y-%m-%d %H:%M} UTC, "
            f"{'❌ ' + run.error if run.error else 'ok' if run.finished_at else 'läuft'}"
        )
        if run.guide_created_at:
            lines.append(f"- Preisführer vom {run.guide_created_at:%Y-%m-%d %H:%M %z}")
        if run.sealed_images is not None:
            lines.append(f"- Bilder für Versiegeltes zugeordnet: {run.sealed_images}")
    lines.append(f"- Produkte: {status.products}, mit Preis: {status.prices}")
    sources = ", ".join(f"{k}: {v}" for k, v in sorted(status.sets_by_source.items()))
    lines.append(f"- Sets: {status.sets_total} (Ausgabe von {sources})")
    lines += ["", f"## Unsichere Sets ({len(status.uncertain)})", ""]
    lines.append("Asiatische Sets, Ausgabe nur von TCGdex, es gibt gleichzeitige Sprachfassungen.")
    lines.append("")
    for item in status.uncertain:
        twins = ", ".join(_expansion_text(t, label) for t, label in item.twins)
        lines.append(
            f"- {item.language}/{item.external_id} {item.name}: "
            f"{_expansion_text(item.expansion_id, item.expansion_label)} – Zwillinge {twins}"
        )
    return "\n".join(lines)
