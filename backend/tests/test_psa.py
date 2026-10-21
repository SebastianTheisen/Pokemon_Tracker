"""PSA-Zertifikate: Einlesen der API-Antwort und Zwischenspeicher."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.providers.psa import PsaClient, normalize_grade, parse_cert
from app.services.errors import InvalidInputError, UpstreamError
from app.services.psa import PsaService

CERT = {
    "CertNumber": "73270136",
    "Brand": "POKEMON JAPANESE SWORD & SHIELD PARADIGM TRIGGER",
    "CardNumber": "110",
    "Subject": "FA/LUGIA V",
    "CardGrade": "GEM MT 10",
    "TotalPopulation": "1234",
    "PopulationHigher": 0,
}


def test_grade_and_parsing() -> None:
    assert normalize_grade("GEM MT 10") == "10"
    assert normalize_grade("NM-MT+ 8.5") == "8.5"
    assert normalize_grade("AUTHENTIC", None) is None
    assert normalize_grade(None, "MINT 9") == "9"

    wrapped = parse_cert({"PSACert": CERT}, "73270136")
    flat = parse_cert({key.lower(): value for key, value in CERT.items()}, "73270136")
    assert wrapped is not None and flat is not None
    assert (wrapped.grade, wrapped.population, wrapped.language_hint) == ("10", 1234, "ja")
    assert flat.subject == "FA/LUGIA V"
    assert parse_cert({"IsValidRequest": True, "ServerMessage": "No data found"}, "1") is None
    assert parse_cert({"IsValidRequest": False, "ServerMessage": "Invalid CertNo"}, "x") is None
    current = parse_cert({"PSACert": {**CERT, "YearIssued": "2022"}}, "73270136")
    assert current is not None and current.year == "2022"
    assert parse_cert(["kaputt"], "1") is None


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 21, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


async def test_lookup_is_cached_and_survives_outages(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    calls: list[str] = []
    status = {"code": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if status["code"] != 200:
            return httpx.Response(status["code"], text="Tageslimit")
        if request.url.path.endswith("/73270136"):
            return httpx.Response(200, json={"PSACert": CERT})
        return httpx.Response(200, json={"ServerMessage": "No data found"})

    clock = Clock()
    configured = settings.model_copy(update={"psa_token": SecretStr("t")})
    async with PsaClient("t", user_agent="test", transport=httpx.MockTransport(handler)) as client:
        async with session_factory() as session:
            service = PsaService(session, configured, client, clock=clock)
            first = await service.lookup("7327 0136")
            again = await service.lookup("73270136")
            unknown = await service.lookup("11111111")
            assert await service.lookup("11111111") is None  # auch „unbekannt“ gemerkt
            await session.commit()
        assert first is not None and again == first
        assert unknown is None
        assert len(calls) == 2

        # Nach der Frist neu – PSA gestört → alter Stand statt Fehler.
        clock.now += timedelta(days=configured.psa_cert_max_age_days + 1)
        status["code"] = 429
        async with session_factory() as session:
            service = PsaService(session, configured, client, clock=clock)
            assert await service.lookup("73270136") == first
            with pytest.raises(UpstreamError):
                await service.lookup("22222222")
            with pytest.raises(InvalidInputError):
                await service.lookup("12ab")
    async with session_factory() as session:
        with pytest.raises(InvalidInputError, match="nicht eingerichtet"):
            await PsaService(session, settings, None).lookup("73270136")
