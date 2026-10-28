"""Sammlung aus einem Collectr-Showcase übernehmen.

Das Lesezeichen „Collectr → Kartenkiste“ liest die öffentliche Showcase-Seite so aus, wie sie
im Browser steht (je Karte die sichtbaren Textzeilen), und gibt sie der App. Kartenkiste
ruft Collectr nie selbst ab. Ausgewertet wird hier, damit sich Regeln ohne neues Lesezeichen
ändern lassen.

Eine Kachel sieht so aus (Zeilen)::

    Espeon V (JP)
    Eevee Heroes
    Secret Rare • 081/069
    Near Mint • Holofoil
    $169.02
    $0.00 (0,00%)
    Qty: 2

Gegradete Karten haben keine Zustandszeile (Firma und Note stehen nur im Bild).

Zuordnung zum Katalog: Kartennummer, dann Setgröße („/069“ bzw. Promo-Kürzel „/SM-P“),
englischer Setname und englischer Kartenname. „(JP)“ steht bei neueren japanischen Sets
nicht immer dabei – gesucht wird daher in Japanisch und Englisch, die Sprache gibt nur
einen kleinen Ausschlag.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CardSet, CollectionItem, Folder, Game, GradingCompany, User
from app.services.card_names import translate_card_name
from app.services.catalog_numbers import normalize_number
from app.services.collection import CollectionService, ItemInput
from app.services.display_names import translated_set_title
from app.services.errors import InvalidInputError

LANGUAGES = ("ja", "en")
MAX_ROWS = 1500
MAX_MATCHES = 5

# TCGplayer-Zustände (Collectr) → Cardmarket-Skala der App
CONDITIONS = {
    "near mint": "NM",
    "lightly played": "EX",
    "moderately played": "LP",
    "heavily played": "PL",
    "damaged": "PO",
}

# Gewichte der Zuordnung (Summe 1,0 ohne Sprache)
WEIGHT_TOTAL = 0.35
WEIGHT_SET = 0.35
WEIGHT_NAME = 0.25
BONUS_LANGUAGE = 0.05
MATCHED_SCORE = 0.75  # ab hier gilt ein Treffer als zugeordnet …
MATCHED_LEAD = 0.1  # … wenn der Zweite so weit dahinter liegt
CHECK_SCORE = 0.35  # darunter taugt ein Kandidat nicht einmal zum Prüfen

# „Espeon V (JP)“, „Sun & Moon Promos (JP)“, aber auch „Scarlet & Violet Promo JP“
_JP_TAG = re.compile(r"\s*(?:\(JP\)|\bJP)\s*$", re.IGNORECASE)
_QTY = re.compile(r"^Qty:\s*(\d+)$", re.IGNORECASE)
# Preise in jeder Währung, die Collectr anbietet ($, €, £, ¥ …) und Veränderung in %
_PRICE = re.compile(r"^[+\-−▲▼]?\s*[$€£¥₩]|^[+\-−]?\s*[\d.,]+\s*[$€£¥₩]$|%\)?$")
_NUMBER = re.compile(r"^#?([A-Za-z]{0,6}-?\d{1,4}[A-Za-z]?)(?:/([A-Za-z0-9-]+))?$")
_KEY = re.compile(r"[^a-z0-9]+")
_VARIANT_ONLY = re.compile(
    r"^(?:reverse holofoil|holofoil|normal|1st edition(?: holofoil)?|unlimited(?: holofoil)?)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CollectrRow:
    """Eine ausgewertete Kachel."""

    name: str
    set_name: str
    rarity: str | None
    number: str | None
    total: str | None
    condition: str | None
    variant: str
    quantity: int
    graded: bool
    japanese: bool

    @property
    def number_norm(self) -> str | None:
        return normalize_number(self.number) if self.number else None


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", line)).strip()


def _rarity_number(line: str) -> tuple[str | None, str, str | None] | None:
    """„Secret Rare • 081/069“ → (Seltenheit, Nummer, Setgröße); auch nur „085“."""
    left, _, right = line.rpartition("•")
    match = _NUMBER.match(right.strip())
    if match is None:
        return None
    return (left.strip() or None), match.group(1), match.group(2)


def _merge_lines(lines: Sequence[str]) -> list[str]:
    """Zeilen wieder zusammensetzen, die der Browser getrennt liefert (Flex-Layout):
    „Secret Rare“ / „•“ / „081/069“ → „Secret Rare • 081/069“, „Qty:“ / „2“ → „Qty: 2“."""
    merged: list[str] = []
    glue = False
    for raw in lines:
        line = _clean(raw)
        if not line:
            continue
        if merged and (glue or line.startswith("•") or merged[-1] == "Qty:"):
            merged[-1] = _clean(f"{merged[-1]} {line}")
        else:
            merged.append(line)
        glue = line.endswith("•")
    return merged


def parse_row(lines: Sequence[str]) -> CollectrRow | None:
    """Kachel-Zeilen auswerten; ``None``, wenn es keine Karte ist (kein Name, keine Nummer)."""
    texts: list[str] = []
    rarity = number = total = condition = None
    variant, quantity, condition_seen = "normal", 1, False
    for line in _merge_lines(lines):
        if _PRICE.search(line):
            continue
        if condition_seen and _VARIANT_ONLY.match(line):  # Variante als eigene Zeile
            variant = "reverse" if "reverse" in line.casefold() else variant
            continue
        if qty := _QTY.match(line):
            quantity = max(1, int(qty.group(1)))
            continue
        head, _, tail = line.partition("•")
        if (code := CONDITIONS.get(head.strip().casefold())) is not None:
            condition, condition_seen = code, True
            variant = "reverse" if "reverse" in tail.casefold() else "normal"
            continue
        if (
            number is None
            and (parsed := _rarity_number(line)) is not None
            and ("•" in line or texts)
        ):
            rarity, number, total = parsed
            continue
        texts.append(line)
    if len(texts) < 1 or number is None:
        return None
    name = texts[0]
    set_name = texts[1] if len(texts) > 1 else ""
    japanese = bool(_JP_TAG.search(name) or _JP_TAG.search(set_name))
    return CollectrRow(
        name=_JP_TAG.sub("", name),
        set_name=_JP_TAG.sub("", set_name),
        rarity=rarity,
        number=number,
        total=total,
        condition=condition,
        variant=variant,
        quantity=quantity,
        graded=not condition_seen,
        japanese=japanese,
    )


def _key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold().replace("&", "and"))
    return _KEY.sub("", "".join(c for c in text if not unicodedata.combining(c)))


def _similarity(a: str, b: str) -> float:
    key_a, key_b = _key(a), _key(b)
    if not key_a or not key_b:
        return 0.0
    if key_a == key_b:
        return 1.0
    return SequenceMatcher(None, key_a, key_b).ratio()


def english_card_name(card: Card) -> str:
    """Englischer Name zum Vergleich mit Collectr (TCGplayer-Namen sind englisch)."""
    if card.language == "en":
        return card.name
    return translate_card_name(card.name, card.language, "en") or card.name_en or card.name


def english_set_name(card_set: CardSet) -> str:
    return translated_set_title(card_set) or card_set.name


def total_matches(row: CollectrRow, card_set: CardSet) -> bool:
    """Passt die Setgröße („/069“) bzw. das Promo-Kürzel („/SM-P“)?"""
    if not row.total:
        return False
    if row.total.isdigit():
        size = int(row.total)
        return size in {card_set.card_count_official, card_set.card_count_total}
    code = row.total.casefold()
    return code in {card_set.external_id.casefold(), (card_set.code or "").casefold()}


@dataclass(frozen=True)
class CandidateScore:
    card: Card
    score: float


def score_card(row: CollectrRow, card: Card) -> float:
    score = WEIGHT_TOTAL * total_matches(row, card.card_set)
    score += WEIGHT_SET * _similarity(row.set_name, english_set_name(card.card_set))
    # Ohne Setgröße (Promos wie „085“) zählt der Name dafür mehr.
    name_weight = WEIGHT_NAME + (0.0 if row.total else WEIGHT_TOTAL)
    score += name_weight * _similarity(row.name, english_card_name(card))
    if (card.language == "ja") == row.japanese:
        score += BONUS_LANGUAGE
    return round(score, 3)


RowStatus = Literal["matched", "check", "missing"]


@dataclass
class RowResult:
    index: int
    row: CollectrRow
    status: RowStatus
    matches: list[CandidateScore] = field(default_factory=list)


def classify(index: int, row: CollectrRow, cards: Sequence[Card]) -> RowResult:
    """Kandidaten bewerten und einordnen: sicher zugeordnet, prüfen oder nicht gefunden."""
    scored = sorted(
        (CandidateScore(card, score_card(row, card)) for card in cards),
        key=lambda c: -c.score,
    )
    scored = [c for c in scored if c.score >= CHECK_SCORE][:MAX_MATCHES]
    if not scored:
        return RowResult(index, row, "missing")
    best = scored[0]
    lead = best.score - scored[1].score if len(scored) > 1 else 1.0
    status: RowStatus = (
        "matched" if best.score >= MATCHED_SCORE and lead >= MATCHED_LEAD else "check"
    )
    return RowResult(index, row, status, scored)


@dataclass(frozen=True)
class ImportItem:
    card_id: uuid.UUID
    quantity: int
    condition: str | None
    variant: str
    grading_company: GradingCompany | None
    grade: str | None


# Karte, Variante, Zustand, Grading-Firma, Note – was eine Position eindeutig macht
_ItemKey = tuple[uuid.UUID, str, str | None, GradingCompany | None, str | None]


@dataclass(frozen=True)
class CommitResult:
    folder: Folder
    added: int
    skipped: int


class CollectrImport:
    """Vorschau und Übernahme für *einen* Nutzer."""

    def __init__(self, session: AsyncSession, user: User, collection: CollectionService) -> None:
        self._session = session
        self._user = user
        self._collection = collection

    async def _cards_by_number(self, numbers: set[str]) -> dict[str, list[Card]]:
        found: dict[str, list[Card]] = defaultdict(list)
        if not numbers:
            return found
        cards = (
            await self._session.scalars(
                select(Card)
                .join(CardSet, Card.set_id == CardSet.id)
                .where(
                    Card.number_norm.in_(numbers),
                    Card.language.in_(LANGUAGES),
                    CardSet.game == Game.POKEMON.value,
                )
            )
        ).unique()
        for card in cards:
            found[card.number_norm].append(card)
        return found

    async def preview(self, rows: Sequence[Sequence[str]]) -> list[RowResult]:
        if len(rows) > MAX_ROWS:
            raise InvalidInputError(f"Höchstens {MAX_ROWS} Karten auf einmal.")
        parsed = [(index, row) for index, lines in enumerate(rows) if (row := parse_row(lines))]
        by_number = await self._cards_by_number(
            {norm for _, row in parsed if (norm := row.number_norm)}
        )
        return [
            classify(index, row, by_number.get(row.number_norm or "", [])) for index, row in parsed
        ]

    async def _folder(self, name: str) -> Folder:
        name = _clean(name)[:80] or "Collectr"
        for folder in await self._collection.list_folders():
            if folder.name.casefold() == name.casefold():
                return folder
        return await self._collection.create_folder(name)

    async def commit(self, folder_name: str, items: Sequence[ImportItem]) -> CommitResult:
        """Positionen anlegen; was im Ordner schon genauso liegt, wird übersprungen (ein
        zweiter Durchlauf legt nichts doppelt an)."""
        if len(items) > MAX_ROWS:
            raise InvalidInputError(f"Höchstens {MAX_ROWS} Karten auf einmal.")
        folder = await self._folder(folder_name)
        existing: set[_ItemKey] = {
            (item.card_id, item.variant, item.condition, item.grading_company, item.grade)
            for item in await self._session.scalars(
                select(CollectionItem).where(
                    CollectionItem.user_id == self._user.id,
                    CollectionItem.folder_id == folder.id,
                )
            )
            if item.card_id is not None
        }
        # Gleiche Karte mehrfach im Showcase (z. B. zweimal einzeln angelegt): eine Position
        # mit zusammengezählter Menge – nicht als „schon vorhanden“ überspringen.
        merged: dict[_ItemKey, int] = {}
        for item in items:
            graded = item.grading_company is not None
            condition = None if graded else (item.condition or "NM")
            grade = item.grade if graded else None
            key = (item.card_id, item.variant, condition, item.grading_company, grade)
            merged[key] = merged.get(key, 0) + item.quantity
        added = skipped = 0
        for key, quantity in merged.items():
            if key in existing:
                skipped += 1
                continue
            card_id, variant, condition, company, grade = key
            await self._collection.add_item(
                ItemInput(
                    folder_id=folder.id,
                    card_id=card_id,
                    variant=variant,
                    condition=condition,
                    quantity=min(quantity, 9999),
                    grading_company=company,
                    grade=grade,
                ),
                refresh_prices=False,
            )
            added += 1
        return CommitResult(folder=folder, added=added, skipped=skipped)
