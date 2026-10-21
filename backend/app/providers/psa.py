"""Client für die offizielle PSA Public API (https://api.psacard.com/publicapi).

psacard.com selbst blockt Abrufe vom Server (Cloudflare, Spike ``docs/phase5/apify_runs_f.md``);
die Public API ist der vorgesehene Weg – mit kostenlosem Token, aber begrenzten Abrufen pro
Tag. Deshalb merkt sich Kartenkiste jedes Zertifikat (:mod:`app.services.psa`).

Die Antwort von ``GET /cert/GetByCertNumber/{nummer}`` steckt in ``PSACert`` und enthält u. a.
``YearIssued`` (früher ``Year``), ``Brand`` (Set), ``CardNumber``, ``Subject`` (Karte),
``Variety``, ``CardGrade`` bzw. ``GradeDescription`` („GEM MT 10“). ``TotalPopulation`` und
``PopulationHigher`` sind in der öffentlichen API meist leer. Unbekannte oder ungültige
Nummern: HTTP 200 mit ``IsValidRequest: false`` bzw. ``ServerMessage: "No data found"``.
Feldnamen werden ohne Rücksicht auf Groß-/Kleinschreibung gelesen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx

API = "https://api.psacard.com/publicapi"
_GRADE = re.compile(r"(\d{1,2}(?:\.5)?)\s*$")


class PsaError(Exception):
    """PSA-API nicht erreichbar, Token ungültig oder Tageslimit erreicht."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PsaCert:
    """Ein geprüftes PSA-Zertifikat."""

    cert: str
    year: str | None
    brand: str | None
    card_number: str | None
    subject: str | None
    variety: str | None
    grade_description: str | None
    grade: str | None
    population: int | None
    population_higher: int | None

    @property
    def language_hint(self) -> str | None:
        """„POKEMON JAPANESE …“ → ``ja`` (für den Abgleich mit dem Scan)."""
        brand = (self.brand or "").upper()
        for word, code in (("JAPANESE", "ja"), ("KOREAN", "ko"), ("CHINESE", "zh-tw")):
            if word in brand:
                return code
        return None


def _field(data: dict[str, Any], name: str) -> Any:
    lowered = name.lower()
    return next((value for key, value in data.items() if key.lower() == lowered), None)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def normalize_grade(*texts: str | None) -> str | None:
    """„GEM MT 10“ → „10“, „NM-MT+ 8.5“ → „8.5“, „AUTHENTIC“ → ``None``."""
    for text in texts:
        match = _GRADE.search(text or "")
        if match and 0 < float(match.group(1)) <= 10:  # noqa: PLR2004 – Notenskala
            return match.group(1)
    return None


def parse_cert(payload: object, cert: str) -> PsaCert | None:
    """Antwort der API → :class:`PsaCert`; ``None``, wenn PSA das Zertifikat nicht kennt."""
    if not isinstance(payload, dict) or _field(payload, "IsValidRequest") is False:
        return None
    data = _field(payload, "PSACert")
    if not isinstance(data, dict):
        data = payload if _field(payload, "CertNumber") is not None else None
    if not data:
        return None
    grade_description = _text(_field(data, "GradeDescription"))
    card_grade = _text(_field(data, "CardGrade"))
    return PsaCert(
        cert=_text(_field(data, "CertNumber")) or cert,
        year=_text(_field(data, "YearIssued")) or _text(_field(data, "Year")),
        brand=_text(_field(data, "Brand")),
        card_number=_text(_field(data, "CardNumber")),
        subject=_text(_field(data, "Subject")),
        variety=_text(_field(data, "Variety")),
        grade_description=grade_description or card_grade,
        grade=normalize_grade(card_grade, grade_description),
        population=_int(_field(data, "TotalPopulation")),
        population_higher=_int(_field(data, "PopulationHigher")),
    )


class PsaClient:
    """Asynchroner Client der PSA Public API. Als Kontextmanager verwenden."""

    def __init__(
        self,
        token: str,
        *,
        user_agent: str,
        base_url: str = API,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"bearer {token}",
                "Accept": "application/json",
                "User-Agent": user_agent,
            },
            timeout=20.0,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_cert(self, cert: str) -> PsaCert | None:
        """Zertifikat nachschlagen (``None`` = unbekannt)."""
        try:
            response = await self._client.get(f"/cert/GetByCertNumber/{cert}")
        except httpx.HTTPError as exc:
            raise PsaError(f"PSA nicht erreichbar: {type(exc).__name__}") from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise PsaError(
                f"PSA: HTTP {response.status_code} {response.text[:150]}".strip(),
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise PsaError("PSA: Antwort ist kein JSON") from exc
        return parse_cert(payload, cert)
