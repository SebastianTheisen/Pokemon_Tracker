"""Nutzerkonto und Rollen."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Role(enum.StrEnum):
    """Rollen: ``user`` sieht nur eigene Daten, ``admin`` zusätzlich die Nutzerverwaltung."""

    USER = "user"
    ADMIN = "admin"


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Ein Nutzerkonto. Die E-Mail wird immer kleingeschrieben gespeichert."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        default=Role.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN
