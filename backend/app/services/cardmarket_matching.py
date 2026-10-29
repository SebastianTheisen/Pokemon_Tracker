"""Cardmarket-Zuordnung über Kartennamen – für Sets und Karten, die TCGdex nicht verknüpft.

TCGdex meldet die Cardmarket-ID nur für einen Teil der Karten (Japan: unter der Hälfte), und
Karten aus anderen Quellen (offizielle Datenbanken, pokemontcg.io, PriceCharting) haben gar
keine. Der Cardmarket-Katalog enthält aber je Ausgabe alle Einzelkarten mit englischem Namen
(„Charizard ex [Burning Darkness | Explosive Vortex]“). Daraus:

1. **Ausgabe je Set** (nur Sets ohne Ausgabe): die Ausgabe, deren Kartennamen am besten zu
   den (englischen) Namen des Sets passen – mindestens :data:`MIN_SET_SHARE` der Namen des
   Sets und :data:`MIN_EXPANSION_SHARE` der Ausgabe, zeitlich passend. Sprachfassungen
   (Zwillinge, z. B. Japanisch 6602 und vereinfachtes Chinesisch 6603) sind gleich gut –
   Japanisch nimmt die ältere, Chinesisch die jüngere Ausgabe; sonst bleibt es offen.
2. **Produkt je Karte** (nur Karten ohne Produkt): gleicher Name in der Ausgabe des Sets.
   Gibt es den Namen mehrfach (normale Karte, Illustration Rare, …), entscheidet die
   Reihenfolge – Karten nach Nummer, Produkte nach Produkt-ID –, aber nur, wenn die Anzahl
   auf beiden Seiten gleich ist.

Japanische, koreanische und chinesische Namen werden über die Pokédex-Daten ins Englische
übersetzt; deutsche Karten nehmen den Namen ihrer englischen Fassung. Trainerkarten ohne
englischen Namen bleiben offen – außer sie haben einen aus TCGplayer (``name_en``,
:func:`app.services.japanese_gaps.JapaneseGaps`).
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CardSet, CmExpansion, CmProduct, ExpansionLinkSource, Game
from app.services.card_names import translate_card_name
from app.services.cardmarket_catalog import SINGLE_CATEGORY, link_set

log = structlog.get_logger(__name__)

MATCH_LANGUAGES = ("en", "de", "ja", "zh-cn")
MIN_COMMON_NAMES = 5
MIN_SET_SHARE = 0.6
MIN_EXPANSION_SHARE = 0.4
MAX_DATE_GAP_DAYS = 180
TIE = 0.02
_VERSION = re.compile(r"\s*\(V\.\s*\d+\)\s*$", re.I)
_ASCII = re.compile(r"^[\x20-\x7e]+$")


def name_key(name: str) -> str:
    """Vergleichsform: „Charizard ex [Burning Darkness | …] (V.2)“ und „Charizard-ex“ →
    „charizardex“."""
    base = _VERSION.sub("", name.split(" [", 1)[0])
    return re.sub(r"[\W_]+", "", base.casefold())


@dataclass
class MatchReport:
    sets_linked: dict[str, int] = field(default_factory=dict)
    cards_linked: dict[str, int] = field(default_factory=dict)
    sets_ambiguous: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # „ja/SV2a Pokémon Card 151 → 5207 (…)“

    def count(self, bucket: dict[str, int], language: str, amount: int = 1) -> None:
        bucket[language] = bucket.get(language, 0) + amount


@dataclass
class _Card:
    id: uuid.UUID
    number_norm: str
    key: str | None
    product_id: int | None


@dataclass
class _Expansion:
    id: int
    first_added: date | None
    twins: frozenset[int]
    names: dict[str, list[int]]  # Namensschlüssel → Produkt-IDs (aufsteigend)
    sample: str = ""  # ein Produktname zur Kontrolle im Bericht


def _number_order(number: str) -> tuple[int, int, str]:
    digits = re.match(r"(\d+)", number)
    return (0, int(digits.group(1)), number) if digits else (1, 0, number)


def english_name(
    name: str, language: str, english_sibling: str | None, name_en: str | None = None
) -> str | None:
    """Englischer Name einer Karte für den Vergleich mit Cardmarket. ``name_en``: englischer
    Name aus TCGplayer (japanische Trainer, die die Pokédex-Übersetzung nicht kennt)."""
    if language == "en":
        return name
    if english_sibling:
        return english_sibling
    if language == "de":
        return None
    translated = translate_card_name(name, language, target="en")
    if translated:
        return translated
    if name_en:
        return name_en
    return name if _ASCII.match(name) else None  # z. B. PriceCharting-Karten (englisch)


async def _load_expansions(session: AsyncSession) -> dict[int, _Expansion]:
    names: defaultdict[int, defaultdict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    samples: dict[int, str] = {}
    rows = await session.execute(
        select(CmProduct.id_product, CmProduct.id_expansion, CmProduct.name)
        .where(CmProduct.id_category == SINGLE_CATEGORY)
        .order_by(CmProduct.id_product)
    )
    for product_id, expansion_id, name in rows:
        if key := name_key(name):
            names[expansion_id][key].append(product_id)
            samples.setdefault(expansion_id, name)
    expansions = {e.id_expansion: e for e in (await session.scalars(select(CmExpansion))).all()}
    return {
        expansion_id: _Expansion(
            id=expansion_id,
            first_added=expansions[expansion_id].first_added
            if expansion_id in expansions
            else None,
            twins=frozenset(
                expansions[expansion_id].twin_ids if expansion_id in expansions else ()
            ),
            names=dict(by_name),
            sample=samples.get(expansion_id, ""),
        )
        for expansion_id, by_name in names.items()
    }


def _choose_expansion(
    card_set: CardSet,
    keys: set[str],
    expansions: dict[int, _Expansion],
    owners: dict[int, set[str]],
) -> int | str | None:
    """Beste Ausgabe für ein Set; ``"ambiguous"``, wenn mehrere gleich gut passen.

    Eine Ausgabe, die schon zu einem *anderen* Set gehört (andere Set-ID), scheidet aus –
    sonst bekäme z. B. das japanische „151“ die englische Ausgabe und damit englische Preise.
    Sprachfassungen desselben Sets (gleiche ID, z. B. Englisch und Deutsch) teilen sie sich.
    """
    scored: list[tuple[float, int]] = []
    for expansion in expansions.values():
        owner = owners.get(expansion.id)
        if owner and card_set.external_id not in owner:
            continue
        common = len(keys & expansion.names.keys())
        if common < MIN_COMMON_NAMES:
            continue
        share_set, share_expansion = common / len(keys), common / len(expansion.names)
        if share_set < MIN_SET_SHARE or share_expansion < MIN_EXPANSION_SHARE:
            continue
        if card_set.release_date and expansion.first_added:
            gap = abs((expansion.first_added - card_set.release_date).days)
            if gap > MAX_DATE_GAP_DAYS:
                continue
        scored.append((share_set + share_expansion, expansion.id))
    if not scored:
        return None
    scored.sort(reverse=True)
    best_score = scored[0][0]
    tied = [expansion_id for score, expansion_id in scored if best_score - score <= TIE]
    if len(tied) == 1:
        return tied[0]
    first = expansions[tied[0]]
    if all(other == first.id or other in first.twins for other in tied):
        if card_set.language == "ja":
            return min(tied)  # Japanisch erscheint vor der chinesischen Fassung
        if card_set.language == "zh-cn":
            return max(tied)
    return "ambiguous"


async def match_cardmarket(  # noqa: PLR0912, PLR0915 – ein Durchgang über alle Sets
    session: AsyncSession, *, dry_run: bool = False, languages: tuple[str, ...] = MATCH_LANGUAGES
) -> MatchReport:
    """Sets und Karten über Kartennamen mit Cardmarket verknüpfen. Commit macht der Aufrufer."""
    report = MatchReport()
    expansions = await _load_expansions(session)
    english = dict(
        (
            await session.execute(
                select(Card.external_id, Card.name).where(
                    Card.language == "en", Card.external_id.is_not(None)
                )
            )
        ).all()
    )
    # Nur Pokémon: Andere Spiele haben eigene Kategorien und eine eigene Verknüpfung.
    sets = (
        await session.scalars(
            select(CardSet).where(
                CardSet.language.in_(languages), CardSet.game == Game.POKEMON.value
            )
        )
    ).all()
    rows = await session.execute(
        select(
            Card.id,
            Card.set_id,
            Card.external_id,
            Card.language,
            Card.name,
            Card.name_en,
            Card.number_norm,
            Card.cardmarket_product_id,
            Card.cardmarket_product_override,
        )
        .join(CardSet, CardSet.id == Card.set_id)
        .where(Card.language.in_(languages), CardSet.game == Game.POKEMON.value)
    )
    cards: defaultdict[uuid.UUID, list[_Card]] = defaultdict(list)
    for row in rows:
        name = english_name(row.name, row.language, english.get(row.external_id), row.name_en)
        cards[row.set_id].append(
            _Card(
                id=row.id,
                number_norm=row.number_norm,
                key=name_key(name) if name else None,
                product_id=row.cardmarket_product_override or row.cardmarket_product_id,
            )
        )
    owners: defaultdict[int, set[str]] = defaultdict(set)
    for external_id, expansion_id in await session.execute(
        select(CardSet.external_id, CardSet.cardmarket_expansion_id).where(
            CardSet.cardmarket_expansion_id.is_not(None), CardSet.game == Game.POKEMON.value
        )
    ):
        if expansion_id is not None:
            owners[expansion_id].add(external_id)

    # 1. Ausgabe je Set
    assigned: dict[uuid.UUID, int] = {}
    for card_set in sets:
        if card_set.cardmarket_expansion_id is not None:
            continue
        keys = {card.key for card in cards.get(card_set.id, []) if card.key}
        if len(keys) < MIN_COMMON_NAMES:
            continue
        chosen = _choose_expansion(card_set, keys, expansions, owners)
        if chosen == "ambiguous":
            report.sets_ambiguous.append(f"{card_set.language}/{card_set.external_id}")
            continue
        if not isinstance(chosen, int):
            continue
        owners[chosen].add(card_set.external_id)
        assigned[card_set.id] = chosen
        picked = expansions[chosen]
        report.links.append(
            f"{card_set.language}/{card_set.external_id} {card_set.name} → {chosen} "
            f"({len(keys & picked.names.keys())}/{len(keys)} Namen, z. B. „{picked.sample}“)"
        )
        report.count(report.sets_linked, card_set.language)
        if not dry_run:
            await link_set(session, card_set, chosen, ExpansionLinkSource.MATCHED)

    # 2. Produkt je Karte
    updates: dict[uuid.UUID, int] = {}
    for card_set in sets:
        expansion = expansions.get(
            assigned.get(card_set.id, card_set.cardmarket_expansion_id or -1)
        )
        if expansion is None:
            continue
        groups: defaultdict[str, list[_Card]] = defaultdict(list)
        for card in cards.get(card_set.id, []):
            if card.key:
                groups[card.key].append(card)
        linked = 0
        for key, group in groups.items():
            products = expansion.names.get(key)
            if not products or len(products) != len(group):
                continue
            group.sort(key=lambda card: _number_order(card.number_norm))
            for card, product_id in zip(group, products, strict=True):
                if card.product_id is None:
                    updates[card.id] = product_id
                    linked += 1
        if linked:
            report.count(report.cards_linked, card_set.language, linked)
    if not dry_run:
        for card_id, product_id in updates.items():
            await session.execute(
                update(Card).where(Card.id == card_id).values(cardmarket_product_id=product_id)
            )
    log.info(
        "cardmarket.match_done",
        sets=report.sets_linked,
        cards=report.cards_linked,
        ambiguous=len(report.sets_ambiguous),
        dry_run=dry_run,
    )
    return report


def render_match_report(report: MatchReport, *, dry_run: bool) -> str:
    verb = "würden verknüpft" if dry_run else "verknüpft"
    lines = [
        f"Sets {verb}: " + (", ".join(f"{k}: {v}" for k, v in report.sets_linked.items()) or "0"),
        f"Karten {verb}: "
        + (", ".join(f"{k}: {v}" for k, v in report.cards_linked.items()) or "0"),
    ]
    lines += [f"  {link}" for link in report.links]
    if report.sets_ambiguous:
        lines.append("Mehrdeutig (offen): " + ", ".join(report.sets_ambiguous[:40]))
    return "\n".join(lines)
