"""Zweiter Durchgang der Cardmarket-Zuordnung für Karten, die :func:`match_cardmarket` offen
lässt – mit nachvollziehbaren Regeln und Probelauf.

Offen bleiben dort vor allem zwei Fälle (Collectr-Import 29.10.: 27 Karten in 15 Sets):

1. **Name mehrfach** in der Ausgabe (normale Karte + Special Art Rare, Promo-Sammelausgaben
   mit drei „Pikachu“): Der erste Durchgang ordnet nur zu, wenn die Anzahl auf beiden Seiten
   gleich ist. Hier: Produkte, die schon eine andere Karte des Sets hat, fallen weg. Bleibt
   genau eines übrig, ist es eindeutig. Sonst entscheidet die Reihenfolge – Cardmarket vergibt
   Produkt-IDs in Druckreihenfolge, eine Karte über der Setgröße (Secret Rare) ist die letzte,
   eine reguläre die erste. Das gilt nur, wenn genau eine Karte dieses Namens offen ist.
2. **Set ohne Ausgabe** und zu klein für die strengen Schwellen (Concept Packs, alte Sets):
   Ausgabe, die mindestens :data:`MIN_SHARE` der Namen des Sets enthält, zeitlich passt und
   eindeutig die beste ist; mindestens :data:`MIN_COMMON` gemeinsame Namen.

Alles andere bleibt offen und steht im Bericht.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CardSet, CmProduct, CollectionItem, ExpansionLinkSource, Game
from app.services.card_names import TRANSLATED_LANGUAGES, contradicts_english
from app.services.cardmarket_catalog import invalidate_cardmarket_prices, link_set
from app.services.cardmarket_matching import (
    MATCH_LANGUAGES,
    MAX_DATE_GAP_DAYS,
    _Expansion,
    _load_expansions,
    _number_order,
    english_name,
    name_key,
)

log = structlog.get_logger(__name__)

MIN_COMMON = 3
MIN_SHARE = 0.8
LEAD = 0.15  # Vorsprung der besten Ausgabe vor der zweitbesten


@dataclass
class _Open:
    id: uuid.UUID
    set_id: uuid.UUID
    number: str
    name: str
    key: str


@dataclass
class RescueReport:
    sets: list[str] = field(default_factory=list)
    cards: list[str] = field(default_factory=list)
    still_open: list[str] = field(default_factory=list)
    dry_run: bool = True


def pick_product(
    card_number: str, set_size: int | None, candidates: list[int], free: list[int]
) -> int | None:
    """Produkt für eine einzelne offene Karte eines mehrfach vorkommenden Namens."""
    if len(free) == 1:
        return free[0]
    if not free:
        return None
    digits = _number_order(card_number)
    secret = set_size is not None and digits[0] == 0 and digits[1] > set_size
    if secret:
        return max(free)  # Secret Rares werden zuletzt angelegt
    if set_size is not None and digits[0] == 0 and digits[1] <= set_size:
        return min(free)
    return None  # ohne Setgröße nicht sicher


def pick_group(
    group: list[_Open], set_size: int | None, free: list[int]
) -> list[tuple[_Open, int]]:
    """Mehrere offene Karten gleichen Namens, mehr freie Produkte (SV9a: Ho-Oh ex als SR und
    SAR, dazu die normale ex): Liegen alle über der Setgröße, sind es die letzten Produkte in
    Nummernreihenfolge; liegen alle darunter, die ersten. Gemischt bleibt es offen."""
    if set_size is None or len(free) < len(group):
        return []
    numbers = [_number_order(card.number) for card in group]
    if any(number[0] != 0 for number in numbers):
        return []
    ordered = sorted(group, key=lambda card: _number_order(card.number))
    products = sorted(free)
    if all(number[1] > set_size for number in numbers):
        return list(zip(ordered, products[-len(group) :], strict=True))
    if all(number[1] <= set_size for number in numbers):
        return list(zip(ordered, products[: len(group)], strict=True))
    return []


def choose_expansion(
    card_set: CardSet, keys: set[str], expansions: dict[int, _Expansion], taken: set[int]
) -> tuple[int, int] | None:
    """(Ausgabe, gemeinsame Namen) für ein kleines Set – nur bei klarem Sieger."""
    scored: list[tuple[float, int, int]] = []
    for expansion in expansions.values():
        if expansion.id in taken:
            continue
        common = len(keys & expansion.names.keys())
        if common < MIN_COMMON or common / len(keys) < MIN_SHARE:
            continue
        if (
            card_set.release_date
            and expansion.first_added
            and abs((expansion.first_added - card_set.release_date).days) > MAX_DATE_GAP_DAYS
        ):
            continue
        # Kleinere Ausgaben bevorzugen: ein Set, das ganz in einer Ausgabe steckt, passt besser
        # als dieselben Namen verteilt über eine große Sammelausgabe.
        scored.append((common / len(keys) + common / len(expansion.names), expansion.id, common))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][0] - scored[1][0] < LEAD:
        return None
    return scored[0][1], scored[0][2]


async def rescue_cardmarket(  # noqa: PLR0912, PLR0915 – ein Durchgang, Regeln oben
    session: AsyncSession, *, dry_run: bool = True, only_owned: bool = False
) -> RescueReport:
    """Offene Karten nachträglich zuordnen. ``only_owned``: nur Karten aus Sammlungen.
    Commit macht der Aufrufer."""
    report = RescueReport(dry_run=dry_run)
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
    sets = {
        s.id: s
        for s in (
            await session.scalars(
                select(CardSet).where(
                    CardSet.game == Game.POKEMON.value, CardSet.language.in_(MATCH_LANGUAGES)
                )
            )
        ).all()
    }
    rows = (
        await session.execute(
            select(
                Card.id,
                Card.set_id,
                Card.external_id,
                Card.language,
                Card.name,
                Card.name_en,
                Card.number,
                Card.number_norm,
                Card.cardmarket_product_id,
                Card.cardmarket_product_override,
            ).where(Card.set_id.in_(list(sets)))
        )
    ).all()
    owned: set[uuid.UUID] = set()
    if only_owned:
        owned = set(
            await session.scalars(
                select(CollectionItem.card_id).where(CollectionItem.card_id.is_not(None))
            )
        )
    used: defaultdict[uuid.UUID, set[int]] = defaultdict(set)  # Set → vergebene Produkte
    keys_of_set: defaultdict[uuid.UUID, set[str]] = defaultdict(set)
    open_cards: list[_Open] = []
    for row in rows:
        product = row.cardmarket_product_override or row.cardmarket_product_id
        name = english_name(row.name, row.language, english.get(row.external_id), row.name_en)
        key = name_key(name) if name else ""
        if key:
            keys_of_set[row.set_id].add(key)
        if product is not None:
            used[row.set_id].add(product)
        elif key and (not only_owned or row.id in owned):
            open_cards.append(_Open(row.id, row.set_id, row.number_norm, row.name, key))

    # 2. Sets ohne Ausgabe (mit offenen Karten)
    taken = {s.cardmarket_expansion_id for s in sets.values() if s.cardmarket_expansion_id}
    effective = {
        set_id: s.cardmarket_expansion_id
        for set_id, s in sets.items()
        if s.cardmarket_expansion_id is not None
    }
    for set_id in {card.set_id for card in open_cards}:
        card_set = sets[set_id]
        if card_set.cardmarket_expansion_id is not None:
            continue
        chosen = choose_expansion(card_set, keys_of_set[set_id], expansions, taken)
        label = f"{card_set.language}/{card_set.external_id} {card_set.name}"
        if chosen is None:
            report.still_open.append(f"{label}: keine eindeutige Cardmarket-Ausgabe")
            continue
        expansion_id, common = chosen
        taken.add(expansion_id)
        report.sets.append(
            f"{label} → Ausgabe {expansion_id} ({common}/{len(keys_of_set[set_id])} Namen, "
            f"z. B. „{expansions[expansion_id].sample}“)"
        )
        effective[set_id] = expansion_id  # für Schritt 1 (im Probelauf nur gedacht)
        if not dry_run:
            await link_set(session, card_set, expansion_id, ExpansionLinkSource.MATCHED)

    # 1. Karten: gleicher Name, Regeln siehe Modul-Doku
    by_set_key: defaultdict[tuple[uuid.UUID, str], list[_Open]] = defaultdict(list)
    for card in open_cards:
        by_set_key[(card.set_id, card.key)].append(card)
    updates: dict[uuid.UUID, int] = {}
    for (set_id, key), group in by_set_key.items():
        card_set = sets[set_id]
        expansion = expansions.get(effective.get(set_id, -1))
        products = expansion.names.get(key, []) if expansion else []
        free = [p for p in products if p not in used[set_id]]
        size = card_set.card_count_official
        if len(group) == len(free):
            group.sort(key=lambda card: _number_order(card.number))
            chosen_pairs = list(zip(group, sorted(free), strict=True))
        elif len(group) == 1:
            pick = pick_product(group[0].number, size, products, free)
            chosen_pairs = [(group[0], pick)] if pick is not None else []
        else:
            chosen_pairs = pick_group(group, size, free)
        if not chosen_pairs:
            for card in group:
                report.still_open.append(
                    f"{card_set.external_id} {card.number} {card.name}: "
                    + ("nicht in der Ausgabe" if not products else "mehrdeutig")
                )
            continue
        for card, product in chosen_pairs:
            updates[card.id] = product
            used[set_id].add(product)
    names = dict(
        (
            await session.execute(
                select(CmProduct.id_product, CmProduct.name).where(
                    CmProduct.id_product.in_(list(updates.values()))
                )
            )
        ).all()
    )
    cards_by_id = {card.id: card for card in open_cards}
    for card_id, product in updates.items():
        card = cards_by_id[card_id]
        report.cards.append(
            f"{sets[card.set_id].external_id} {card.number} {card.name} → {product} "
            f"„{names.get(product, '?')}“"
        )
    if not dry_run:
        for card_id, product in updates.items():
            await session.execute(
                update(Card).where(Card.id == card_id).values(cardmarket_product_id=product)
            )
    log.info(
        "cardmarket.rescue_done",
        sets=len(report.sets),
        cards=len(report.cards),
        open=len(report.still_open),
        dry_run=dry_run,
    )
    return report


def render_rescue_report(report: RescueReport) -> str:
    mode = "Probelauf, nichts gespeichert" if report.dry_run else "gespeichert"
    lines = [
        f"# Cardmarket: offene Karten zuordnen ({mode})",
        "",
        f"Sets mit Ausgabe: {len(report.sets)} · Karten zugeordnet: {len(report.cards)} · "
        f"weiter offen: {len(report.still_open)}",
        "",
    ]
    lines += [f"- Set: {line}" for line in report.sets]
    lines += [f"- {line}" for line in report.cards]
    if report.still_open:
        lines += ["", "Weiter offen:"] + [f"- {line}" for line in report.still_open[:60]]
    return "\n".join(lines) + "\n"


_VERSION_SUFFIX = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*$")


async def drop_contradicting_products(session: AsyncSession, *, dry_run: bool = True) -> list[str]:
    """Asiatische Karten, deren Cardmarket-Produkt nach Namen sicher eine andere Karte ist
    (siehe :func:`product_contradicts`): Produkt lösen, daraus übernommenen englischen Namen
    leeren, Cardmarket-Werte verwerfen. Eigene Wahl eines Nutzers bleibt. Commit macht der
    Aufrufer; Rückgabe: eine Zeile je Karte."""
    rows = (
        await session.execute(
            select(Card, CmProduct.name, CardSet.external_id)
            .join(CmProduct, CmProduct.id_product == Card.cardmarket_product_id)
            .join(CardSet, CardSet.id == Card.set_id)
            .where(
                Card.language.in_(TRANSLATED_LANGUAGES),
                Card.cardmarket_product_override.is_(None),
            )
        )
    ).all()
    lines = []
    for card, product_name, set_code in rows:
        if not contradicts_english(card.name, card.language, product_name):
            continue
        lines.append(
            f"{card.language} {set_code} {card.number} {card.name} ≠ "
            f"{card.cardmarket_product_id} „{product_name}“"
        )
        if dry_run:
            continue
        if card.name_en == _VERSION_SUFFIX.sub("", product_name)[:200]:
            card.name_en = None
        card.cardmarket_product_id = None
        await invalidate_cardmarket_prices(session, card_id=card.id)
    log.info("cardmarket.contradicting_products", cards=len(lines), dry_run=dry_run)
    return lines
