"""API-Tests für Preise, Preisverlauf, Einstellungen und Quellen-Status."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import PriceCheck
from tests.conftest import Account, RegisterUser
from tests.pricing_helpers import UPDATED, FakeProvider, cardmarket, make_card

API = "/api/v1"


async def test_prices_require_login(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    card = await make_card(session_factory)

    assert (await client.get(f"{API}/cards/{card.id}/prices")).status_code == 401
    assert (await client.get(f"{API}/cards/{card.id}/price-history")).status_code == 401


async def test_card_prices_with_proof_and_marked_estimates(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    price_provider.quotes = [cardmarket("trend", "1805.90"), cardmarket("low", "220")]

    response = await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    offer = body["offers"][0]
    assert offer["source"] == "cardmarket"
    assert offer["kind"] == "verified"
    assert offer["metrics"] == {"trend": "1805.90", "low": "220.00"}
    assert offer["url"] == "https://www.cardmarket.com/de/Pokemon/Products?idProduct=574273"
    assert offer["updated_at"].startswith("2026-10-16T08:51")
    nm = next(c for c in body["conditions"] if c["condition"] == "NM")
    assert (nm["value"], nm["kind"], nm["basis_metric"]) == ("1805.90", "estimated", "trend")

    # Zweiter Aufruf innerhalb der Frist holt nicht erneut.
    await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)
    assert len(price_provider.calls) == 1


async def test_card_without_prices_reports_no_data(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)

    body = (await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)).json()

    assert body["status"] == "no_data"
    assert body["offers"] == []
    assert body["conditions"] == []


async def test_source_failure_still_returns_stored_prices(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    price_provider.quotes = [cardmarket("trend", "50")]
    await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)

    # Gespeicherten Stand altern lassen, damit neu geholt wird – die Quelle ist jetzt gestört.
    async with session_factory() as session:
        await session.execute(
            update(PriceCheck).values(checked_at=datetime.now(UTC) - timedelta(hours=13))
        )
        await session.commit()
    price_provider.error = RuntimeError("down")
    price_provider.quotes = []

    response = await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)

    assert len(price_provider.calls) == 2  # wirklich erneut versucht
    assert response.status_code == 200
    assert response.json()["offers"][0]["metrics"] == {"trend": "50.00"}


async def test_price_history_endpoint(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
) -> None:
    user = await register_user("max@example.com")
    card = await make_card(session_factory)
    price_provider.quotes = [
        cardmarket("trend", "100", updated=UPDATED - timedelta(days=1)),
        cardmarket("trend", "120"),
    ]
    await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)

    response = await client.get(
        f"{API}/cards/{card.id}/price-history", params={"days": 3650}, headers=user.headers
    )

    body = response.json()
    assert [p["value"] for p in body["points"]] == ["100.00", "120.00"]
    assert (body["lowest"], body["highest"], body["currency"]) == ("100.00", "120.00", "EUR")


async def test_settings_roundtrip_validation_and_reset(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")

    initial = (await client.get(f"{API}/me/settings", headers=user.headers)).json()
    assert initial["condition_factors"]["EX"] == "0.85"
    assert initial["custom_condition_factors"] == []

    changed = await client.patch(
        f"{API}/me/settings",
        json={"condition_factors": {"EX": "0.9", "NM": "1.00"}, "default_language": "ja"},
        headers=user.headers,
    )
    assert changed.status_code == 200
    assert changed.json()["condition_factors"]["EX"] == "0.90"
    assert changed.json()["custom_condition_factors"] == ["EX"]  # NM = Standard → nicht gespeichert
    assert changed.json()["default_language"] == "ja"

    for invalid in ({"condition_factors": {"EX": "5"}}, {"condition_factors": {"XX": "1"}}):
        response = await client.patch(f"{API}/me/settings", json=invalid, headers=user.headers)
        assert response.status_code == 422

    reset = await client.patch(
        f"{API}/me/settings", json={"reset_condition_factors": True}, headers=user.headers
    )
    assert reset.json()["custom_condition_factors"] == []


async def test_language_factors_roundtrip(client: AsyncClient, register_user: RegisterUser) -> None:
    user = await register_user("max@example.com")

    initial = (await client.get(f"{API}/me/settings", headers=user.headers)).json()
    assert initial["language_factors"]["de"] == "1.00"
    assert initial["custom_language_factors"] == []

    changed = await client.patch(
        f"{API}/me/settings",
        json={"language_factors": {"de": "0.8", "en": "1.00"}},
        headers=user.headers,
    )
    assert changed.json()["language_factors"]["de"] == "0.80"
    assert changed.json()["custom_language_factors"] == ["de"]
    invalid = await client.patch(
        f"{API}/me/settings", json={"language_factors": {"fr": "0.9"}}, headers=user.headers
    )
    assert invalid.status_code == 422

    reset = await client.patch(
        f"{API}/me/settings", json={"reset_language_factors": True}, headers=user.headers
    )
    assert reset.json()["custom_language_factors"] == []
    assert reset.json()["language_factors"]["de"] == "1.00"


async def test_settings_are_per_user(client: AsyncClient, register_user: RegisterUser) -> None:
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")
    await client.patch(
        f"{API}/me/settings", json={"condition_factors": {"EX": "0.5"}}, headers=alice.headers
    )

    bob_settings = (await client.get(f"{API}/me/settings", headers=bob.headers)).json()

    assert bob_settings["condition_factors"]["EX"] == "0.85"


async def test_price_sources_status_admin_only(
    client: AsyncClient, admin: Account, register_user: RegisterUser
) -> None:
    user = await register_user("max@example.com")

    assert (await client.get(f"{API}/admin/price-sources", headers=user.headers)).status_code == 403
    response = await client.get(f"{API}/admin/price-sources", headers=admin.headers)
    assert response.status_code == 200
    assert response.json()[0]["name"] == "tcgdex"
    assert response.json()[0]["paused"] is False
