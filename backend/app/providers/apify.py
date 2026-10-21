"""Client für die Apify-API (https://docs.apify.com/api/v2): Dienste starten, Ergebnisse, Guthaben.

Kartenkiste startet darüber einen Dienst aus dem Apify-Store (z. B. verkaufte eBay.de-Artikel)
mit dem Token des Betreibers. Jeder Lauf bekommt einen Kostendeckel (``maxTotalChargeUsd``)
und ein Zeitlimit; das Monatsbudget prüft der Aufrufer vorher mit :meth:`ApifyClient.usage`.
Der Token steht nur in der ``.env`` und wird nie geloggt.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Self

import httpx

API = "https://api.apify.com/v2"
FINISHED = frozenset({"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"})
_POLL_SECONDS = 30


class ApifyError(Exception):
    """Apify nicht erreichbar, Lauf fehlgeschlagen oder Antwort unbrauchbar."""


@dataclass(frozen=True)
class ApifyUsage:
    """Verbrauch im laufenden Abrechnungsmonat (US-Dollar)."""

    used_usd: float
    limit_usd: float
    cycle_end: datetime | None


@dataclass(frozen=True)
class ApifyRun:
    run_id: str
    items: list[dict[str, Any]]
    cost_usd: float | None


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class ApifyClient:
    """Asynchroner Apify-Client. Als Kontextmanager verwenden (schließt die Verbindung)."""

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
            headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent},
            timeout=90.0,
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

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApifyError(f"Apify nicht erreichbar: {type(exc).__name__}") from exc
        if response.status_code >= httpx.codes.BAD_REQUEST:
            message = ""
            try:
                message = str(response.json().get("error", {}).get("message", ""))
            except ValueError:
                message = response.text[:200]
            raise ApifyError(f"Apify: HTTP {response.status_code} {message}".strip())
        try:
            return response.json()
        except ValueError as exc:
            raise ApifyError("Apify: Antwort ist kein JSON") from exc

    async def usage(self) -> ApifyUsage:
        data = (await self._request("GET", "/users/me/limits")).get("data") or {}
        current = data.get("current") or {}
        limits = data.get("limits") or {}
        return ApifyUsage(
            used_usd=float(current.get("monthlyUsageUsd") or 0.0),
            limit_usd=float(limits.get("maxMonthlyUsageUsd") or 0.0),
            cycle_end=_parse_time((data.get("monthlyUsageCycle") or {}).get("endAt")),
        )

    async def run_actor(
        self,
        actor_id: str,
        payload: dict[str, Any],
        *,
        max_charge_usd: float,
        timeout_seconds: int,
        max_items: int,
    ) -> ApifyRun:
        """Startet einen Dienst, wartet auf das Ende und liefert die Ergebnisse."""
        started = await self._request(
            "POST",
            f"/acts/{actor_id.replace('/', '~')}/runs",
            params={
                "timeout": timeout_seconds,
                "maxTotalChargeUsd": max_charge_usd,
                "waitForFinish": 60,
            },
            json=payload,
        )
        run: dict[str, Any] = started.get("data") or {}
        deadline = time.monotonic() + timeout_seconds + 60
        while run.get("status") not in FINISHED:
            if time.monotonic() > deadline:
                raise ApifyError("Apify: Lauf dauert zu lange")
            polled = await self._request(
                "GET", f"/actor-runs/{run.get('id')}", params={"waitForFinish": _POLL_SECONDS}
            )
            run = polled.get("data") or {}
        if run.get("status") != "SUCCEEDED":
            message = str(run.get("statusMessage") or run.get("status"))[:200]
            raise ApifyError(f"Apify-Lauf fehlgeschlagen: {message}")
        dataset = run.get("defaultDatasetId")
        items: Any = []
        if dataset:
            items = await self._request(
                "GET", f"/datasets/{dataset}/items", params={"clean": "true", "limit": max_items}
            )
        cost = run.get("usageTotalUsd")
        return ApifyRun(
            run_id=str(run.get("id")),
            items=[item for item in items if isinstance(item, dict)]
            if isinstance(items, list)
            else [],
            cost_usd=float(cost) if isinstance(cost, int | float) else None,
        )
