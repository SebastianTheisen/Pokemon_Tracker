"""Registrierung, Anmeldung, Token-Rotation, Passwortänderung und -Reset."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_secret,
    hash_password,
    hash_token,
    normalize_human_code,
    password_needs_rehash,
    verify_password,
)
from app.models import InviteCode, PasswordResetToken, RefreshToken, Role, User
from app.services.audit import record_audit
from app.services.errors import (
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    RateLimitedError,
)
from app.services.rate_limit import FailureLimiter

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class TokenPair:
    """Ergebnis einer erfolgreichen Anmeldung oder Token-Erneuerung."""

    access_token: str
    refresh_token: str
    expires_in: int
    user: User


class AuthService:
    """Fachlogik rund um Konten und Sitzungen. Commit übernimmt der Aufrufer."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        limiter: FailureLimiter | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._session = session
        self._settings = settings
        self._limiter = limiter
        self._now = clock

    # ------------------------------------------------------------------ Tokens

    async def _issue_tokens(
        self, user: User, *, family_id: uuid.UUID | None = None, user_agent: str | None = None
    ) -> tuple[TokenPair, RefreshToken]:
        now = self._now()
        access_ttl = timedelta(minutes=self._settings.access_token_ttl_minutes)
        refresh_secret = generate_secret()
        refresh = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_token(refresh_secret),
            family_id=family_id or uuid.uuid4(),
            expires_at=now + timedelta(days=self._settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:300] or None,
        )
        self._session.add(refresh)
        await self._session.flush()
        access = create_access_token(
            user_id=user.id,
            role=user.role.value,
            secret=self._settings.jwt_secret.get_secret_value(),
            ttl=access_ttl,
            now=now,
        )
        pair = TokenPair(
            access_token=access,
            refresh_token=refresh_secret,
            expires_in=int(access_ttl.total_seconds()),
            user=user,
        )
        return pair, refresh

    async def _revoke_all_refresh_tokens(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=self._now())
        )

    # ------------------------------------------------------------ Registrierung

    async def register(
        self,
        *,
        invite_code: str,
        email: str,
        password: str,
        display_name: str,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> TokenPair:
        """Legt ein Konto mit gültigem Einladungscode an und meldet direkt an."""
        now = self._now()
        invite = await self._session.scalar(
            select(InviteCode)
            .where(InviteCode.code_hash == hash_token(normalize_human_code(invite_code)))
            .with_for_update()  # verhindert doppelte Nutzung bei gleichzeitigen Anfragen
        )
        if invite is None or not invite.is_usable(now):
            raise InvalidInputError(
                "Einladungscode ist ungültig, abgelaufen oder bereits benutzt.",
                code="invalid_invite",
            )

        email = normalize_email(email)
        if await self._session.scalar(select(User.id).where(User.email == email)):
            raise ConflictError("Diese E-Mail ist bereits registriert.", code="email_taken")

        user = User(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
            role=Role.USER,
            last_login_at=now,
        )
        self._session.add(user)
        await self._session.flush()
        invite.used_at = now
        invite.used_by_id = user.id
        record_audit(
            self._session,
            action="user.registered",
            actor_id=user.id,
            target_user_id=user.id,
            ip=ip,
            details={"invite_id": str(invite.id)},
        )
        pair, _ = await self._issue_tokens(user, user_agent=user_agent)
        return pair

    # ----------------------------------------------------------------- Anmeldung

    async def login(
        self, *, email: str, password: str, ip: str | None = None, user_agent: str | None = None
    ) -> TokenPair:
        """Prüft E-Mail und Passwort. Unbekannte E-Mail und falsches Passwort sind
        für den Aufrufer nicht unterscheidbar (gleiche Meldung, gleiche Rechenzeit)."""
        email = normalize_email(email)
        limiter_key = f"{email}|{ip or '-'}"
        if self._limiter is not None and (wait := self._limiter.retry_after(limiter_key)):
            raise RateLimitedError(
                f"Zu viele Fehlversuche. Bitte in {wait} Sekunden erneut versuchen.",
                retry_after_seconds=wait,
            )

        user = await self._session.scalar(select(User).where(User.email == email))
        password_ok = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)
        if user is None or not password_ok or not user.is_active:
            if self._limiter is not None:
                self._limiter.register_failure(limiter_key)
            raise AuthenticationError(
                "E-Mail oder Passwort ist falsch.", code="invalid_credentials"
            )

        if self._limiter is not None:
            self._limiter.reset(limiter_key)
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = self._now()
        pair, _ = await self._issue_tokens(user, user_agent=user_agent)
        return pair

    async def refresh(self, *, refresh_token: str, user_agent: str | None = None) -> TokenPair:
        """Tauscht ein Refresh-Token gegen ein neues Paar (Rotation mit Diebstahlerkennung)."""
        now = self._now()
        stored = await self._session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(refresh_token))
            .with_for_update()
        )
        if stored is None:
            raise AuthenticationError("Sitzung ungültig. Bitte neu anmelden.", code="invalid_token")

        if stored.replaced_by_id is not None or stored.revoked_at is not None:
            # Ein bereits ersetztes Token taucht wieder auf → vermutlich kopiert/gestohlen.
            # Die gesamte Login-Familie wird gesperrt; beide Parteien müssen neu anmelden.
            if stored.replaced_by_id is not None:
                await self._session.execute(
                    update(RefreshToken)
                    .where(
                        RefreshToken.family_id == stored.family_id,
                        RefreshToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                record_audit(
                    self._session,
                    action="auth.refresh_token_reuse",
                    actor_id=stored.user_id,
                    target_user_id=stored.user_id,
                    details={"family_id": str(stored.family_id)},
                )
            raise AuthenticationError(
                "Sitzung ungültig. Bitte neu anmelden.",
                code="invalid_token",
                persist_changes=True,  # die Sperre muss trotz 401 gespeichert werden
            )

        if stored.expires_at <= now:
            raise AuthenticationError("Sitzung abgelaufen. Bitte neu anmelden.", code="expired")

        user = await self._session.get(User, stored.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Konto ist deaktiviert.", code="account_disabled")

        pair, new_token = await self._issue_tokens(
            user, family_id=stored.family_id, user_agent=user_agent or stored.user_agent
        )
        stored.replaced_by_id = new_token.id
        return pair

    async def logout(self, *, refresh_token: str) -> None:
        """Beendet die Sitzung. Unbekannte Tokens werden stillschweigend ignoriert."""
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_token(refresh_token),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=self._now())
        )

    # ------------------------------------------------------------- Passwörter

    async def change_password(
        self, user: User, *, current_password: str, new_password: str, ip: str | None = None
    ) -> None:
        """Ändert das Passwort und beendet alle Sitzungen des Nutzers."""
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError(
                "Das aktuelle Passwort ist falsch.", code="invalid_credentials"
            )
        user.password_hash = hash_password(new_password)
        await self._revoke_all_refresh_tokens(user.id)
        record_audit(
            self._session,
            action="user.password_changed",
            actor_id=user.id,
            target_user_id=user.id,
            ip=ip,
        )

    async def reset_password(self, *, code: str, new_password: str, ip: str | None = None) -> None:
        """Setzt das Passwort mit einem vom Admin erzeugten Einmal-Code neu."""
        now = self._now()
        token = await self._session.scalar(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == hash_token(normalize_human_code(code)))
            .with_for_update()
        )
        if token is None or token.used_at is not None or token.expires_at <= now:
            raise InvalidInputError(
                "Reset-Code ist ungültig, abgelaufen oder bereits benutzt.", code="invalid_code"
            )
        user = await self._session.get(User, token.user_id)
        if user is None or not user.is_active:
            raise InvalidInputError("Konto ist deaktiviert.", code="account_disabled")
        user.password_hash = hash_password(new_password)
        token.used_at = now
        await self._revoke_all_refresh_tokens(user.id)
        record_audit(
            self._session,
            action="user.password_reset",
            actor_id=user.id,
            target_user_id=user.id,
            ip=ip,
        )

    # --------------------------------------------------------- Eigene Sitzungen

    async def list_sessions(self, user: User) -> Sequence[RefreshToken]:
        """Aktive Sitzungen (je Login das jüngste Token) des angemeldeten Nutzers."""
        now = self._now()
        result = await self._session.scalars(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.replaced_by_id.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return result.all()

    async def revoke_session(self, user: User, session_id: uuid.UUID) -> None:
        """Beendet eine eigene Sitzung. Fremde Sitzungen gelten als „nicht gefunden“."""
        token = await self._session.scalar(
            select(RefreshToken).where(
                RefreshToken.id == session_id, RefreshToken.user_id == user.id
            )
        )
        if token is None:
            raise NotFoundError("Sitzung nicht gefunden.")
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=self._now())
        )
