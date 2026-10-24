"""Showcase: Ordner, die ein Nutzer für alle Freunde (alle angemeldeten Nutzer) freigibt.

**Was Freunde sehen:** Karten/Produkte, Fassung, Zustand, Slab, Menge und den aktuellen Wert.
**Was sie nie sehen:** Kaufpreis und -datum, Eigenpreis, Notizen, Gewinn und den Wert beim
Hinzufügen – die Ausgabe leert diese Felder (``ItemOut.public``). Nicht freigegebene Ordner
und deaktivierte Nutzer sind „nicht gefunden“ (404), genau wie unbekannte.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectionItem, Folder, User
from app.services.collection import CollectionService, ValuedItem
from app.services.errors import NotFoundError
from app.services.pricing import PriceService

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Showcase:
    owner: User
    folders: list[Folder]
    items: list[ValuedItem]

    @property
    def total_value(self) -> Decimal:
        return sum((i.value.total_value or ZERO for i in self.items), ZERO)

    @property
    def item_count(self) -> int:
        return sum(i.item.quantity for i in self.items)


class FriendsService:
    def __init__(self, session: AsyncSession, viewer: User, prices: PriceService) -> None:
        self._session = session
        self._viewer = viewer
        self._prices = prices

    async def _shared_folders(self, owner_ids: list[uuid.UUID] | None = None) -> list[Folder]:
        statement = (
            select(Folder)
            .join(User, User.id == Folder.user_id)
            .where(Folder.shared, User.is_active)
            .order_by(Folder.sort_order, Folder.name)
        )
        if owner_ids is not None:
            statement = statement.where(Folder.user_id.in_(owner_ids))
        return list((await self._session.scalars(statement)).all())

    async def showcase(self, owner_id: uuid.UUID, folder_id: uuid.UUID | None = None) -> Showcase:
        """Freigegebene Ordner eines Nutzers samt bewerteter Positionen (optional ein Ordner)."""
        folders = await self._shared_folders([owner_id])
        owner = await self._session.get(User, owner_id)
        if owner is None or not folders:
            raise NotFoundError("Keine freigegebene Sammlung gefunden.")
        if folder_id is not None and folder_id not in {f.id for f in folders}:
            raise NotFoundError("Ordner nicht gefunden.")
        shown = {folder_id} if folder_id else {f.id for f in folders}
        # Werte wie in der eigenen Ansicht des Besitzers (seine Preisdaten).
        valued = await CollectionService(self._session, owner, self._prices).valued_items()
        items = [v for v in valued if v.item.folder_id in shown]
        items.sort(key=lambda v: v.value.total_value or Decimal(-1), reverse=True)
        return Showcase(owner=owner, folders=folders, items=items)

    async def friends(self) -> list[Showcase]:
        """Alle Nutzer mit mindestens einem freigegebenen Ordner (ohne einen selbst)."""
        owner_ids = list(
            dict.fromkeys(
                f.user_id for f in await self._shared_folders() if f.user_id != self._viewer.id
            )
        )
        result = [await self.showcase(owner_id) for owner_id in owner_ids]
        result.sort(key=lambda s: s.owner.display_name.casefold())
        return result

    async def shared_item(self, item_id: uuid.UUID) -> ValuedItem:
        """Eine Position aus einem freigegebenen Ordner (für den Tausch-Rechner)."""
        item = await self._session.get(CollectionItem, item_id)
        if item is None:
            raise NotFoundError("Position nicht gefunden.")
        showcase = await self.showcase(item.user_id, item.folder_id)
        entry = next((v for v in showcase.items if v.item.id == item_id), None)
        if entry is None:
            raise NotFoundError("Position nicht gefunden.")
        return entry
