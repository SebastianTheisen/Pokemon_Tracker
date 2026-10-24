"""Katalogsuche: Name (unscharf, Deutsch/Englisch gemischt) und/oder Kartennummer.

Ablauf für ``"nachtara 215"``:

1. Anfrage zerlegen → Name ``nachtara``, Nummer ``215``.
2. Karten finden, deren Name passt (Teilstring oder Trigramm-Ähnlichkeit ``<%``), optional
   gefiltert nach Nummer. Bester Score je TCGdex-ID.
3. Alle Sprachfassungen dieser IDs zurückgeben – so findet „Umbreon 215“ auch die deutsche
   „Nachtara VMAX“ und umgekehrt.

Setkürzel + Nummer wie auf der Karte („PFL077“, „pfl 77“, „SV8a-217“): Kürzel (offiziell,
:attr:`CardSet.code`) oder Set-ID, dann genau diese Nummer – in allen Sprachen.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, Subquery, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CardSet
from app.services.card_names import foreign_search_terms, translate_card_name
from app.services.catalog_numbers import ParsedQuery, normalize_number, parse_query
from app.services.errors import NotFoundError

DEFAULT_LIMIT = 30
MAX_LIMIT = 100
_CODE_REST = re.compile(r"^\d{1,3}[a-z]?$")
_MAX_CODE = 8
MAX_CODE_QUERY_WORDS = 4


@dataclass(frozen=True)
class SearchHit:
    """Ein Treffer mit Relevanz (0..1)."""

    card: Card
    score: float


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _name_condition(term: str) -> ColumnElement[bool]:
    lowered = func.lower(Card.name)
    return or_(
        lowered.like(f"%{_escape_like(term)}%", escape="\\"),
        literal(term).op("<%")(lowered),  # pg_trgm: Wort-Ähnlichkeit ≥ Schwelle (0,6)
    )


def _name_score(term: str) -> ColumnElement[float]:
    return func.word_similarity(literal(term), func.lower(Card.name))


def _ordered(statement: Select[Card], limit: int) -> Select[Card]:
    return (
        statement.join(Card.card_set)
        .order_by(CardSet.release_date.desc().nulls_last(), Card.number_norm)
        .limit(limit)
    )


async def search_cards(
    session: AsyncSession,
    query: str,
    *,
    language: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchHit]:
    """Sucht Karten. ``language`` filtert die Ergebnisse auf eine Sprache."""
    limit = max(1, min(limit, MAX_LIMIT))
    by_code = await _search_set_code(session, query, language=language, limit=limit)
    if by_code:
        return by_code
    parsed: ParsedQuery = parse_query(query)
    if parsed.is_empty:
        return []

    filters: list[ColumnElement[bool]] = []
    if parsed.number is not None:
        filters.append(Card.number_norm == parsed.number)
    if language is not None:
        result_language_filter: list[ColumnElement[bool]] = [Card.language == language]
    else:
        result_language_filter = []

    if not parsed.name:  # nur Nummer
        rows = await session.scalars(
            _ordered(select(Card).where(*filters, *result_language_filter), limit)
        )
        return [SearchHit(card=card, score=1.0) for card in rows.unique()]

    # Deutsch/Englisch → auch asiatische Pokémon-Namen suchen („pikachu“ findet „ピカチュウ“).
    # Alle Schreibweisen in einer Abfrage (früher je Schreibweise zwei – unter Last zu langsam).
    terms = list(dict.fromkeys([parsed.name.casefold(), *foreign_search_terms(parsed.name)]))
    hits: dict[uuid.UUID, SearchHit] = {}
    for hit in await _hits_for_terms(session, terms, filters, result_language_filter, limit):
        known = hits.get(hit.card.id)
        if known is None or known.score < hit.score:
            hits[hit.card.id] = hit
    ordered = list(hits.values())
    ordered.sort(
        key=lambda hit: (
            -hit.score,
            -(hit.card.card_set.release_date.toordinal() if hit.card.card_set.release_date else 0),
            hit.card.external_id or "",
            hit.card.language,
        )
    )
    return ordered[:limit]


def code_candidates(query: str) -> list[tuple[str, str]]:
    """Mögliche Aufteilungen in (Kürzel, Nummer): „PFL077“ → [(„pfl“, „077“), …]."""
    compact = re.sub(r"[\s-]+", "", query.casefold())
    candidates = []
    for split in range(2, min(len(compact), _MAX_CODE) + 1):
        code, rest = compact[:split], compact[split:]
        if any(char.isalpha() for char in code) and _CODE_REST.match(rest):
            candidates.append((code, rest))
    return candidates


def code_parts(query: str) -> list[tuple[list[tuple[str, str]], str]]:
    """Mögliche Lesarten „Kürzel + Nummer (+ Name)“: „nachtara s6a 095“ →
    Kandidaten aus „s6a 095“ bzw. „s6a095“ und der Rest „nachtara“ als Name."""
    tokens = query.split()
    readings = []
    for start in range(len(tokens)):
        for size in (2, 1):
            part = tokens[start : start + size]
            if len(part) != size:
                continue
            candidates = code_candidates("".join(part))
            if candidates:
                rest = " ".join(tokens[:start] + tokens[start + size :])
                readings.append((candidates, rest))
    return readings


def _name_matches(card: Card, name: str) -> bool:
    """Grenzt Kürzel-Treffer ein: Name (auch übersetzt, z. B. „ブラッキー“ ↔ „Nachtara“)."""
    wanted = name.casefold()
    names = [card.name, translate_card_name(card.name, card.language) or ""]
    return any(wanted in candidate.casefold() for candidate in names if candidate)


async def _search_set_code(
    session: AsyncSession, query: str, *, language: str | None, limit: int
) -> list[SearchHit]:
    """„PFL077“, „s6a 095“, „nachtara s6a 095“: Karten mit dieser Nummer im Set mit diesem
    Kürzel (längstes Kürzel gewinnt); weitere Wörter grenzen über den Namen ein."""
    if len(query.split()) > MAX_CODE_QUERY_WORDS:
        return []
    for candidates, name in code_parts(query):
        codes = [code for code, _ in candidates]
        rows = (
            await session.execute(
                select(CardSet.id, func.lower(CardSet.code), func.lower(CardSet.external_id)).where(
                    or_(
                        func.lower(CardSet.code).in_(codes),
                        func.lower(CardSet.external_id).in_(codes),
                    )
                )
            )
        ).all()
        for code, rest in reversed(candidates):  # längstes Kürzel zuerst
            set_ids = [row[0] for row in rows if code in (row[1], row[2])]
            if not set_ids:
                continue
            statement = select(Card).where(
                Card.set_id.in_(set_ids), Card.number_norm == normalize_number(rest)
            )
            if language is not None:
                statement = statement.where(Card.language == language)
            cards = list((await session.scalars(_ordered(statement, limit))).unique())
            if name:
                # Name passt nicht? Kürzel und Nummer sind eindeutiger – dann alle zeigen.
                cards = [card for card in cards if _name_matches(card, name)] or cards
            if cards:
                return [SearchHit(card=card, score=1.0) for card in cards]
    return []


def _matches(terms: Sequence[str], *where: ColumnElement[bool]) -> Subquery:
    """(Karten-ID, externe ID, Score) je Schreibweise – als ``UNION ALL`` statt einer
    OR-Bedingung: so nutzt jede Schreibweise den Trigramm-Index (mit OR liest Postgres alle
    Karten, Lasttest Phase 6)."""
    branches = [
        select(
            Card.id.label("card_id"),
            Card.external_id.label("external_id"),
            _name_score(term).label("score"),
        ).where(_name_condition(term), *where)
        for term in terms
    ]
    return (branches[0] if len(branches) == 1 else union_all(*branches)).subquery()


async def _hits_for_terms(
    session: AsyncSession,
    terms: Sequence[str],
    filters: list[ColumnElement[bool]],
    result_language_filter: list[ColumnElement[bool]],
    limit: int,
) -> list[SearchHit]:
    """Treffer für mehrere Schreibweisen (Name + Übersetzungen); Score = beste Schreibweise."""
    # 1) Beste Ähnlichkeit je TCGdex-ID (über alle Sprachen).
    found = _matches(terms, Card.external_id.is_not(None), *filters)
    best = func.max(found.c.score)
    matched = (
        select(found.c.external_id.label("external_id"), best.label("score"))
        .group_by(found.c.external_id)
        .order_by(best.desc())
        .limit(limit)
        .subquery()
    )
    linked = await session.execute(
        select(Card, matched.c.score)
        .join(matched, Card.external_id == matched.c.external_id)
        .where(*result_language_filter)
    )
    hits = [SearchHit(card=card, score=float(hit_score)) for card, hit_score in linked.unique()]

    # 2) Selbst angelegte Karten (ohne TCGdex-ID) direkt über ihren Namen.
    own_found = _matches(terms, Card.external_id.is_(None), *filters, *result_language_filter)
    own_best = (
        select(own_found.c.card_id, func.max(own_found.c.score).label("score"))
        .group_by(own_found.c.card_id)
        .limit(limit)
        .subquery()
    )
    own = await session.execute(
        select(Card, own_best.c.score).join(own_best, Card.id == own_best.c.card_id)
    )
    hits += [SearchHit(card=card, score=float(hit_score)) for card, hit_score in own.unique()]
    return hits


async def get_card(session: AsyncSession, card_id: uuid.UUID) -> Card:
    card = await session.get(Card, card_id)
    if card is None:
        raise NotFoundError("Karte nicht gefunden.")
    return card


async def list_sets(session: AsyncSession, language: str | None = None) -> Sequence[CardSet]:
    statement = select(CardSet).order_by(CardSet.release_date.desc().nulls_last(), CardSet.name)
    if language is not None:
        statement = statement.where(CardSet.language == language)
    result = await session.scalars(statement)
    return result.all()
