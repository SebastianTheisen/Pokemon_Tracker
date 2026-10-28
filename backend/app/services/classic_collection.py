"""Japanische Classic Collection (2023): Pokémon Card Game Classic – drei Decks mit je 32 Karten.

Die offizielle Datenbank pokemon-card.com führt sie nicht (Prüfung 28.10.2026). Sie druckt die
Grafiken des Grundsets 1996 neu – ohne Katalogeintrag erkannte der Scanner das Grundset.

Quellen (Prüfung ``docs/phase8/classic_sources.md``):

* **tcgcsv.com** (TCGplayer-Katalog, Pokémon Japan = Kategorie 85): je Deck eine Gruppe mit
  englischem Namen, gedruckter Nummer („001/032“) und Bild. Gespeichert wird nur die Adresse.
* **Cardmarket** (schon importiert): je Deck eine eigene Ausgabe mit allen Einzelkarten –
  zugeordnet über den englischen Namen, Rest in Nummern-Reihenfolge.

Pokémon bekommen den japanischen Namen (PokéAPI-Liste, „Charmander“ → „ヒトカゲ“): Ihn liest
der Scanner, und die App zeigt daraus den deutschen. Trainer und Energien behalten den
englischen. ``name_en`` hält immer den englischen Namen (Suche „charizard“).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CardSource, CmProduct, Game, ImageSource
from app.models.cardmarket import ExpansionLinkSource
from app.services.card_names import species_id_by_name, species_name
from app.services.cardmarket_catalog import invalidate_cardmarket_prices
from app.services.catalog_numbers import normalize_number

log = structlog.get_logger(__name__)

LANGUAGE = "ja"
CATEGORY = 85  # TCGplayer: Pokémon Japan
VARIANTS = {"normal": True, "reverse": False, "holo": False}
SMALL_IMAGE = "_200w.jpg"
LARGE_IMAGE = "_in_1000x1000.jpg"
_LEVEL = re.compile(r"\s+Lv\.?\s*\d+$", re.IGNORECASE)
_EX = re.compile(r"\s+ex$")
_BRACKET = re.compile(r"\s*\[.*$")
# Zusatz nach Bindestrich mit Leerzeichen: „Boss's Orders - Giovanni“ (nicht „Ho-Oh“).
_DASH_SUFFIX = re.compile(r"\s+-\s+.*$")
_KEY = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ClassicDeck:
    code: str
    tcgcsv_group: int
    cardmarket_expansion: int
    name: str


DECKS = (
    ClassicDeck("CLL", 23818, 5528, "Pokémon Card Game Classic: Charizard & Ho-Oh ex Deck"),
    ClassicDeck("CLF", 23819, 5527, "Pokémon Card Game Classic: Venusaur & Lugia ex Deck"),
    ClassicDeck("CLK", 23817, 5529, "Pokémon Card Game Classic: Blastoise & Suicune ex Deck"),
)


@dataclass(frozen=True)
class ClassicCard:
    english: str
    number: str  # „001“
    total: int | None  # 32
    rarity: str | None
    image_url: str | None

    @property
    def japanese(self) -> str | None:
        """Japanischer Name für Pokémon („Ho-Oh ex“ → „ホウオウex“), sonst ``None``."""
        base = _LEVEL.sub("", self.english).strip()
        suffix = "ex" if _EX.search(base) else ""
        species = species_id_by_name(_EX.sub("", base), "en")
        name = species_name(species, "ja") if species else None
        return f"{name}{suffix}" if name else None


@dataclass
class DeckReport:
    code: str
    cards: int = 0
    japanese_names: int = 0
    linked: int = 0
    unlinked: list[str] = field(default_factory=list)
    large_images: bool = False


@dataclass
class ClassicReport:
    decks: list[DeckReport] = field(default_factory=list)
    dry_run: bool = False
    error: str | None = None


def _extended(product: dict[str, Any], key: str) -> str | None:
    for entry in product.get("extendedData") or []:
        if entry.get("name") == key and entry.get("value"):
            return str(entry["value"]).strip()
    return None


def parse_products(data: object) -> list[ClassicCard]:
    """tcgcsv-Antwort → Karten mit Nummer (das Deck selbst und Zubehör fallen weg)."""
    items = data.get("results", []) if isinstance(data, dict) else []
    cards: list[ClassicCard] = []
    for product in items:
        if not isinstance(product, dict):
            continue
        printed = _extended(product, "Number")
        name = str(product.get("name") or "").strip()
        if not printed or not name:
            continue
        number, _, total = printed.partition("/")
        cards.append(
            ClassicCard(
                english=name,
                number=number.strip(),
                total=int(total) if total.strip().isdigit() else None,
                rarity=_extended(product, "Rarity"),
                image_url=str(product.get("imageUrl") or "") or None,
            )
        )
    return sorted(
        cards,
        key=lambda card: (int(card.number) if card.number.isdigit() else 10**6, card.number),
    )


def name_key(name: str) -> str:
    """Vergleichsschlüssel: Cardmarket „Charmander [Scratch | Ember]“ = tcgcsv „Charmander“;
    ebenso „Poké Ball“ = „Poke Ball“, „Parasect Lv.33“ = „Parasect“, „Boss's Orders -
    Giovanni“ = „Boss's Orders“ (Import 28.10.: fünf CLF-Karten blieben sonst offen)."""
    text = _DASH_SUFFIX.sub("", _BRACKET.sub("", name))
    text = _LEVEL.sub("", text)
    plain = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    return _KEY.sub("", plain.casefold())


def match_products(
    cards: Sequence[ClassicCard], products: Sequence[tuple[int, str]]
) -> dict[str, int]:
    """Nummer → Cardmarket-Produkt: zuerst über den Namen (eindeutig), den Rest in Reihenfolge
    (Produkt-IDs sind bei Cardmarket nach Kartennummer vergeben), wenn die Anzahl passt."""
    by_name: dict[str, list[int]] = {}
    for product_id, name in products:
        by_name.setdefault(name_key(name), []).append(product_id)
    names = [name_key(card.english) for card in cards]
    result: dict[str, int] = {}
    for card, key in zip(cards, names, strict=True):
        if names.count(key) == 1 and len(by_name.get(key, [])) == 1:
            result[card.number] = by_name[key][0]
    used = set(result.values())
    rest_cards = [card for card in cards if card.number not in result]
    rest_products = [pid for pid, _ in sorted(products) if pid not in used]
    if rest_cards and len(rest_cards) == len(rest_products):
        result |= {card.number: pid for card, pid in zip(rest_cards, rest_products, strict=True)}
    return result


class ClassicCollection:
    """Import der drei Decks (Upsert, wiederholbar)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._transport = transport

    async def run(self, *, dry_run: bool = False) -> ClassicReport:
        report = ClassicReport(dry_run=dry_run)
        base = self._settings.sealed_images_url.rstrip("/")
        async with httpx.AsyncClient(
            # Ohne eigene Kennung liefert tcgcsv keine Daten.
            headers={"User-Agent": self._settings.http_user_agent},
            timeout=60,
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            for deck in DECKS:
                response = await client.get(f"{base}/{CATEGORY}/{deck.tcgcsv_group}/products")
                response.raise_for_status()
                cards = parse_products(response.json())
                large = await self._large_images_work(client, cards)
                deck_report = DeckReport(
                    code=deck.code,
                    cards=len(cards),
                    japanese_names=sum(card.japanese is not None for card in cards),
                    large_images=large,
                )
                report.decks.append(deck_report)
                if dry_run or not cards:
                    continue
                async with self._session_factory() as session:
                    await self._store(session, deck, cards, large=large, report=deck_report)
                    await session.commit()
        log.info(
            "classic.import_done",
            decks=[(d.code, d.cards, d.linked) for d in report.decks],
            dry_run=dry_run,
        )
        return report

    @staticmethod
    async def _large_images_work(client: httpx.AsyncClient, cards: Sequence[ClassicCard]) -> bool:
        """Große Fassung des TCGplayer-Bildes vorhanden? (Stichprobe an der ersten Karte.)"""
        sample = next((card.image_url for card in cards if card.image_url), None)
        if sample is None or SMALL_IMAGE not in sample:
            return False
        try:
            response = await client.head(sample.replace(SMALL_IMAGE, LARGE_IMAGE))
        except httpx.HTTPError:
            return False
        return response.status_code == 200  # noqa: PLR2004

    async def _store(
        self,
        session: AsyncSession,
        deck: ClassicDeck,
        cards: Sequence[ClassicCard],
        *,
        large: bool,
        report: DeckReport,
    ) -> None:
        released = await session.scalar(
            select(func.min(CmProduct.date_added)).where(
                CmProduct.id_expansion == deck.cardmarket_expansion
            )
        )
        totals = [card.total for card in cards if card.total]
        values: dict[str, Any] = {
            "external_id": deck.code,
            "language": LANGUAGE,
            "game": Game.POKEMON.value,
            "name": deck.name,
            "series_name": "Classic",
            "code": deck.code,
            "release_date": released or date(2023, 11, 10),
            "card_count_official": max(totals, default=None),
            "card_count_total": len(cards),
            "cardmarket_expansion_id": deck.cardmarket_expansion,
            "cardmarket_expansion_source": ExpansionLinkSource.BUILTIN.value,
            "synced_at": func.now(),
        }
        statement = insert(CardSet).values(values)
        set_id = await session.scalar(
            statement.on_conflict_do_update(
                index_elements=[CardSet.external_id, CardSet.language],
                set_={key: statement.excluded[key] for key in values if key != "external_id"},
            ).returning(CardSet.id)
        )
        for card in cards:
            image = card.image_url
            if large and image:
                image = image.replace(SMALL_IMAGE, LARGE_IMAGE)
            row = insert(Card).values(
                external_id=f"{deck.code}-{card.number}"[:64],
                language=LANGUAGE,
                set_id=set_id,
                number=card.number[:32],
                number_norm=normalize_number(card.number),
                name=(card.japanese or card.english)[:200],
                name_en=card.english[:200],
                rarity=card.rarity,
                variants=VARIANTS,
                image_url=image[:500] if image else None,
                image_source=ImageSource.TCGPLAYER,
                source=CardSource.TCGPLAYER,
            )
            await session.execute(
                row.on_conflict_do_update(
                    index_elements=[Card.external_id, Card.language],
                    index_where=Card.external_id.is_not(None),
                    set_={
                        key: row.excluded[key]
                        for key in (
                            "set_id",
                            "name",
                            "name_en",
                            "number",
                            "number_norm",
                            "rarity",
                            "variants",
                            "image_url",
                            "image_source",
                        )
                    }
                    | {"updated_at": func.now()},
                )
            )
        await self._link(session, deck, cards, set_id=set_id, report=report)

    @staticmethod
    async def _link(
        session: AsyncSession,
        deck: ClassicDeck,
        cards: Sequence[ClassicCard],
        *,
        set_id: object,
        report: DeckReport,
    ) -> None:
        products = [
            (row.id_product, row.name)
            for row in (
                await session.execute(
                    select(CmProduct.id_product, CmProduct.name).where(
                        CmProduct.id_expansion == deck.cardmarket_expansion,
                        CmProduct.category_name.ilike("%single%"),
                    )
                )
            ).all()
        ]
        mapping = match_products(cards, products)
        stored = {
            card.number: card
            for card in (await session.scalars(select(Card).where(Card.set_id == set_id))).unique()
        }
        for card in cards:
            row = stored.get(card.number)
            product_id = mapping.get(card.number)
            if row is None or product_id is None:
                report.unlinked.append(f"{card.number} {card.english}")
                continue
            if row.cardmarket_product_id != product_id:
                if row.cardmarket_product_id is not None:
                    await invalidate_cardmarket_prices(session, card_id=row.id)
                row.cardmarket_product_id = product_id
            report.linked += 1


def render_report(report: ClassicReport) -> str:
    title = "# Classic Collection" + (" (Probelauf, nichts gespeichert)" if report.dry_run else "")
    lines = [title, ""]
    if report.error:
        lines.append(f"Fehler: {report.error}")
    for deck in report.decks:
        lines.append(
            f"- **{deck.code}**: {deck.cards} Karten, davon {deck.japanese_names} mit "
            f"japanischem Namen; Cardmarket verknüpft {deck.linked}"
            + (f", offen: {', '.join(deck.unlinked)}" if deck.unlinked else "")
            + ("; große Bilder" if deck.large_images else "; kleine Bilder (200 px)")
        )
    return "\n".join(lines) + "\n"


async def refresh_classic_collection(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> ClassicReport | None:
    """Für den Worker: abgleichen, Fehler nur protokollieren."""
    try:
        return await ClassicCollection(session_factory, settings).run()
    except Exception:  # Quelle nicht erreichbar o. Ä. – nächster Lauf versucht es erneut
        log.exception("classic.import_failed")
        return None
