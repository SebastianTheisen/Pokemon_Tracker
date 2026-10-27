"""Spiele (Pokémon, One Piece): Zuordnung von Positionen und Filter in Abfragen.

Karten erben das Spiel von ihrem Set. Versiegeltes hängt am Set (falls bekannt) oder am
Cardmarket-Produkt, aus dessen Download es stammt; ohne beides gilt Pokémon (Bestand).
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import ColumnElement, func, literal, select
from sqlalchemy.orm import aliased

from app.models import Card, CardSet, CmProduct, CollectionItem, Game, Product

GameName = Literal["pokemon", "onepiece"]
DEFAULT_GAME = Game.POKEMON.value
GAME_LABELS = {Game.POKEMON.value: "Pokémon", Game.ONEPIECE.value: "One Piece"}


def item_game() -> ColumnElement[str]:
    """Spiel einer Position als SQL-Ausdruck (korreliert mit :class:`CollectionItem`).

    Eigene Aliase in den Unterabfragen: Die äußere Abfrage verbindet ``Card``/``Product``
    oft schon selbst – ohne Alias würde SQLAlchemy die Unterabfrage dorthin korrelieren.
    """
    card, card_set = aliased(Card), aliased(CardSet)
    product, product_set, cm_product = aliased(Product), aliased(CardSet), aliased(CmProduct)
    card_game = (
        select(card_set.game)
        .join(card, card.set_id == card_set.id)
        .where(card.id == CollectionItem.card_id)
        .correlate(CollectionItem)
        .scalar_subquery()
    )
    product_set_game = (
        select(product_set.game)
        .join(product, product.set_id == product_set.id)
        .where(product.id == CollectionItem.product_id)
        .correlate(CollectionItem)
        .scalar_subquery()
    )
    product_cm_game = (
        select(cm_product.game)
        .join(product, product.cardmarket_product_id == cm_product.id_product)
        .where(product.id == CollectionItem.product_id)
        .correlate(CollectionItem)
        .scalar_subquery()
    )
    return func.coalesce(card_game, product_set_game, product_cm_game, literal(DEFAULT_GAME))


def card_game(card: Card) -> str:
    """Spiel einer Karte (über ihr Set)."""
    return card.card_set.game or DEFAULT_GAME
