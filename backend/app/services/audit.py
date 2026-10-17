"""Einträge ins Audit-Log schreiben."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def record_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    target_user_id: uuid.UUID | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Fügt einen Audit-Eintrag zur laufenden Transaktion hinzu (Commit macht der Aufrufer)."""
    session.add(
        AuditLog(
            action=action,
            actor_id=actor_id,
            target_user_id=target_user_id,
            ip=ip,
            details=details or {},
        )
    )
