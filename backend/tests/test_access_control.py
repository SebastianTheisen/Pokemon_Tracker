"""Zugriffsschutz: Rollen, Mandantentrennung (IDOR) und Admin-Regeln.

Grundsatz: Fremde Objekte sind für normale Nutzer „nicht vorhanden“ (404), Admin-Funktionen
sind für normale Nutzer verboten (403), ohne Anmeldung gibt es nichts (401).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AuditLog
from tests.conftest import Account, RegisterUser

API = "/api/v1"

ADMIN_ENDPOINTS = [
    ("GET", "/admin/users", None),
    ("PATCH", "/admin/users/{id}", {"is_active": False}),
    ("POST", "/admin/users/{id}/password-reset", None),
    ("GET", "/admin/invites", None),
    ("POST", "/admin/invites", {}),
    ("DELETE", "/admin/invites/{id}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ENDPOINTS)
async def test_admin_endpoints_are_forbidden_for_users(
    client: AsyncClient,
    register_user: RegisterUser,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    user = await register_user("max@example.com")

    response = await client.request(
        method, API + path.format(id=user.user_id), json=body, headers=user.headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ENDPOINTS)
async def test_admin_endpoints_require_login(
    client: AsyncClient, method: str, path: str, body: dict[str, object] | None
) -> None:
    response = await client.request(method, API + path.format(id=uuid.uuid4()), json=body)

    assert response.status_code == 401


async def test_user_cannot_revoke_foreign_session(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    bob_session = (await client.get(f"{API}/me/sessions", headers=bob.headers)).json()[0]["id"]

    attack = await client.delete(f"{API}/me/sessions/{bob_session}", headers=alice.headers)

    assert attack.status_code == 404
    still_valid = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": bob.refresh_token}
    )
    assert still_valid.status_code == 200


async def test_sessions_list_contains_only_own_sessions(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")

    alice_ids = {
        s["id"] for s in (await client.get(f"{API}/me/sessions", headers=alice.headers)).json()
    }
    bob_ids = {
        s["id"] for s in (await client.get(f"{API}/me/sessions", headers=bob.headers)).json()
    }

    assert alice_ids
    assert bob_ids
    assert not alice_ids & bob_ids


async def test_deactivated_user_is_locked_out_immediately(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")

    response = await client.patch(
        f"{API}/admin/users/{user.user_id}", json={"is_active": False}, headers=admin.headers
    )
    assert response.status_code == 200

    # Auch das noch nicht abgelaufene Access-Token wirkt nicht mehr.
    assert (await client.get(f"{API}/me", headers=user.headers)).status_code == 401
    refresh = await client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    assert refresh.status_code == 401
    login = await client.post(
        f"{API}/auth/login", json={"email": user.email, "password": user.password}
    )
    assert login.status_code == 401


async def test_role_change_takes_effect_without_new_login(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")
    assert (await client.get(f"{API}/admin/users", headers=user.headers)).status_code == 403

    await client.patch(
        f"{API}/admin/users/{user.user_id}", json={"role": "admin"}, headers=admin.headers
    )

    assert (await client.get(f"{API}/admin/users", headers=user.headers)).status_code == 200


async def test_admin_cannot_lock_out_themselves(client: AsyncClient, admin: Account) -> None:
    for change in ({"is_active": False}, {"role": "user"}):
        response = await client.patch(
            f"{API}/admin/users/{admin.user_id}", json=change, headers=admin.headers
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "self_lockout"


async def test_last_active_admin_cannot_be_removed(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    second = await register_user("zweiter@example.com")
    await client.patch(
        f"{API}/admin/users/{second.user_id}", json={"role": "admin"}, headers=admin.headers
    )

    # Zweiter Admin stuft den ersten herab – erlaubt, es bleibt ja einer übrig.
    demote = await client.patch(
        f"{API}/admin/users/{admin.user_id}", json={"role": "user"}, headers=second.headers
    )
    assert demote.status_code == 200

    # Der verbliebene Admin kann sich nicht selbst entfernen.
    last = await client.patch(
        f"{API}/admin/users/{second.user_id}", json={"is_active": False}, headers=second.headers
    )
    assert last.status_code == 400


async def test_admin_actions_are_audited(
    client: AsyncClient,
    admin: Account,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    await client.patch(
        f"{API}/admin/users/{user.user_id}", json={"is_active": False}, headers=admin.headers
    )
    await client.post(f"{API}/admin/users/{user.user_id}/password-reset", headers=admin.headers)

    async with session_factory() as session:
        entries = (
            await session.scalars(select(AuditLog).where(AuditLog.actor_id == admin.user_id))
        ).all()

    actions = {entry.action for entry in entries}
    assert {"admin.invite_created", "admin.user_updated", "admin.password_reset_created"} <= actions
    updated = next(e for e in entries if e.action == "admin.user_updated")
    assert updated.target_user_id == user.user_id
    assert updated.details == {"is_active": False}


async def test_invite_listing_shows_status_and_hides_codes(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    await register_user("max@example.com")  # verbraucht eine Einladung
    await client.post(f"{API}/admin/invites", json={"note": "offen"}, headers=admin.headers)

    invites = (await client.get(f"{API}/admin/invites", headers=admin.headers)).json()

    assert sorted(i["status"] for i in invites) == ["open", "used"]
    assert all("code" not in invite for invite in invites)


async def test_used_invite_cannot_be_revoked(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    await register_user("max@example.com")
    used = (await client.get(f"{API}/admin/invites", headers=admin.headers)).json()[0]

    response = await client.delete(f"{API}/admin/invites/{used['id']}", headers=admin.headers)

    assert response.status_code == 400
    missing = await client.delete(f"{API}/admin/invites/{uuid.uuid4()}", headers=admin.headers)
    assert missing.status_code == 404
