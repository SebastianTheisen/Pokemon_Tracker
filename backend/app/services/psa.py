"""PSA-Zertifikate nachschlagen – mit Zwischenspeicher (die PSA-API erlaubt wenige Abrufe/Tag).

Beim Slab-Scan liest der Scanner die Zertifikatsnummer vom Etikett
(:class:`app.scanner.slab.SlabLabel`). Ist ein Token eingerichtet (``PT_PSA_TOKEN``), bestätigt
PSA Karte, Note und Population. Zertifikate ändern sich nicht – nur die Population; gemerkte
Daten werden deshalb erst nach ``psa_cert_max_age_days`` erneuert. Ist PSA gestört, gilt der
zuletzt gemerkte Stand.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import PsaCertRecord
from app.providers.psa import PsaCert, PsaClient, PsaError
from app.services.errors import InvalidInputError, UpstreamError

log = structlog.get_logger(__name__)

_CERT = re.compile(r"^\d{6,10}$")
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PsaService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        client: PsaClient | None,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._session = session
        self._settings = settings
        self._client = client
        self._now = clock

    @property
    def configured(self) -> bool:
        return self._client is not None

    async def lookup(self, cert: str) -> PsaCert | None:
        """Zertifikat (gemerkt oder frisch von PSA); ``None`` = PSA kennt es nicht."""
        cert = cert.replace(" ", "")
        if not _CERT.match(cert):
            raise InvalidInputError("Ungültige Zertifikatsnummer (6–10 Ziffern).")
        if self._client is None:
            raise InvalidInputError("PSA-Abfrage ist nicht eingerichtet (PT_PSA_TOKEN fehlt).")
        record = await self._session.get(PsaCertRecord, cert)
        fresh_since = self._now() - timedelta(days=self._settings.psa_cert_max_age_days)
        if record is not None and record.fetched_at >= fresh_since:
            return _from_record(record)
        try:
            result = await self._client.get_cert(cert)
        except PsaError as exc:
            log.warning("psa.lookup_failed", cert=cert, error=str(exc))
            if record is not None:
                return _from_record(record)  # lieber alter Stand als gar nichts
            raise UpstreamError(f"PSA-Abfrage fehlgeschlagen: {exc}") from exc
        statement = insert(PsaCertRecord).values(
            cert=cert,
            data=asdict(result) if result is not None else None,
            fetched_at=self._now(),
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[PsaCertRecord.cert],
                set_={"data": statement.excluded.data, "fetched_at": statement.excluded.fetched_at},
            )
        )
        if record is not None:
            await self._session.refresh(record)
        return result


def _from_record(record: PsaCertRecord) -> PsaCert | None:
    if record.data is None:
        return None
    return PsaCert(**record.data)  # type: ignore[arg-type]
