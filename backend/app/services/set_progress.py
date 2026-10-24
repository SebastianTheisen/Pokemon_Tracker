"""Set-Fortschritt: welche Karten eines Sets fehlen noch – auch als „Master-Set“.

* **Set:** jede Karte des Sets (Katalog, inkl. Secret Rares) zählt einmal – egal welche
  Fassung man besitzt.
* **Master-Set:** jede Fassung zählt einzeln. Je Karte gibt es den Hauptplatz (normal bzw.
  holo – in der Sammlung „normal“) und, wenn die Karte als Reverse Holo existiert, einen
  zweiten Platz „reverse“. Unbekannte Fassungen (``variants`` leer) zählen als ein Platz.
  1. Edition und Sonderstempel zählen nicht extra (in der Sammlung nicht unterscheidbar).
* Besitz zählt über alle Ordner und auch gegradete Karten (die Fassung steht an der Position).
* **Fehlt noch:** Summe der Near-Mint-Preise der fehlenden Plätze (nur Karten mit Preis).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CardSet, CollectionItem, User, WishlistItem
from app.services.alerts import card_value
from app.services.errors import InvalidInputError, NotFoundError
from app.services.pricing import CardPrices, PriceService

ZERO = Decimal("0.00")
MAX_BULK_WISHLIST = 500


def has_reverse(variants: dict[str, bool] | None) -> bool:
    return bool(variants and variants.get("reverse"))


def master_slots(variants: dict[str, bool] | None) -> int:
    """Plätze einer Karte im Master-Set: Hauptfassung + ggf. Reverse Holo."""
    return 1 + (1 if has_reverse(variants) else 0)


@dataclass(frozen=True)
class CardProgress:
    card: Card
    owned_normal: int
    owned_reverse: int
    on_wishlist: bool
    nm_value: Decimal | None
    reverse_value: Decimal | None

    @property
    def reverse(self) -> bool:
        return has_reverse(self.card.variants)

    @property
    def owned(self) -> bool:
        return self.owned_normal + self.owned_reverse > 0

    @property
    def master_owned(self) -> int:
        return int(self.owned_normal > 0) + int(self.reverse and self.owned_reverse > 0)

    @property
    def missing_value(self) -> Decimal:
        """Kosten der fehlenden Master-Plätze (soweit Preise bekannt)."""
        total = ZERO
        if self.owned_normal == 0 and self.nm_value is not None:
            total += self.nm_value
        if self.reverse and self.owned_reverse == 0 and self.reverse_value is not None:
            total += self.reverse_value
        return total


@dataclass(frozen=True)
class SetProgress:
    card_set: CardSet
    cards: list[CardProgress]

    @property
    def cards_total(self) -> int:
        return len(self.cards)

    @property
    def cards_owned(self) -> int:
        return sum(1 for c in self.cards if c.owned)

    @property
    def master_total(self) -> int:
        return sum(master_slots(c.card.variants) for c in self.cards)

    @property
    def master_owned(self) -> int:
        return sum(c.master_owned for c in self.cards)

    @property
    def missing_value(self) -> Decimal:
        """Was das Master-Set noch kostet (nur Karten mit Preis)."""
        return sum((c.missing_value for c in self.cards), ZERO)

    @property
    def missing_set_value(self) -> Decimal:
        """Was das Set (eine Fassung je Karte) noch kostet."""
        return sum((c.nm_value for c in self.cards if not c.owned and c.nm_value is not None), ZERO)


def _sort_key(card: Card) -> tuple[int, str, str]:
    """Nach Nummer: „2“ vor „10“, Buchstaben-Nummern (TG01, SV001) danach."""
    digits = "".join(ch for ch in card.number_norm if ch.isdigit())
    return (0 if card.number_norm.isdigit() else 1, digits.zfill(6), card.number_norm)


@dataclass(frozen=True)
class SetCounts:
    """Zahlen für die Set-Übersicht (ohne Kartenliste)."""

    cards_total: int
    master_total: int
    master_owned: int


async def owned_by_card(
    session: AsyncSession, owner: User, card_ids: Iterable[uuid.UUID] | None = None
) -> dict[tuple[uuid.UUID, str], int]:
    """Besessene Stückzahl je (Karte, Fassung) über alle Ordner."""
    statement = (
        select(CollectionItem.card_id, CollectionItem.variant, func.sum(CollectionItem.quantity))
        .where(CollectionItem.user_id == owner.id, CollectionItem.card_id.is_not(None))
        .group_by(CollectionItem.card_id, CollectionItem.variant)
    )
    if card_ids is not None:
        statement = statement.where(CollectionItem.card_id.in_(list(card_ids)))
    rows = await session.execute(statement)
    return {(card_id, variant): int(quantity) for card_id, variant, quantity in rows if card_id}


class SetProgressService:
    def __init__(self, session: AsyncSession, owner: User, prices: PriceService) -> None:
        self._session = session
        self._owner = owner
        self._prices = prices

    async def progress(self, set_id: uuid.UUID) -> SetProgress:
        card_set = await self._session.get(CardSet, set_id)
        if card_set is None:
            raise NotFoundError("Set nicht gefunden.")
        cards = sorted(
            (await self._session.scalars(select(Card).where(Card.set_id == set_id))).all(),
            key=_sort_key,
        )
        ids = [c.id for c in cards]
        owned = await owned_by_card(self._session, self._owner, ids)
        wished = set(
            (
                await self._session.scalars(
                    select(WishlistItem.card_id).where(
                        WishlistItem.user_id == self._owner.id, WishlistItem.card_id.in_(ids)
                    )
                )
            ).all()
        )
        prices: dict[uuid.UUID, CardPrices] = await self._prices.prices_for_cards(ids, self._owner)
        return SetProgress(
            card_set=card_set,
            cards=[
                CardProgress(
                    card=card,
                    owned_normal=owned.get((card.id, "normal"), 0),
                    owned_reverse=owned.get((card.id, "reverse"), 0),
                    on_wishlist=card.id in wished,
                    nm_value=card_value(prices.get(card.id), "normal", "NM"),
                    reverse_value=card_value(prices.get(card.id), "reverse", "NM"),
                )
                for card in cards
            ],
        )

    async def counts(self, set_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, SetCounts]:
        """Katalog- und Master-Zahlen für mehrere Sets (Übersicht) mit wenigen Abfragen."""
        if not set_ids:
            return {}
        rows = (
            await self._session.execute(
                select(Card.id, Card.set_id, Card.variants).where(Card.set_id.in_(set_ids))
            )
        ).all()
        owned = await owned_by_card(self._session, self._owner, [row[0] for row in rows])
        totals: dict[uuid.UUID, list[int]] = {}
        for card_id, set_id, variants in rows:
            entry = totals.setdefault(set_id, [0, 0, 0])
            entry[0] += 1
            entry[1] += master_slots(variants)
            entry[2] += int(owned.get((card_id, "normal"), 0) > 0) + int(
                has_reverse(variants) and owned.get((card_id, "reverse"), 0) > 0
            )
        return {
            set_id: SetCounts(cards_total=a, master_total=b, master_owned=c)
            for set_id, (a, b, c) in totals.items()
        }

    async def add_to_wishlist(self, card_ids: Sequence[uuid.UUID]) -> int:
        """Mehrere Karten (z. B. „alle fehlenden“) auf die Merkliste – vorhandene zählen nicht."""
        unique = list(dict.fromkeys(card_ids))
        if len(unique) > MAX_BULK_WISHLIST:
            raise InvalidInputError(f"Höchstens {MAX_BULK_WISHLIST} Karten auf einmal.")
        known = set((await self._session.scalars(select(Card.id).where(Card.id.in_(unique)))).all())
        if len(known) != len(unique):
            raise NotFoundError("Karte nicht gefunden.")
        present = set(
            (
                await self._session.scalars(
                    select(WishlistItem.card_id).where(
                        WishlistItem.user_id == self._owner.id, WishlistItem.card_id.in_(unique)
                    )
                )
            ).all()
        )
        added = [card_id for card_id in unique if card_id not in present]
        self._session.add_all(WishlistItem(user_id=self._owner.id, card_id=c) for c in added)
        await self._session.flush()
        return len(added)
