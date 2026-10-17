"""Nutzerverwaltung durch Admins: Nutzer, Einladungen, Passwort-Reset-Codes.

Jede ändernde Aktion landet im Audit-Log. Admins können sich nicht selbst sperren oder
herabstufen, und der letzte aktive Admin bleibt immer erhalten (Schutz vor Aussperren).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import generate_human_code, hash_password, hash_token
from app.models import InviteCode, PasswordResetToken, RefreshToken, Role, User
from app.services.audit import record_audit
from app.services.auth import Clock, normalize_email, utc_now
from app.services.errors import ConflictError, InvalidInputError, NotFoundError


@dataclass(frozen=True)
class IssuedCode[T]:
    """Ein frisch erzeugter Code. ``plain_code`` wird nur genau einmal angezeigt."""

    record: T
    plain_code: str


class AdminService:
    """Fachlogik des Admin-Bereichs. Commit übernimmt der Aufrufer."""

    def __init__(self, session: AsyncSession, settings: Settings, *, clock: Clock = utc_now):
        self._session = session
        self._settings = settings
        self._now = clock

    # ------------------------------------------------------------------ Nutzer

    async def create_user(
        self, *, email: str, password: str, display_name: str, role: Role = Role.USER
    ) -> User:
        """Legt ein Konto direkt an (nur für die Einrichtung per CLI, z. B. den ersten Admin)."""
        email = normalize_email(email)
        if await self._session.scalar(select(User.id).where(User.email == email)):
            raise ConflictError("Diese E-Mail ist bereits registriert.", code="email_taken")
        user = User(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
            role=role,
        )
        self._session.add(user)
        await self._session.flush()
        record_audit(
            self._session,
            action="user.created_by_cli",
            actor_id=None,
            target_user_id=user.id,
            details={"role": role.value},
        )
        return user

    async def list_users(self) -> Sequence[User]:
        result = await self._session.scalars(select(User).order_by(User.created_at))
        return result.all()

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._session.get(User, user_id)
        if user is None:
            raise NotFoundError("Nutzer nicht gefunden.")
        return user

    async def update_user(
        self,
        admin: User,
        user_id: uuid.UUID,
        *,
        is_active: bool | None = None,
        role: Role | None = None,
        ip: str | None = None,
    ) -> User:
        """Sperrt/entsperrt einen Nutzer oder ändert seine Rolle."""
        user = await self.get_user(user_id)
        if user.id == admin.id and (is_active is False or role is Role.USER):
            raise InvalidInputError(
                "Du kannst dich nicht selbst sperren oder herabstufen.", code="self_lockout"
            )
        losing_admin = user.role is Role.ADMIN and (is_active is False or role is Role.USER)
        if losing_admin and await self._active_admin_count() <= 1:
            raise InvalidInputError(
                "Der letzte aktive Admin kann nicht entfernt werden.", code="last_admin"
            )

        changes: dict[str, str | bool] = {}
        if is_active is not None and is_active != user.is_active:
            user.is_active = is_active
            changes["is_active"] = is_active
            if not is_active:
                await self._session.execute(
                    update(RefreshToken)
                    .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
                    .values(revoked_at=self._now())
                )
        if role is not None and role != user.role:
            user.role = role
            changes["role"] = role.value
        if changes:
            record_audit(
                self._session,
                action="admin.user_updated",
                actor_id=admin.id,
                target_user_id=user.id,
                ip=ip,
                details=changes,
            )
        return user

    async def _active_admin_count(self) -> int:
        count = await self._session.scalar(
            select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active)
        )
        return int(count or 0)

    # -------------------------------------------------------------- Einladungen

    async def create_invite(
        self, admin: User, *, note: str | None = None, ttl_days: int | None = None
    ) -> IssuedCode[InviteCode]:
        plain = generate_human_code()
        invite = InviteCode(
            id=uuid.uuid4(),
            code_hash=hash_token(plain),
            note=(note or "").strip()[:200] or None,
            created_by_id=admin.id,
            expires_at=self._now() + timedelta(days=ttl_days or self._settings.invite_ttl_days),
        )
        self._session.add(invite)
        await self._session.flush()
        record_audit(
            self._session,
            action="admin.invite_created",
            actor_id=admin.id,
            details={"invite_id": str(invite.id)},
        )
        return IssuedCode(record=invite, plain_code=plain)

    async def list_invites(self) -> Sequence[InviteCode]:
        result = await self._session.scalars(
            select(InviteCode).order_by(InviteCode.created_at.desc())
        )
        return result.all()

    async def revoke_invite(self, admin: User, invite_id: uuid.UUID) -> InviteCode:
        invite = await self._session.get(InviteCode, invite_id)
        if invite is None:
            raise NotFoundError("Einladung nicht gefunden.")
        if invite.used_at is not None:
            raise InvalidInputError("Die Einladung wurde bereits benutzt.", code="invite_used")
        if invite.revoked_at is None:
            invite.revoked_at = self._now()
            record_audit(
                self._session,
                action="admin.invite_revoked",
                actor_id=admin.id,
                details={"invite_id": str(invite.id)},
            )
        return invite

    # --------------------------------------------------------- Passwort-Reset

    async def create_password_reset(
        self, admin: User, user_id: uuid.UUID, *, ip: str | None = None
    ) -> IssuedCode[PasswordResetToken]:
        """Erzeugt einen Einmal-Code; ältere, unbenutzte Codes des Nutzers werden ungültig."""
        user = await self.get_user(user_id)
        now = self._now()
        await self._session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        plain = generate_human_code()
        token = PasswordResetToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_token(plain),
            created_by_id=admin.id,
            expires_at=now + timedelta(hours=self._settings.password_reset_ttl_hours),
        )
        self._session.add(token)
        await self._session.flush()
        record_audit(
            self._session,
            action="admin.password_reset_created",
            actor_id=admin.id,
            target_user_id=user.id,
            ip=ip,
        )
        return IssuedCode(record=token, plain_code=plain)
