"""Scan-Service: Foto → Karte (Plan 5.6).

Ablauf je Bild:

1. Rate-Limit prüfen, Bild sicher laden (:func:`app.scanner.imaging.decode_image`).
2. Auswerten (OCR, Merkmale, Ausschnitt) – in einem Thread.
3. **Kandidaten** aus dem Katalog: Nummer (+ Setgröße/Setcode) und unscharfer Name.
4. **Bildabgleich** der besten Kandidaten gegen Katalogbilder und die eigenen
   Referenzbilder des Nutzers. Ohne jeden Textanker: nur gegen die eigenen Referenzbilder
   (Rettungsweg).
5. Bewerten (:mod:`app.services.scan_scoring`), sicher/unsicher entscheiden.
6. Protokollieren (``scan_log``, ohne Bild). Der Kartenausschnitt bleibt bis zur
   Bestätigung im Arbeitsspeicher – bestätigt der Nutzer, wird er sein Referenzbild.

Bleibt das Ergebnis schwach und wurde noch nicht koreanisch gelesen, folgt ein zweiter
OCR-Durchlauf mit dem koreanischen Modell (Plan: „wenn der erste Durchlauf zu wenig liefert“).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import ColumnElement, delete, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CardReferenceImage, CardSet, ScanLog, ScanMode, User
from app.scanner.analysis import PhotoAnalysis, add_korean_pass, analyze_photo
from app.scanner.binder import BinderLayout, binder_cells
from app.scanner.imaging import (
    BINDER_MAX_SIDE,
    MAX_SIDE,
    InvalidImageError,
    UInt8Image,
    decode_image,
    encode_jpeg,
)
from app.scanner.matching import (
    CONFIDENT_INLIERS,
    REFERENCE_FEATURES,
    ImageFeatures,
    extract_features,
    match_score,
)
from app.scanner.runtime import ScannerRuntime
from app.scanner.slab import SlabLabel
from app.scanner.storage import ReferenceStore
from app.scanner.text import NameCandidate, TextFeatures, is_cjk_text
from app.scanner.twins import TwinDecision, pick_twin
from app.services.errors import InvalidInputError, NotFoundError, RateLimitedError
from app.services.scan_scoring import (
    Candidate,
    add_image_reasons,
    apply_twins,
    is_confident,
    rank,
    score_text,
    twin_group,
)

log = structlog.get_logger(__name__)

MAX_ALTERNATIVES = 4
NUMBER_QUERY_LIMIT = 300
NAME_QUERY_LIMIT = 60
NAME_QUERIES = 6
RESCUE_MIN_INLIERS = CONFIDENT_INLIERS // 2
REFERENCE_MAX_SIDE = 800
RATE_WINDOW = timedelta(hours=1)
# Zeichen, die der Vergleichsschlüssel (``compact_key``) entfernt – gleich in SQL.
_COMPACT_SQL_CHARS = " .,'’`\"-·・"  # noqa: RUF001


@dataclass(frozen=True)
class ScanMatch:
    """Ein Kandidat im Ergebnis."""

    card: Card
    confidence: float
    reasons: tuple[str, ...]
    inliers: int | None


@dataclass(frozen=True)
class ScanOutcome:
    """Ergebnis eines Bildes."""

    scan_id: uuid.UUID
    best: ScanMatch | None
    alternatives: tuple[ScanMatch, ...]
    confident: bool
    detected: dict[str, Any]
    grading: SlabLabel | None
    duration_ms: int
    reference_available: bool


@dataclass(frozen=True)
class BatchItem:
    """Ein Bild eines Stapel-Scans – mit Ergebnis oder Fehlermeldung."""

    filename: str
    outcome: ScanOutcome | None = None
    error: str | None = None


@dataclass(frozen=True)
class BinderCellOutcome:
    row: int
    column: int
    outcome: ScanOutcome


@dataclass(frozen=True)
class BinderOutcome:
    method: str
    cells: tuple[BinderCellOutcome, ...]


@dataclass(frozen=True)
class ConfirmOutcome:
    scan_id: uuid.UUID
    card: Card
    reference: CardReferenceImage | None
    reference_note: str | None


@dataclass
class _Evaluation:
    ranked: list[Candidate] = field(default_factory=list)
    rescue: bool = False


def _best_score(evaluation: _Evaluation) -> float:
    return evaluation.ranked[0].score if evaluation.ranked else 0.0


def _match(candidate: Candidate) -> ScanMatch:
    return ScanMatch(
        card=candidate.card,
        confidence=candidate.confidence,
        reasons=tuple(candidate.reasons),
        inliers=candidate.inliers,
    )


def _score_pairs(
    query: ImageFeatures, references: Sequence[tuple[int, str, ImageFeatures]]
) -> list[tuple[int, str, int]]:
    """Bildabgleich vieler Referenzen (läuft in einem Thread)."""
    return [(index, kind, match_score(query, ref)) for index, kind, ref in references]


class ScanService:
    """Scans eines Nutzers."""

    def __init__(self, session: AsyncSession, runtime: ScannerRuntime, user: User) -> None:
        self.session = session
        self.runtime = runtime
        self.settings = runtime.settings
        self.user = user

    # ------------------------------------------------------------------ Grenzen

    async def _check_rate_limit(self, images: int) -> None:
        since = datetime.now(UTC) - RATE_WINDOW
        used, oldest = (
            await self.session.execute(
                select(func.count(), func.min(ScanLog.created_at)).where(
                    ScanLog.user_id == self.user.id, ScanLog.created_at >= since
                )
            )
        ).one()
        limit = self.settings.scan_rate_limit_per_hour
        if used + images > limit:
            retry = RATE_WINDOW - (datetime.now(UTC) - oldest) if oldest else RATE_WINDOW
            raise RateLimitedError(
                f"Zu viele Scans: höchstens {limit} Bilder pro Stunde.",
                retry_after_seconds=max(1, int(retry.total_seconds())),
            )

    async def _decode(self, data: bytes, *, max_side: int = MAX_SIDE) -> UInt8Image:
        try:
            image: UInt8Image = await self.runtime.run_cpu(
                lambda: decode_image(
                    data, max_side=max_side, max_pixels=self.settings.scan_max_pixels
                )
            )
        except InvalidImageError as exc:
            raise InvalidInputError(str(exc), code="invalid_image") from exc
        return image

    # ------------------------------------------------------------------ Kandidaten

    async def _cards_by_number(self, text: TextFeatures) -> list[Card]:
        cards: list[Card] = []
        set_codes = sorted(text.set_codes)
        languages = list(text.language.languages)
        for number in sorted({hit.number for hit in text.numbers}):
            totals = sorted(
                {hit.total for hit in text.numbers if hit.number == number and hit.total}
            )
            narrowing: list[ColumnElement[bool]] = []
            if totals:
                narrowing.append(CardSet.card_count_official.in_(totals))
            if set_codes:
                narrowing.append(
                    func.replace(func.lower(CardSet.external_id), "-", "").in_(set_codes)
                )
            if languages and not totals:
                narrowing.append(Card.language.in_(languages))
            statement = (
                select(Card)
                .join(CardSet, Card.set_id == CardSet.id)
                .where(Card.number_norm == number)
                .order_by(CardSet.release_date.desc().nulls_last())
                .limit(NUMBER_QUERY_LIMIT)
            )
            if narrowing:
                statement = statement.where(or_(*narrowing))
            cards += (await self.session.scalars(statement)).unique()
        return cards

    async def _cards_by_name(self, names: Iterable[NameCandidate]) -> list[Card]:
        compact_name = func.translate(func.lower(Card.name), _COMPACT_SQL_CHARS, "")
        cards: list[Card] = []
        for name in list(names)[:NAME_QUERIES]:
            cjk = is_cjk_text(name.key)
            conditions: list[ColumnElement[bool]] = []
            if len(name.base) >= (2 if cjk else 3):
                conditions.append(compact_name.contains(name.base, autoescape=True))
            if not cjk and len(name.key) >= 4:  # noqa: PLR2004 – Trigramme brauchen Länge
                # pg_trgm (Index): Wort-Ähnlichkeit für Tippfehler der OCR
                conditions.append(literal(name.text.casefold()).op("<%")(func.lower(Card.name)))
            if not conditions:
                continue
            statement = (
                select(Card)
                .join(CardSet, Card.set_id == CardSet.id)
                .where(or_(*conditions))
                .order_by(CardSet.release_date.desc().nulls_last())
                .limit(NAME_QUERY_LIMIT)
            )
            cards += (await self.session.scalars(statement)).unique()
        return cards

    async def _text_candidates(
        self, text: TextFeatures, language_hint: str | None
    ) -> list[Candidate]:
        found: dict[uuid.UUID, Card] = {}
        for card in [*await self._cards_by_number(text), *await self._cards_by_name(text.names)]:
            found.setdefault(card.id, card)
        candidates = [
            score_text(Candidate(card), text, language_hint=language_hint)
            for card in found.values()
        ]
        if language_hint is not None:
            candidates = [c for c in candidates if c.card.language == language_hint] or candidates
        return rank(candidates)

    # ------------------------------------------------------------------ Bildabgleich

    async def _reference_rows(
        self, card_ids: Sequence[uuid.UUID] | None, *, limit: int | None = None
    ) -> list[CardReferenceImage]:
        statement = select(CardReferenceImage).where(CardReferenceImage.user_id == self.user.id)
        if card_ids is not None:
            statement = statement.where(CardReferenceImage.card_id.in_(card_ids))
        statement = statement.order_by(CardReferenceImage.created_at.desc())
        if limit is not None:
            statement = statement.limit(limit)
        return list((await self.session.scalars(statement)).unique())

    async def _load_reference_features(
        self, rows: Sequence[CardReferenceImage]
    ) -> list[ImageFeatures | None]:
        store = self.runtime.references
        loaded: list[ImageFeatures | None] = await self.runtime.run_cpu(
            lambda: [store.features(row.user_id, row.id) for row in rows]
        )
        return loaded

    async def _image_match(self, ranked: list[Candidate], query: ImageFeatures) -> None:
        """Bildabgleich der besten Kandidaten (Katalogbild + eigene Referenzbilder)."""
        top = ranked[: self.settings.scanner_max_image_candidates]
        if not top or len(query) == 0:
            return
        catalog = await self.runtime.catalog_images.features_many(c.card.image_url for c in top)
        index_by_card = {c.card.id: i for i, c in enumerate(top)}
        references = await self._reference_rows(list(index_by_card))
        reference_features = await self._load_reference_features(references)

        pairs: list[tuple[int, str, ImageFeatures]] = [
            (index, "catalog", features)
            for index, features in enumerate(catalog)
            if features is not None
        ]
        pairs += [
            (index_by_card[row.card_id], "reference", features)
            for row, features in zip(references, reference_features, strict=True)
            if features is not None
        ]
        if not pairs:
            return
        scores: list[tuple[int, str, int]] = await self.runtime.run_cpu(_score_pairs, query, pairs)
        for index, kind, inliers in scores:
            candidate = top[index]
            if kind == "catalog":
                candidate.catalog_inliers = max(candidate.catalog_inliers or 0, inliers)
            else:
                candidate.reference_inliers = max(candidate.reference_inliers or 0, inliers)
        for candidate in top:
            add_image_reasons(candidate)

    async def _rescue_by_references(self, query: ImageFeatures) -> list[Candidate]:
        """Kein lesbarer Text: nur gegen die eigenen (neuesten) Referenzbilder abgleichen."""
        limit = self.settings.scanner_rescue_references
        if limit == 0 or len(query) == 0:
            return []
        rows = await self._reference_rows(None, limit=limit)
        features = await self._load_reference_features(rows)
        pairs = [
            (index, "reference", feature)
            for index, feature in enumerate(features)
            if feature is not None
        ]
        scores: list[tuple[int, str, int]] = await self.runtime.run_cpu(_score_pairs, query, pairs)
        best: dict[uuid.UUID, Candidate] = {}
        for index, _kind, inliers in scores:
            if inliers < RESCUE_MIN_INLIERS:
                continue
            row = rows[index]
            candidate = best.setdefault(row.card_id, Candidate(row.card))
            candidate.reference_inliers = max(candidate.reference_inliers or 0, inliers)
        for candidate in best.values():
            add_image_reasons(candidate)
        return rank(list(best.values()))

    async def _twin_images(self, twins: Sequence[Candidate]) -> list[str] | None:
        """Bild-URLs aller Zwillinge in *einer* Sprache (Text darf kein Unterschied sein)."""
        ids = [twin.card.external_id for twin in twins if twin.card.external_id]
        rows = await self.session.execute(
            select(Card.external_id, Card.language, Card.image_url).where(
                Card.external_id.in_(ids),
                Card.image_url.is_not(None),
                Card.image_language.is_(None),
            )
        )
        by_identity: dict[str, dict[str, str]] = {twin.identity: {} for twin in twins}
        for twin in twins:
            if twin.card.image_url:
                language = twin.card.image_language or twin.card.language
                by_identity[twin.identity][language] = twin.card.image_url
        for external_id, language, image_url in rows:
            if external_id in by_identity and image_url:
                by_identity[external_id].setdefault(language, image_url)
        common = set.intersection(*(set(urls) for urls in by_identity.values()))
        for language in (twins[0].card.language, "en", *sorted(common)):
            if language in common:
                return [by_identity[twin.identity][language] for twin in twins]
        return None

    async def _separate_twins(self, ranked: list[Candidate], photo: UInt8Image) -> None:
        """Original und Nachdruck (gleiche Nummer, gleiche Grafik) am Bild unterscheiden."""
        twins = twin_group(ranked, self.settings.scanner_max_image_candidates)
        urls = await self._twin_images(twins) if twins else None
        if urls is None:
            return
        catalog = self.runtime.catalog_images
        images = [await catalog.image_for(url) for url in urls]
        if any(image is None for image in images):
            return
        decision: TwinDecision = await self.runtime.run_cpu(
            pick_twin, photo, [image for image in images if image is not None]
        )
        if decision.members:
            winner = None if decision.index is None else twins[decision.index]
            apply_twins([twins[index] for index in decision.members], winner)
        log.info(
            "scan.twins",
            cards=[twin.identity for twin in twins],
            members=decision.members,
            winner=decision.index,
            distances=[round(value, 1) for value in decision.distances],
        )

    async def _evaluate(
        self, analysis: PhotoAnalysis, image: UInt8Image, language_hint: str | None
    ) -> _Evaluation:
        ranked = await self._text_candidates(analysis.text, language_hint)
        if not ranked:
            return _Evaluation(await self._rescue_by_references(analysis.features), rescue=True)
        await self._image_match(ranked, analysis.features)
        ranked = rank(ranked)
        await self._separate_twins(ranked, analysis.reference_image(image))
        return _Evaluation(rank(ranked))

    # ------------------------------------------------------------------ Ablauf

    @staticmethod
    def _korean_may_help(
        analysis: PhotoAnalysis, evaluation: _Evaluation, language_hint: str | None
    ) -> bool:
        """Zweiter Durchlauf koreanisch, wenn das Ergebnis unsicher ist und nichts auf eine
        andere Sprache hindeutet (Japanisch und Latein liest das Standardmodell sicher)."""
        if analysis.korean_done or language_hint not in {None, "ko"}:
            return False
        if analysis.text.language.script in {"kana", "latin"}:
            return False
        return not is_confident(evaluation.ranked)

    async def _identify(
        self,
        image: UInt8Image,
        *,
        mode: ScanMode,
        language_hint: str | None,
        find_crop: bool = True,
    ) -> ScanOutcome:
        started = time.perf_counter()
        reader = self.runtime.reader
        korean_allowed = self.settings.scanner_korean_ocr
        analysis: PhotoAnalysis = await self.runtime.run_cpu(
            lambda: analyze_photo(
                image,
                reader,
                korean=korean_allowed and language_hint == "ko",
                find_crop=find_crop,
            )
        )
        evaluation = await self._evaluate(analysis, image, language_hint)
        if korean_allowed and self._korean_may_help(analysis, evaluation, language_hint):
            korean = await self.runtime.run_cpu(add_korean_pass, analysis, image, reader)
            korean_evaluation = await self._evaluate(korean, image, language_hint)
            # Nur übernehmen, wenn es besser wird – das KO-Modell liest andere Schriften falsch.
            if _best_score(korean_evaluation) > _best_score(evaluation):
                analysis, evaluation = korean, korean_evaluation

        ranked = evaluation.ranked
        confident = is_confident(ranked)
        best = ranked[0] if ranked else None
        best_identity = best.identity if best else None
        alternatives = ranked[1 : 1 + MAX_ALTERNATIVES]
        detected = analysis.text.summary() | {"rescue": evaluation.rescue}

        scan_id = uuid.uuid4()
        reference = analysis.reference_image(image)
        reference_jpeg: bytes = await self.runtime.run_cpu(
            lambda: encode_jpeg(reference, max_side=REFERENCE_MAX_SIDE)
        )
        self.runtime.pending.put(scan_id, self.user.id, reference_jpeg)

        duration_ms = int((time.perf_counter() - started) * 1000)
        self.session.add(
            ScanLog(
                id=scan_id,
                user_id=self.user.id,
                mode=mode,
                duration_ms=duration_ms,
                best_card_id=best.card.id if best else None,
                confidence=best.confidence if best else None,
                confident=confident,
                detected=detected,
            )
        )
        await self.session.flush()
        log.info(
            "scan.done",
            scan_id=str(scan_id),
            mode=mode.value,
            best=best_identity,
            confident=confident,
            candidates=len(ranked),
            duration_ms=duration_ms,
        )
        return ScanOutcome(
            scan_id=scan_id,
            best=_match(best) if best else None,
            alternatives=tuple(_match(c) for c in alternatives),
            confident=confident,
            detected=detected,
            grading=analysis.text.slab,
            duration_ms=duration_ms,
            reference_available=True,
        )

    async def scan(
        self, data: bytes, *, language_hint: str | None = None, mode: ScanMode = ScanMode.SINGLE
    ) -> ScanOutcome:
        """Ein Foto erkennen."""
        await self._check_rate_limit(1)
        image = await self._decode(data)
        return await self._identify(image, mode=mode, language_hint=language_hint)

    async def scan_batch(
        self, files: Sequence[tuple[str, bytes]], *, language_hint: str | None = None
    ) -> list[BatchItem]:
        """Stapel-Scan: mehrere Fotos nacheinander; ein defektes Bild stoppt den Rest nicht."""
        if not files:
            raise InvalidInputError("Keine Bilder übergeben.")
        if len(files) > self.settings.scan_batch_max:
            raise InvalidInputError(
                f"Höchstens {self.settings.scan_batch_max} Bilder pro Stapel.",
                code="batch_too_large",
            )
        await self._check_rate_limit(len(files))
        items: list[BatchItem] = []
        for filename, data in files:
            try:
                image = await self._decode(data)
            except InvalidInputError as exc:
                items.append(BatchItem(filename=filename, error=exc.message))
                continue
            outcome = await self._identify(image, mode=ScanMode.BATCH, language_hint=language_hint)
            items.append(BatchItem(filename=filename, outcome=outcome))
        return items

    async def scan_binder(
        self, data: bytes, *, layout: BinderLayout = "auto", language_hint: str | None = None
    ) -> BinderOutcome:
        """Binderseite (Beta): Seite zerlegen, jede Zelle einzeln erkennen."""
        await self._check_rate_limit(1)
        page = await self._decode(data, max_side=BINDER_MAX_SIDE)
        cells, method = await self.runtime.run_cpu(binder_cells, page, layout)
        await self._check_rate_limit(len(cells))
        results = [
            BinderCellOutcome(
                row=cell.row,
                column=cell.column,
                outcome=await self._identify(
                    cell.image,
                    mode=ScanMode.BINDER,
                    language_hint=language_hint,
                    find_crop=False,
                ),
            )
            for cell in cells
        ]
        return BinderOutcome(method=method, cells=tuple(results))

    # ------------------------------------------------------------------ Bestätigen

    async def confirm(
        self, scan_id: uuid.UUID, card_id: uuid.UUID, *, save_reference: bool = True
    ) -> ConfirmOutcome:
        """Nutzer bestätigt (oder korrigiert) das Ergebnis; optional wird der
        Kartenausschnitt sein Referenzbild für diese Karte."""
        entry = await self.session.scalar(
            select(ScanLog).where(ScanLog.id == scan_id, ScanLog.user_id == self.user.id)
        )
        if entry is None:
            raise NotFoundError("Scan nicht gefunden.")
        card = await self.session.get(Card, card_id)
        if card is None:
            raise NotFoundError("Karte nicht gefunden.")
        entry.confirmed_card_id = card.id
        entry.confirmed_at = datetime.now(UTC)

        if not save_reference:
            return ConfirmOutcome(scan_id, card, None, None)
        pending = self.runtime.pending.pop(scan_id, self.user.id)
        if pending is None:
            return ConfirmOutcome(
                scan_id, card, None, "Referenzbild nicht mehr verfügbar (Scan zu alt)."
            )
        features, (width, height) = await self.runtime.run_cpu(
            _reference_features, pending.image_jpeg
        )
        reference = CardReferenceImage(
            id=uuid.uuid4(),
            user_id=self.user.id,
            card_id=card.id,
            scan_id=scan_id,
            feature_count=len(features),
            width=width,
            height=height,
        )
        await self.runtime.run_cpu(
            self.runtime.references.save, self.user.id, reference.id, pending.image_jpeg, features
        )
        self.session.add(reference)
        await self.session.flush()
        await self._limit_references(card.id)
        return ConfirmOutcome(scan_id, card, reference, None)

    async def _limit_references(self, card_id: uuid.UUID) -> None:
        """Höchstens ``scanner_references_per_card`` je Karte – die ältesten fliegen raus."""
        rows = await self._reference_rows([card_id])
        for row in rows[self.settings.scanner_references_per_card :]:
            await self._delete_reference(row)

    async def _delete_reference(self, row: CardReferenceImage) -> None:
        await self.runtime.run_cpu(self.runtime.references.delete, row.user_id, row.id)
        await self.session.delete(row)

    # ------------------------------------------------------------------ Referenzbilder

    async def list_references(self, card_id: uuid.UUID | None = None) -> list[CardReferenceImage]:
        return await self._reference_rows([card_id] if card_id else None)

    async def _own_reference(self, reference_id: uuid.UUID) -> CardReferenceImage:
        row = await self.session.scalar(
            select(CardReferenceImage).where(
                CardReferenceImage.id == reference_id,
                CardReferenceImage.user_id == self.user.id,
            )
        )
        if row is None:
            raise NotFoundError("Referenzbild nicht gefunden.")
        return row

    async def reference_image(self, reference_id: uuid.UUID) -> bytes:
        row = await self._own_reference(reference_id)
        data: bytes | None = await self.runtime.run_cpu(
            self.runtime.references.image, row.user_id, row.id
        )
        if data is None:
            raise NotFoundError("Referenzbild-Datei fehlt.")
        return data

    async def delete_reference(self, reference_id: uuid.UUID) -> None:
        await self._delete_reference(await self._own_reference(reference_id))


def _reference_features(data: bytes) -> tuple[ImageFeatures, tuple[int, int]]:
    """Merkmale und Größe (Breite, Höhe) eines zwischengespeicherten Kartenausschnitts."""
    image = decode_image(data, max_side=REFERENCE_MAX_SIDE)
    height, width = image.shape[:2]
    return extract_features(image, max_features=REFERENCE_FEATURES), (width, height)


# ---------------------------------------------------------------------- Pflege


async def purge_scan_logs(session: AsyncSession, *, retention_days: int) -> int:
    """Löscht Protokolleinträge, die älter als die Aufbewahrungsfrist sind."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await session.execute(delete(ScanLog).where(ScanLog.created_at < cutoff))
    return int(getattr(result, "rowcount", 0) or 0)


async def prune_reference_files(session: AsyncSession, store: ReferenceStore) -> int:
    """Löscht Referenzbild-Dateien ohne Datenbankeintrag (z. B. nach Löschen einer Karte)."""
    rows = await session.execute(select(CardReferenceImage.user_id, CardReferenceImage.id))
    return store.prune({(row[0], row[1]) for row in rows})
