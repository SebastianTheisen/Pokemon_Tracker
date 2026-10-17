"""API-Tests: Registrierung, Anmeldung, Token-Rotation, Passwörter, Sitzungen."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AuditLog, InviteCode, RefreshToken
from tests.conftest import DEFAULT_PASSWORD, Account, RegisterUser

API = "/api/v1"


async def _new_invite(client: AsyncClient, admin: Account) -> str:
    response = await client.post(
        f"{API}/admin/invites", json={"note": "Test"}, headers=admin.headers
    )
    assert response.status_code == 201
    code: str = response.json()["code"]
    return code


def _register_body(code: str, email: str = "max@example.com") -> dict[str, str]:
    return {
        "invite_code": code,
        "email": email,
        "password": DEFAULT_PASSWORD,
        "display_name": "Max",
    }


# ------------------------------------------------------------------ Registrierung


async def test_register_with_invite_logs_in_and_consumes_code(
    client: AsyncClient, admin: Account
) -> None:
    code = await _new_invite(client, admin)

    response = await client.post(f"{API}/auth/register", json=_register_body(code.lower()))

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "max@example.com"
    assert body["user"]["role"] == "user"
    assert body["token_type"] == "bearer"
    me = await client.get(f"{API}/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["display_name"] == "Max"

    again = await client.post(f"{API}/auth/register", json=_register_body(code, "b@example.com"))
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_invite"


async def test_register_rejects_unknown_revoked_and_expired_codes(
    client: AsyncClient, admin: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    unknown = await client.post(f"{API}/auth/register", json=_register_body("AAAAA-BBBBB"))
    assert unknown.status_code == 400

    revoked_code = await _new_invite(client, admin)
    invites = (await client.get(f"{API}/admin/invites", headers=admin.headers)).json()
    await client.delete(f"{API}/admin/invites/{invites[0]['id']}", headers=admin.headers)
    revoked = await client.post(f"{API}/auth/register", json=_register_body(revoked_code))
    assert revoked.status_code == 400

    expired_code = await _new_invite(client, admin)
    async with session_factory() as session:
        await session.execute(
            update(InviteCode)
            .where(InviteCode.revoked_at.is_(None))
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
    expired = await client.post(f"{API}/auth/register", json=_register_body(expired_code))
    assert expired.status_code == 400


async def test_register_rejects_taken_email_and_weak_password(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    await register_user("max@example.com")

    taken = await client.post(
        f"{API}/auth/register",
        json=_register_body(await _new_invite(client, admin), "MAX@example.com"),
    )
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "email_taken"

    weak = await client.post(
        f"{API}/auth/register",
        json=_register_body(await _new_invite(client, admin), "neu@example.com")
        | {"password": "kurz"},
    )
    assert weak.status_code == 422


# ----------------------------------------------------------------------- Anmeldung


async def test_login_errors_do_not_reveal_whether_email_exists(
    client: AsyncClient, admin: Account
) -> None:
    wrong_password = await client.post(
        f"{API}/auth/login", json={"email": admin.email, "password": "falsch-falsch"}
    )
    unknown_email = await client.post(
        f"{API}/auth/login", json={"email": "nobody@example.com", "password": "falsch-falsch"}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.headers["www-authenticate"] == "Bearer"


async def test_login_is_rate_limited_after_failures(client: AsyncClient, admin: Account) -> None:
    for _ in range(3):  # Limit in den Test-Settings: 3
        await client.post(f"{API}/auth/login", json={"email": admin.email, "password": "x" * 10})

    blocked = await client.post(
        f"{API}/auth/login", json={"email": admin.email, "password": admin.password}
    )

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


async def test_requests_without_or_with_bad_token_are_rejected(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/me")).status_code == 401
    bad = await client.get(f"{API}/me", headers={"Authorization": "Bearer kaputt"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_token"


# ---------------------------------------------------------- Rotation & Diebstahl


async def test_refresh_rotates_token(client: AsyncClient, register_user: RegisterUser) -> None:
    user = await register_user("max@example.com")

    first = await client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    assert first.status_code == 200
    new_refresh = first.json()["refresh_token"]
    assert new_refresh != user.refresh_token

    second = await client.post(f"{API}/auth/refresh", json={"refresh_token": new_refresh})
    assert second.status_code == 200


async def test_reused_refresh_token_revokes_whole_family(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    rotated = (
        await client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    ).json()["refresh_token"]

    # Angreifer legt das alte (bereits ersetzte) Token vor …
    reuse = await client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    assert reuse.status_code == 401

    # … danach ist auch das neue Token des echten Nutzers gesperrt (Sperre wurde gespeichert).
    victim = await client.post(f"{API}/auth/refresh", json={"refresh_token": rotated})
    assert victim.status_code == 401
    async with session_factory() as session:
        actions = (await session.scalars(select(AuditLog.action))).all()
        active = (
            await session.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == user.user_id, RefreshToken.revoked_at.is_(None)
                )
            )
        ).all()
    assert "auth.refresh_token_reuse" in actions
    assert active == []


async def test_logout_invalidates_refresh_token(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")

    logout = await client.post(f"{API}/auth/logout", json={"refresh_token": user.refresh_token})
    assert logout.status_code == 204

    refresh = await client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    assert refresh.status_code == 401


# --------------------------------------------------------------------- Passwörter


async def test_change_password_requires_current_and_ends_sessions(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")

    wrong = await client.post(
        f"{API}/me/password",
        json={"current_password": "falsch-falsch", "new_password": "neues-passwort-123"},
        headers=user.headers,
    )
    assert wrong.status_code == 401

    ok = await client.post(
        f"{API}/me/password",
        json={"current_password": user.password, "new_password": "neues-passwort-123"},
        headers=user.headers,
    )
    assert ok.status_code == 204
    refresh = await client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    assert refresh.status_code == 401
    login = await client.post(
        f"{API}/auth/login", json={"email": user.email, "password": "neues-passwort-123"}
    )
    assert login.status_code == 200


async def test_admin_password_reset_flow(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")
    reset = await client.post(
        f"{API}/admin/users/{user.user_id}/password-reset", headers=admin.headers
    )
    assert reset.status_code == 201
    code = reset.json()["code"]

    response = await client.post(
        f"{API}/auth/reset-password", json={"code": code, "new_password": "nach-dem-reset-1"}
    )
    assert response.status_code == 204
    reused = await client.post(
        f"{API}/auth/reset-password", json={"code": code, "new_password": "noch-ein-anderes-1"}
    )
    assert reused.status_code == 400
    login = await client.post(
        f"{API}/auth/login", json={"email": user.email, "password": "nach-dem-reset-1"}
    )
    assert login.status_code == 200
    old_session = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": user.refresh_token}
    )
    assert old_session.status_code == 401


async def test_new_reset_code_invalidates_previous_one(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")
    url = f"{API}/admin/users/{user.user_id}/password-reset"
    first = (await client.post(url, headers=admin.headers)).json()["code"]
    await client.post(url, headers=admin.headers)

    response = await client.post(
        f"{API}/auth/reset-password", json={"code": first, "new_password": "nach-dem-reset-1"}
    )
    assert response.status_code == 400


# ------------------------------------------------------------- Profil & Sitzungen


async def test_update_display_name(client: AsyncClient, register_user: RegisterUser) -> None:
    user = await register_user("max@example.com")

    response = await client.patch(
        f"{API}/me", json={"display_name": "  Maxi "}, headers=user.headers
    )

    assert response.status_code == 200
    assert (await client.get(f"{API}/me", headers=user.headers)).json()["display_name"] == "Maxi"


async def test_sessions_can_be_listed_and_revoked(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")
    await client.post(f"{API}/auth/login", json={"email": user.email, "password": user.password})

    sessions = (await client.get(f"{API}/me/sessions", headers=user.headers)).json()
    assert len(sessions) == 2

    revoke = await client.delete(f"{API}/me/sessions/{sessions[-1]['id']}", headers=user.headers)
    assert revoke.status_code == 204
    assert len((await client.get(f"{API}/me/sessions", headers=user.headers)).json()) == 1
