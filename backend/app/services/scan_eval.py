"""Qualitätsmessung des Scanners mit einem Testsatz (Plan 5.6, „Qualitätsmessung“).

Testsatz = Ordner mit Fotos + ``soll.csv`` (Semikolon)::

    datei;name;nummer;sprache;karte
    03.jpg;ルギアV;110/098;ja;S12-110
    01.jpg;ゼニガメ;007;ja;-

* ``karte`` (optional) ist die erwartete TCGdex-ID. Fehlt sie, zählt ein Treffer mit
  gleicher Nummer und Sprache als richtig.
* ``karte = -`` heißt „nicht im Katalog“: richtig ist dann, dass der Scanner **unsicher**
  ist (die App bietet „Selbst suchen“ an) – ein sicherer Treffer wäre ein Fehler.

Abnahme (Plan, Phase 4): Top-1 ≥ 85 % auf deutschen und englischen Karten, ≤ 3 s pro Karte.
"""

from __future__ import annotations

import asyncio
import csv
import time
from dataclasses import dataclass
from pathlib import Path

from app.models import Card
from app.services.catalog_numbers import normalize_number
from app.services.errors import ServiceError
from app.services.scan import ScanOutcome, ScanService

NOT_IN_CATALOG = "-"
ACCEPTANCE_LANGUAGES = frozenset({"de", "en"})
ACCEPTANCE_TOP1 = 0.85
ACCEPTANCE_SECONDS = 3.0


@dataclass(frozen=True)
class ExpectedCard:
    """Soll-Werte eines Testfotos."""

    file: str
    name: str
    number: str
    language: str
    card: str | None = None

    @property
    def not_in_catalog(self) -> bool:
        return self.card == NOT_IN_CATALOG

    def matches(self, card: Card) -> bool:
        if card.language != self.language:
            return False
        if self.card:
            return card.external_id == self.card
        return card.number_norm == normalize_number(self.number)


@dataclass(frozen=True)
class EvalRow:
    """Ergebnis eines Testfotos."""

    expected: ExpectedCard
    outcome: ScanOutcome | None
    seconds: float
    error: str | None = None

    @property
    def rank(self) -> int | None:
        """1-basierter Rang der richtigen Karte (Treffer + Alternativen), sonst ``None``."""
        if self.outcome is None or self.outcome.best is None:
            return None
        matches = [self.outcome.best, *self.outcome.alternatives]
        return next(
            (index for index, m in enumerate(matches, 1) if self.expected.matches(m.card)), None
        )

    @property
    def correct(self) -> bool:
        if self.expected.not_in_catalog:
            return self.outcome is not None and not self.outcome.confident
        return self.rank == 1

    @property
    def confident_wrong(self) -> bool:
        """Sicher angezeigt, aber falsch – der schlimmste Fall."""
        return self.outcome is not None and self.outcome.confident and not self.correct


def load_expected(path: Path) -> list[ExpectedCard]:
    """Liest ``soll.csv`` (Kopfzeile mit ``datei;name;nummer;sprache[;karte]``)."""
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    return [
        ExpectedCard(
            file=row["datei"].strip(),
            name=row["name"].strip(),
            number=row["nummer"].strip(),
            language=(row.get("sprache") or "de").strip(),
            card=(row.get("karte") or "").strip() or None,
        )
        for row in rows
        if (row.get("datei") or "").strip()
    ]


async def evaluate(
    service: ScanService, photos_dir: Path, expected: list[ExpectedCard]
) -> list[EvalRow]:
    """Scannt jedes Testfoto wie die App (ohne Sprachvorgabe)."""
    rows: list[EvalRow] = []
    for item in expected:
        started = time.perf_counter()
        try:
            data = await asyncio.to_thread((photos_dir / item.file).read_bytes)
            outcome = await service.scan(data)
        except (OSError, ServiceError) as exc:
            message = exc.message if isinstance(exc, ServiceError) else str(exc)
            rows.append(EvalRow(item, None, time.perf_counter() - started, error=message))
            continue
        rows.append(EvalRow(item, outcome, time.perf_counter() - started))
    return rows


def _rate(hits: int, total: int) -> str:
    return f"{hits}/{total} ({100 * hits / total:.0f} %)" if total else "– (keine Fotos)"


def _label(card: Card) -> str:
    return f"{card.name} · {card.external_id or card.id} [{card.language}]"


def render_report(rows: list[EvalRow]) -> str:
    """Markdown-Bericht mit Kennzahlen, Abnahme-Status und Einzelergebnissen."""
    in_catalog = [row for row in rows if not row.expected.not_in_catalog]
    acceptance = [row for row in in_catalog if row.expected.language in ACCEPTANCE_LANGUAGES]
    seconds = [row.seconds for row in rows]
    top1 = sum(row.correct for row in in_catalog)
    top5 = sum(row.rank is not None for row in in_catalog)
    acceptance_top1 = sum(row.correct for row in acceptance)
    outside = [row for row in rows if row.expected.not_in_catalog]
    lines = [
        "# Scanner-Evaluation\n",
        "## Kennzahlen\n",
        f"- Fotos: {len(rows)} (davon {len(outside)} nicht im Katalog)",
        f"- **Top-1:** {_rate(top1, len(in_catalog))}",
        f"- Top-5 (richtige Karte unter Treffer + Alternativen): {_rate(top5, len(in_catalog))}",
        "- Nicht im Katalog, richtig als unsicher erkannt: "
        f"{_rate(sum(row.correct for row in outside), len(outside))}",
        f"- **Sicher, aber falsch:** {sum(row.confident_wrong for row in rows)}",
        f"- Zeit pro Foto: Ø {sum(seconds) / len(seconds):.2f} s, max {max(seconds):.2f} s"
        if seconds
        else "- Zeit pro Foto: –",
        "",
        "## Abnahme (Plan Phase 4)\n",
    ]
    if len(acceptance) == 0:
        lines.append(
            "- Top-1 DE/EN: **noch nicht messbar** – keine deutschen/englischen Fotos im Testsatz"
        )
    else:
        reached = acceptance_top1 / len(acceptance) >= ACCEPTANCE_TOP1
        lines.append(
            f"- Top-1 DE/EN: {_rate(acceptance_top1, len(acceptance))} – Ziel ≥ 85 % "
            f"{'✅' if reached else '❌'}"
            + (" (zu wenige Fotos für eine belastbare Aussage)" if len(acceptance) < 20 else "")  # noqa: PLR2004
        )
    if seconds:
        fast = max(seconds) <= ACCEPTANCE_SECONDS
        lines.append(f"- Latenz ≤ 3 s: {'✅' if fast else '❌'} (max {max(seconds):.2f} s)")
    lines += [
        "",
        "## Einzelergebnisse\n",
        "| Datei | Soll | Ergebnis | Sicher | Rang | Confidence | Begründung | s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        expected = f"{row.expected.name} · {row.expected.number} [{row.expected.language}]"
        if row.expected.card:
            expected += f" ({row.expected.card})"
        if row.outcome is None:
            lines.append(
                f"| {row.expected.file} | {expected} | Fehler: {row.error} | – | – | – | – "
                f"| {row.seconds:.2f} |"
            )
            continue
        best = row.outcome.best
        verdict = "✅" if row.correct else "❌"
        lines.append(
            f"| {row.expected.file} | {expected} | {verdict} {_label(best.card) if best else '–'} "
            f"| {'ja' if row.outcome.confident else 'nein'} | {row.rank or '–'} "
            f"| {best.confidence if best else '–'} "
            f"| {'; '.join(best.reasons).replace('|', '/') if best else '–'} | {row.seconds:.2f} |"
        )
    lines += ["", "## Erkannte Merkmale\n"]
    for row in rows:
        if row.outcome is not None:
            detected = row.outcome.detected
            numbers = ", ".join(n["raw"] for n in detected.get("numbers", [])) or "–"
            names = ", ".join(detected.get("names", [])) or "–"
            slab = detected.get("slab")
            slab_text = f" · Slab {slab['company']} {slab['grade']}" if slab else ""
            lines.append(
                f"- **{row.expected.file}:** Nummern {numbers} · Namen {names} · Sprache "
                f"{', '.join(detected.get('languages', [])) or '–'}{slab_text}"
            )
    return "\n".join(lines) + "\n"
