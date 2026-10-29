"""Lücken im japanischen Katalog aus dem TCGplayer-Katalog (tcgcsv.com) schließen.

Bei älteren japanischen Sets fehlen oft die Karten über der Setgröße (Secret Rares wie „Rare
Candy 086/076“ in Megalo Cannon, BW9). TCGplayer führt die Sets vollständig – mit Nummer,
englischem Namen, Seltenheit und Bild. Ergänzt werden nur Karten, deren Nummer im Set fehlt;
vorhandene Karten bleiben unverändert. Neue Sets werden nicht angelegt.

Sicherung gegen falsche Zuordnung: Ein TCGplayer-Set gilt nur dann als dasselbe Set, wenn sein
Kürzel passt (mit Sprache, „BW9“ = „BW9-B“) **und** die meisten seiner Kartennummern im
Kartenkiste-Set schon vorhanden sind (:data:`MIN_OVERLAP`). Sonst wird es nur gemeldet.

Namen wie beim Classic-Import: Pokémon japanisch (PokéAPI), sonst englisch; ``name_en``
immer englisch. Gespeichert wird nur die Bildadresse.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CardSource, Game, ImageSource
from app.services.catalog_numbers import normalize_number
from app.services.classic_collection import (
    LARGE_IMAGE,
    SMALL_IMAGE,
    VARIANTS,
    ClassicCard,
    parse_products,
)
from app.services.tcgplayer_sets import code_key

log = structlog.get_logger(__name__)

LANGUAGE = "ja"
CATEGORY = 85  # TCGplayer: Pokémon Japan
MIN_OVERLAP = 0.6  # Anteil der TCGplayer-Nummern, die im Set schon vorkommen müssen
MIN_KNOWN = 5  # so viele gemeinsame Nummern mindestens (kleine Sets/Decks)
DOMINANT = 2  # bei mehreren TCGplayer-Sets für ein Katalog-Set: so viel mehr Treffer nötig
_DIGIT = re.compile(r"\d")
_NUMBER_SUFFIX = re.compile(r"\s+-\s+[\w-]+/[\w-]+$")  # „Emolga - 025/BW-P“
CONCURRENCY = 6
_BRACKET = re.compile(r"\s*[\[(][^\])]*[\])]\s*$")  # „Rare Candy (Secret)“, „… [1st Edition]“


def catalog_codes(external_id: str, code: str | None) -> set[str]:
    """Kürzel-Schlüssel eines Katalog-Sets; „BW9-B“ zählt auch als „BW9“."""
    codes = {value for value in (external_id, code) if value}
    codes |= {value[:-2] for value in codes if value.upper().endswith("-B")}
    return {code_key(value) for value in codes}


@dataclass(frozen=True)
class CatalogSet:
    id: uuid.UUID
    external_id: str
    numbers: frozenset[str]


@dataclass
class SetGap:
    """Ergebnis für ein TCGplayer-Set."""

    group: str
    abbreviation: str
    catalog_set: str | None
    overlap: int = 0
    tcg_numbers: int = 0
    missing: list[ClassicCard] = field(default_factory=list)
    skipped: str | None = None  # Grund, wenn nicht ergänzt wird


@dataclass
class GapReport:
    sets: list[SetGap] = field(default_factory=list)
    added: int = 0
    dry_run: bool = True
    images: dict[str, str] = field(default_factory=dict)  # TCGplayer-Adresse → beste Fassung

    @property
    def large_images(self) -> int:
        return sum(LARGE_IMAGE in url for url in self.images.values())

    @property
    def missing(self) -> int:
        return sum(len(gap.missing) for gap in self.sets if gap.skipped is None)


def unique_by_number(cards: Iterable[ClassicCard]) -> dict[str, ClassicCard]:
    """Eine Karte je Nummer (TCGplayer listet Fassungen wie „1st Edition“ einzeln)."""
    found: dict[str, ClassicCard] = {}
    for card in cards:
        found.setdefault(normalize_number(card.number), card)
    return found


def assess(
    group: Mapping[str, Any], cards: Sequence[ClassicCard], catalog: Sequence[CatalogSet]
) -> SetGap:
    """TCGplayer-Set mit dem passenden Katalog-Set vergleichen (eindeutig + Überschneidung)."""
    gap = SetGap(
        group=str(group.get("name") or ""),
        abbreviation=str(group.get("abbreviation") or ""),
        catalog_set=None,
    )
    by_number = unique_by_number(cards)
    gap.tcg_numbers = len(by_number)
    if len(catalog) != 1:
        gap.skipped = "kein Katalog-Set" if not catalog else "Kürzel mehrdeutig"
        return gap
    target = catalog[0]
    gap.catalog_set = target.external_id
    gap.overlap = sum(number in target.numbers for number in by_number)
    if gap.overlap < MIN_KNOWN or gap.overlap < MIN_OVERLAP * len(by_number):
        gap.skipped = f"nur {gap.overlap}/{len(by_number)} Nummern gemeinsam"
        return gap
    totals = Counter(card.total for card in by_number.values() if card.total)
    usual = totals.most_common(1)[0][0] if totals else None
    gap.missing = [
        card
        for number, card in by_number.items()
        if number not in target.numbers
        and _DIGIT.search(number)  # Basis-Energien „DAR“, „FIG“ … haben keine Nummer
        and card.total == usual  # „086/076“ in einem 076er-Set; Promos ohne Zahl
    ]
    return gap


def resolve_conflicts(gaps: Sequence[SetGap]) -> None:
    """Mehrere TCGplayer-Sets auf dasselbe Katalog-Set (Decks mit eigener Nummerierung wie die
    drei „Battle Strength Decks“ → Bk): nur ein klar bestes zählt, sonst keines."""
    by_set: dict[str, list[SetGap]] = {}
    for gap in gaps:
        if gap.skipped is None and gap.catalog_set is not None:
            by_set.setdefault(gap.catalog_set, []).append(gap)
    for rivals in by_set.values():
        if len(rivals) < 2:  # noqa: PLR2004
            continue
        rivals.sort(key=lambda gap: -gap.overlap)
        best, second = rivals[0], rivals[1]
        dominant = best.overlap >= DOMINANT * second.overlap
        for gap in rivals[0 if not dominant else 1 :]:
            gap.skipped = f"mehrere TCGplayer-Sets für {gap.catalog_set}" + (
                f" – „{best.group}“ passt besser" if dominant else ""
            )
            gap.missing = []


class JapaneseGaps:
    """Probelauf (Standard) oder Ergänzen der fehlenden Karten."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._transport = transport

    async def _catalog(self) -> dict[str, list[CatalogSet]]:
        """Kürzel-Schlüssel → japanische Katalog-Sets mit ihren Kartennummern."""
        async with self._session_factory() as session:
            sets = (
                await session.execute(
                    select(CardSet.id, CardSet.external_id, CardSet.code).where(
                        CardSet.game == Game.POKEMON.value, CardSet.language == LANGUAGE
                    )
                )
            ).all()
            numbers: dict[uuid.UUID, set[str]] = {}
            for set_id, number in (
                await session.execute(
                    select(Card.set_id, Card.number_norm).where(Card.language == LANGUAGE)
                )
            ).all():
                numbers.setdefault(set_id, set()).add(number)
        by_code: dict[str, list[CatalogSet]] = {}
        for set_id, external_id, code in sets:
            entry = CatalogSet(set_id, external_id, frozenset(numbers.get(set_id, set())))
            if not entry.numbers:
                continue  # leere Hüllen (z. B. XY11a/b) nie befüllen
            for key in catalog_codes(external_id, code):
                by_code.setdefault(key, []).append(entry)
        return by_code

    async def run(self, *, apply: bool = False, only: str | None = None) -> GapReport:
        report = GapReport(dry_run=not apply)
        catalog = await self._catalog()
        base = self._settings.sealed_images_url.rstrip("/")
        async with httpx.AsyncClient(
            headers={"User-Agent": self._settings.http_user_agent},  # ohne Kennung keine Daten
            timeout=60,
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            groups = (await client.get(f"{base}/{CATEGORY}/groups")).json().get("results", [])
            wanted = [
                group
                for group in groups
                if isinstance(group, dict)
                and isinstance(group.get("abbreviation"), str)
                and code_key(group["abbreviation"]) in catalog
                and (only is None or code_key(group["abbreviation"]) == code_key(only))
            ]
            semaphore = asyncio.Semaphore(CONCURRENCY)

            async def products(group: Mapping[str, Any]) -> list[ClassicCard]:
                async with semaphore:
                    response = await client.get(f"{base}/{CATEGORY}/{group['groupId']}/products")
                return parse_products(response.json()) if response.is_success else []

            fetched = await asyncio.gather(*(products(group) for group in wanted))
            assessed = [
                assess(group, cards, catalog[code_key(group["abbreviation"])])
                for group, cards in zip(wanted, fetched, strict=True)
            ]
            resolve_conflicts(assessed)
            report.sets = [gap for gap in assessed if gap.missing or gap.skipped]
            report.images = await _best_images(
                client, [card for gap in report.sets for card in gap.missing]
            )
        if apply:
            ids = {entry.external_id: entry.id for entries in catalog.values() for entry in entries}
            async with self._session_factory() as session:
                for gap in report.sets:
                    if gap.skipped is None and gap.catalog_set is not None:
                        report.added += await self._store(
                            session, ids[gap.catalog_set], gap, report.images
                        )
                await session.commit()
        log.info(
            "japanese_gaps.done",
            sets=len(report.sets),
            missing=report.missing,
            added=report.added,
            dry_run=report.dry_run,
        )
        return report

    @staticmethod
    async def _store(
        session: AsyncSession, set_id: uuid.UUID, gap: SetGap, images: Mapping[str, str]
    ) -> int:
        added = 0
        for card in gap.missing:
            image = images.get(card.image_url or "", card.image_url)
            english = _BRACKET.sub("", _NUMBER_SUFFIX.sub("", card.english)).strip()
            english = english or card.english
            result = await session.execute(
                insert(Card)
                .values(
                    external_id=f"{gap.catalog_set}-{card.number}"[:64],
                    language=LANGUAGE,
                    set_id=set_id,
                    number=card.number[:32],
                    number_norm=normalize_number(card.number),
                    name=(card.japanese or english)[:200],
                    name_en=english[:200],
                    rarity=card.rarity,
                    variants=VARIANTS,
                    image_url=image[:500] if image else None,
                    image_source=ImageSource.TCGPLAYER,
                    source=CardSource.TCGPLAYER,
                )
                .on_conflict_do_nothing()  # nichts überschreiben
            )
            added += int(getattr(result, "rowcount", 0) or 0)
        return added


async def _best_images(client: httpx.AsyncClient, cards: Sequence[ClassicCard]) -> dict[str, str]:
    """Je Karte die große Bildfassung, wenn TCGplayer sie hat (sonst die kleine, 200 px).
    Einzeln geprüft – eine Stichprobe genügte nicht (Promo-Energien haben keine große)."""
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def best(url: str) -> tuple[str, str]:
        if SMALL_IMAGE not in url:
            return url, url
        large = url.replace(SMALL_IMAGE, LARGE_IMAGE)
        try:
            async with semaphore:
                response = await client.head(large)
        except httpx.HTTPError:
            return url, url
        return url, large if response.is_success else url

    urls = {card.image_url for card in cards if card.image_url}
    return dict(await asyncio.gather(*(best(url) for url in urls)))


def render_report(report: GapReport, *, details: int = 40) -> str:
    mode = "Probelauf, nichts gespeichert" if report.dry_run else f"{report.added} ergänzt"
    lines = [
        f"# Japanischer Katalog: Lücken aus TCGplayer ({mode})",
        "",
        f"Fehlende Karten in passenden Sets: **{report.missing}**; große Bilder für "
        f"{report.large_images} von {len(report.images)}",
        "",
    ]
    ready = [gap for gap in report.sets if gap.skipped is None]
    for gap in sorted(ready, key=lambda g: -len(g.missing))[:details]:
        numbers = ", ".join(f"{c.number} {c.english}" for c in gap.missing[:6])
        more = f" … (+{len(gap.missing) - 6})" if len(gap.missing) > 6 else ""  # noqa: PLR2004
        lines.append(
            f"- **{gap.catalog_set}** „{gap.group}“ ({gap.overlap}/{gap.tcg_numbers} gemeinsam):"
            f" {len(gap.missing)} fehlen – {numbers}{more}"
        )
    if len(ready) > details:
        lines.append(f"- … und {len(ready) - details} weitere Sets")
    skipped = [gap for gap in report.sets if gap.skipped is not None]
    if skipped:
        lines += ["", f"Nicht ergänzt (Zuordnung unsicher): {len(skipped)} Sets"]
        lines += [
            f"- {gap.abbreviation} „{gap.group}“ → {gap.catalog_set or '–'}: {gap.skipped}"
            for gap in skipped[:20]
        ]
    return "\n".join(lines) + "\n"
