"""Kommandozeile für Einrichtung und Wartung.

Beispiele (im Container: ``docker compose exec api python -m app.cli ...``)::

    python -m app.cli create-admin --email ich@example.com --name "Sebastian"
    python -m app.cli create-invite --note "für Max"
    python -m app.cli sync-catalog                 # alle Sprachen, inkrementell
    python -m app.cli sync-catalog --languages de en --full
    python -m app.cli search "nachtara 215"
    python -m app.cli refresh-prices               # Preis-Runde sofort ausführen
    python -m app.cli prices "nachtara 215" --language de
    python -m app.cli collection-check --email ich@example.com   # Probe, speichert nichts
    python -m app.cli scan foto.jpg --email ich@example.com     # ein Foto erkennen
    python -m app.cli scan-eval --photos testset --expected testset/soll.csv --email ich@…
    python -m app.cli scanner-warmup --korean     # OCR-Modelle laden (KO wird heruntergeladen)
    python -m app.cli import-images --dry-run     # Bildquellen testen, nichts speichern
    python -m app.cli import-images --sources pokemontcg pokemon.com
    python -m app.cli image-status                # letzter Bild-Import und Abdeckung
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.models import (
    GradingCompany,
    ImageImportRun,
    OfficialCard,
    Product,
    ProductKind,
    Role,
    User,
)
from app.providers.pricing.registry import build_price_providers
from app.providers.tcgdex import TcgdexClient
from app.scanner.ocr import RapidOcrReader
from app.scanner.runtime import ScannerRuntime
from app.services.admin import AdminService
from app.services.card_details import sync_card_details
from app.services.cardmarket_catalog import catalog_status as cardmarket_status
from app.services.cardmarket_catalog import render_status as render_cardmarket_status
from app.services.cardmarket_catalog import run_catalog_import
from app.services.catalog_search import search_cards
from app.services.catalog_sync import fill_image_fallbacks, sync_catalog
from app.services.collection import CollectionService, ItemFilter, ItemInput
from app.services.errors import ServiceError
from app.services.image_import import (
    ALL_SOURCES,
    catalog_coverage,
    run_image_import,
)
from app.services.image_import import (
    render_report as render_image_report,
)
from app.services.price_health import SourceHealth
from app.services.pricing import PriceService
from app.services.scan import ScanOutcome, ScanService
from app.services.scan_eval import evaluate, load_expected, render_report
from app.worker import refresh_tracked_prices

MIN_PASSWORD_LENGTH = 10


def _read_password() -> str:
    """Passwort aus ``PT_ADMIN_PASSWORD`` (nicht-interaktiv) oder per verdeckter Eingabe."""
    if env_password := os.environ.get("PT_ADMIN_PASSWORD"):
        return env_password
    first = getpass.getpass("Passwort (mind. 10 Zeichen): ")
    if getpass.getpass("Passwort wiederholen: ") != first:
        raise SystemExit("Die Passwörter stimmen nicht überein.")
    return first


async def _create_admin(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    password = _read_password()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit("Das Passwort muss mindestens 10 Zeichen lang sein.")
    async with factory() as session:
        user = await AdminService(session, settings).create_user(
            email=args.email, password=password, display_name=args.name, role=Role.ADMIN
        )
        await session.commit()
    print(f"Admin angelegt: {user.email} ({user.id})")


async def _create_invite(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    async with factory() as session:
        admin = await session.get(User, args.admin_id) if args.admin_id else None
        service = AdminService(session, settings)
        if admin is None:
            admins = [u for u in await service.list_users() if u.is_admin and u.is_active]
            if not admins:
                raise SystemExit("Kein aktiver Admin vorhanden – zuerst create-admin ausführen.")
            admin = admins[0]
        issued = await service.create_invite(admin, note=args.note, ttl_days=args.days)
        await session.commit()
    print(f"Einladungscode: {issued.plain_code}")
    print(f"Gültig bis:     {issued.record.expires_at:%d.%m.%Y %H:%M} UTC")


async def _sync_catalog(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    languages = args.languages or settings.catalog_languages
    async with TcgdexClient(
        base_url=settings.tcgdex_base_url, user_agent=settings.http_user_agent
    ) as client:
        reports = await sync_catalog(
            client,
            factory,
            languages,
            full=args.full,
            concurrency=settings.catalog_sync_concurrency,
        )
    print(f"{'Sprache':<8} {'Sets':>5} {'neu/akt.':>9} {'übersprungen':>13} {'Karten':>8} Fehler")
    for report in reports:
        print(
            f"{report.language:<8} {report.sets_total:>5} {report.sets_synced:>9} "
            f"{report.sets_skipped:>13} {report.cards_upserted:>8} {len(report.errors)}"
        )
        for error in report.errors[:5]:
            print(f"    ! {error}")
    if any(report.errors for report in reports):
        sys.exit(1)


async def _fill_images(
    factory: async_sessionmaker[AsyncSession], _settings: Settings, _args: argparse.Namespace
) -> None:
    """Fehlende Kartenbilder durch Bilder anderer Sprachfassungen ergänzen."""
    async with factory() as session:
        filled = await fill_image_fallbacks(session)
        await session.commit()
    print(f"Ersatzbilder gesetzt: {filled}")


async def _import_images(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    """Fehlende Bilder aus pokemontcg.io, pokemon.com und den offiziellen Datenbanken."""
    report = await run_image_import(
        factory,
        settings,
        sources=args.sources or settings.image_import_sources,
        max_pages=args.max_pages,
        max_details=args.max_details,
        dry_run=args.dry_run,
    )
    text = render_image_report(report)
    if args.out:
        await asyncio.to_thread(Path(args.out).write_text, text, encoding="utf-8")
    print(text)


async def _cardmarket_import(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    """Cardmarket-Katalog + Preisführer laden, Sets mit ihrer Cardmarket-Ausgabe verknüpfen."""
    if args.no_link:
        summary = await run_catalog_import(factory, settings, tcgdex=None)
    else:
        async with TcgdexClient(
            base_url=settings.tcgdex_base_url, user_agent=settings.http_user_agent
        ) as client:
            summary = await run_catalog_import(factory, settings, tcgdex=client)
    print(
        f"Produkte: {summary.products}, Preise: {summary.prices}, Ausgaben: "
        f"{summary.expansions} (mit Zwillingen: {summary.expansions_with_twins}), "
        f"feste Zuordnungen geändert: {summary.known_links}, Sets verknüpft: {summary.sets_linked}"
    )
    async with factory() as session:
        text = render_cardmarket_status(await cardmarket_status(session))
    if args.out:
        await asyncio.to_thread(Path(args.out).write_text, text, encoding="utf-8")
    print(text)
    if summary.error:
        raise SystemExit(f"Fehler: {summary.error}")


async def _cardmarket_status(
    factory: async_sessionmaker[AsyncSession], _settings: Settings, args: argparse.Namespace
) -> None:
    """Stand des Cardmarket-Katalogs und unsichere Sets."""
    async with factory() as session:
        text = render_cardmarket_status(await cardmarket_status(session))
    if args.out:
        await asyncio.to_thread(Path(args.out).write_text, text, encoding="utf-8")
    print(text)


async def _sync_card_details(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    """Fehlende Kartendetails (Seltenheit, Varianten, Illustrator) aus TCGdex holen."""
    async with TcgdexClient(
        base_url=settings.tcgdex_base_url, user_agent=settings.http_user_agent
    ) as client:
        report = await sync_card_details(
            factory, client, concurrency=settings.card_details_concurrency, limit=args.limit
        )
    print(
        f"Offen: {report.pending}, aktualisiert: {report.updated}, "
        f"bei TCGdex unbekannt: {report.not_found}, Fehler: {report.failed}"
    )
    for error in report.errors:
        print(f"    ! {error}")


async def _image_status(
    factory: async_sessionmaker[AsyncSession], _settings: Settings, _args: argparse.Namespace
) -> None:
    """Letzter Bild-Import und aktuelle Abdeckung."""
    async with factory() as session:
        run = await session.scalar(
            select(ImageImportRun).order_by(ImageImportRun.started_at.desc()).limit(1)
        )
        coverage = await catalog_coverage(session)
        progress = (
            await session.execute(
                select(
                    OfficialCard.source,
                    func.count(),
                    func.count(OfficialCard.detail_fetched_at),
                    func.count(OfficialCard.card_id),
                )
                .group_by(OfficialCard.source)
                .order_by(OfficialCard.source)
            )
        ).all()
    if run is None:
        print("Noch kein Bild-Import gelaufen.")
    else:
        state = f"fertig {run.finished_at:%d.%m.%Y %H:%M} UTC" if run.finished_at else "läuft"
        print(f"Letzter Lauf: gestartet {run.started_at:%d.%m.%Y %H:%M} UTC, {state}")
        for item in run.report.get("sources", []):
            if isinstance(item, dict):
                print(
                    f"  {item.get('source')}: {item.get('images_set')} Bilder, "
                    f"{item.get('cards_created')} angelegt, {len(item.get('errors', []))} Fehler"
                )
    if progress:
        print("Offizielle Datenbanken (Karten / Details geladen / zugeordnet):")
        for source, total, detailed, matched in progress:
            percent = 100 * detailed // total if total else 0
            print(f"  {source}: {total} / {detailed} ({percent} %) / {matched}")
        print("  Zuordnung und Bilder folgen, sobald alle Details geladen sind.")
    print("Abdeckung (mit Bild / gesamt):")
    for language, value in coverage.items():
        print(f"  {language}: {value}")


async def _search(
    factory: async_sessionmaker[AsyncSession], _settings: Settings, args: argparse.Namespace
) -> None:
    async with factory() as session:
        hits = await search_cards(session, args.query, language=args.language, limit=args.limit)
    if not hits:
        print("Keine Treffer.")
    for hit in hits:
        card = hit.card
        print(
            f"{hit.score:4.2f}  [{card.language:<5}] {card.name} · {card.card_set.name} · "
            f"{card.number}  ({card.external_id or 'eigene Karte'})"
        )


async def _refresh_prices(
    factory: async_sessionmaker[AsyncSession], settings: Settings, _args: argparse.Namespace
) -> None:
    health = SourceHealth(
        threshold=settings.price_breaker_threshold,
        pause=timedelta(minutes=settings.price_breaker_pause_minutes),
    )
    async with TcgdexClient(
        base_url=settings.tcgdex_base_url, user_agent=settings.http_user_agent
    ) as client:
        summary = await refresh_tracked_prices(
            factory, settings, build_price_providers(settings, client), health
        )
    print(
        f"Karten: {summary.cards} · neue Preiswerte: {summary.quotes_stored} · "
        f"mit Fehlern: {summary.failed_cards} · Tageswerte: {summary.snapshots}"
    )


async def _prices(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    """Erste Trefferkarte der Suche: Preise sofort holen und anzeigen."""
    health = SourceHealth(
        threshold=settings.price_breaker_threshold,
        pause=timedelta(minutes=settings.price_breaker_pause_minutes),
    )
    async with (
        TcgdexClient(
            base_url=settings.tcgdex_base_url, user_agent=settings.http_user_agent
        ) as client,
        factory() as session,
    ):
        hits = await search_cards(session, args.query, language=args.language, limit=1)
        if not hits:
            print("Keine Karte gefunden.")
            return
        card = hits[0].card
        service = PriceService(session, settings, build_price_providers(settings, client), health)
        report = await service.refresh(card, force=True)
        prices = await service.get_prices(card, None)
        await session.commit()

    print(
        f"{card.name} · {card.card_set.name} · {card.number} [{card.language}] ({card.external_id})"
    )
    print(f"Abruf: {', '.join(f'{k}={v}' for k, v in report.outcomes.items())}")
    if not prices.has_prices:
        print("Kein belegter Preis.")
    for offer in prices.offers:
        metrics = ", ".join(f"{k} {v}" for k, v in sorted(offer.metrics.items()))
        print(f"  {offer.source}/{offer.variant}: {metrics} {offer.currency}")
        print(f"    Stand {offer.updated_at:%d.%m.%Y %H:%M} UTC · Beleg: {offer.url or '–'}")
    for price in prices.conditions:
        if price.variant != "normal":
            continue
        if price.kind == "estimated":
            detail = f"Schätzung, {price.basis_metric} = {price.basis_value} × {price.factor}"
        else:
            detail = f"belegt, {price.source}"
        print(f"  {price.condition}: {price.value} {price.currency} ({detail})")


CHECK_CARDS = (
    ("nachtara 215", "de", {"condition": "NM", "quantity": 2}),
    ("glurak 4", "de", {"condition": "LP"}),
    ("Team Rockets Mewtu ex 231", "de", {"grading_company": GradingCompany.PSA, "grade": "10",
                                          "custom_price": Decimal("900")}),
)  # fmt: skip


async def _collection_check(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    """Probe-Sammlung mit echten Karten und Preisen – alles in einer Transaktion, die am Ende
    zurückgerollt wird. Es bleibt nichts in der Datenbank zurück."""
    health = SourceHealth(
        threshold=settings.price_breaker_threshold,
        pause=timedelta(minutes=settings.price_breaker_pause_minutes),
    )
    async with (
        TcgdexClient(
            base_url=settings.tcgdex_base_url, user_agent=settings.http_user_agent
        ) as client,
        factory() as session,
    ):
        owner = await session.scalar(select(User).where(User.email == args.email.strip().lower()))
        if owner is None:
            raise SystemExit(f"Kein Nutzer mit E-Mail {args.email}.")
        prices = PriceService(session, settings, build_price_providers(settings, client), health)
        collection = CollectionService(session, owner, prices)
        folder = await collection.create_folder("Phase-3-Probe")
        try:
            for query, language, fields in CHECK_CARDS:
                hits = await search_cards(session, query, language=language, limit=1)
                if not hits:
                    print(f"! Keine Karte für „{query}“")
                    continue
                await collection.add_item(
                    ItemInput(folder_id=folder.id, card_id=hits[0].card.id, **fields)
                )
            product = Product(kind=ProductKind.DISPLAY, language="de", name="Probe-Display")
            session.add(product)
            await session.flush()
            await collection.add_item(
                ItemInput(folder_id=folder.id, product_id=product.id, custom_price=Decimal("150"))
            )

            items, _ = await collection.list_items(
                ItemFilter(folder_id=folder.id), sort="value_desc"
            )
            for entry in items:
                item, value = entry.item, entry.value
                name = item.card.name if item.card else item.product.name if item.product else "?"
                label = item.condition or item.grade or "-"
                basis = f", {value.basis}" if value.basis else ""
                print(
                    f"{entry.kind:<6} {item.quantity}× {name} [{label}]: "
                    f"{value.total_value} € ({value.kind}{basis})"
                )
            summary = await collection.summary()
            raw, graded, sealed = (summary.by_kind[k] for k in ("raw", "graded", "sealed"))
            print(
                f"Gesamt: {summary.total_value} € · davon geschätzt {summary.estimated_value} € · "
                f"roh {raw.value} € · gegradet {graded.value} € · versiegelt {sealed.value} € · "
                f"{summary.positions} Positionen / {summary.items} Stück / {summary.sets} Sets"
            )
            csv_text = await collection.export_csv()
            print(f"CSV-Export: {len(csv_text.splitlines()) - 1} Zeilen")
        finally:
            await session.rollback()
            print("Probe zurückgerollt – keine Daten gespeichert.")


@asynccontextmanager
async def _scanner(settings: Settings) -> AsyncIterator[ScannerRuntime]:
    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True, headers={"User-Agent": settings.http_user_agent}
    ) as client:
        yield ScannerRuntime(settings, RapidOcrReader(), client)


async def _user_by_email(session: AsyncSession, email: str) -> User:
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise SystemExit(f"Kein Nutzer mit E-Mail {email}.")
    return user


def _print_outcome(outcome: ScanOutcome) -> None:
    if outcome.best is None:
        print("Keine Karte erkannt.")
    else:
        state = "sicher" if outcome.confident else "unsicher – bitte prüfen"
        print(f"Erkannt als {outcome.best.card.name} ({state})")
    for index, match in enumerate(
        [m for m in (outcome.best, *outcome.alternatives) if m is not None], start=1
    ):
        card = match.card
        print(
            f"  {index}. {card.name} · {card.card_set.name} · {card.number} [{card.language}] "
            f"({card.external_id}) · {match.confidence:.2f} · {'; '.join(match.reasons) or '–'}"
        )
    if outcome.grading:
        print(f"Slab: {outcome.grading.company} {outcome.grading.grade or '?'}")
    print(f"Merkmale: {outcome.detected}")
    print(f"Dauer: {outcome.duration_ms} ms")


async def _scan_photo(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    """Ein Foto erkennen (Probe: das Scan-Protokoll wird zurückgerollt)."""
    async with _scanner(settings) as runtime, factory() as session:
        user = await _user_by_email(session, args.email)
        try:
            data = await asyncio.to_thread(Path(args.file).read_bytes)
            outcome = await ScanService(session, runtime, user).scan(
                data, language_hint=args.language
            )
            _print_outcome(outcome)
        finally:
            await session.rollback()


async def _scan_eval(
    factory: async_sessionmaker[AsyncSession], settings: Settings, args: argparse.Namespace
) -> None:
    """Testsatz auswerten (Top-1/Top-5, Latenz) – speichert nichts."""
    expected = load_expected(Path(args.expected))
    async with _scanner(settings) as runtime, factory() as session:
        user = await _user_by_email(session, args.email)
        try:
            rows = await evaluate(ScanService(session, runtime, user), Path(args.photos), expected)
            report = render_report(rows)  # vor dem Zurückrollen – danach sind Karten abgelaufen
        finally:
            await session.rollback()
    if args.out:
        await asyncio.to_thread(Path(args.out).write_text, report, encoding="utf-8")
        print(f"Bericht geschrieben: {args.out}")
    else:
        print(report)


async def _scanner_warmup(
    _factory: async_sessionmaker[AsyncSession], _settings: Settings, args: argparse.Namespace
) -> None:
    """Lädt die OCR-Modelle einmal (das koreanische wird dabei heruntergeladen)."""
    reader = RapidOcrReader()
    print(f"Standardmodell (PP-OCRv6): {reader.warm_up()} Zeilen erkannt")
    if args.korean:
        print(f"Koreanisches Modell: {reader.warm_up(korean=True)} Zeilen erkannt")


Command = Callable[
    [async_sessionmaker[AsyncSession], Settings, argparse.Namespace], Awaitable[None]
]


def _add_image_commands(commands: Any) -> None:
    import_images = commands.add_parser(
        "import-images", help="Fehlende Kartenbilder aus weiteren Quellen ergänzen"
    )
    import_images.add_argument(
        "--sources", nargs="+", choices=ALL_SOURCES, help="Standard: PT_IMAGE_IMPORT_SOURCES"
    )
    import_images.add_argument(
        "--dry-run", action="store_true", help="nur testen: wenige Seiten lesen, nichts speichern"
    )
    import_images.add_argument("--max-pages", type=int, help="Listenseiten je Datenbank")
    import_images.add_argument("--max-details", type=int, help="Detailseiten je Datenbank")
    import_images.add_argument("--out", help="Bericht zusätzlich als Markdown-Datei")
    import_images.set_defaults(handler=_import_images)

    status = commands.add_parser("image-status", help="Letzter Bild-Import und Abdeckung")
    status.set_defaults(handler=_image_status)


def _add_cardmarket_commands(commands: Any) -> None:
    cardmarket = commands.add_parser(
        "cardmarket-import", help="Cardmarket-Katalog + Preisführer laden, Sets verknüpfen"
    )
    cardmarket.add_argument(
        "--no-link", action="store_true", help="Sets nicht bei TCGdex nachfragen (schneller)"
    )
    cardmarket.add_argument("--out", help="Status zusätzlich als Markdown-Datei")
    cardmarket.set_defaults(handler=_cardmarket_import)
    cardmarket_info = commands.add_parser(
        "cardmarket-status", help="Stand des Cardmarket-Katalogs und unsichere Sets"
    )
    cardmarket_info.add_argument("--out", help="zusätzlich als Markdown-Datei")
    cardmarket_info.set_defaults(handler=_cardmarket_status)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("create-admin", help="Admin-Konto anlegen")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True, help="Anzeigename")
    admin.set_defaults(handler=_create_admin)

    invite = commands.add_parser("create-invite", help="Einladungscode erzeugen")
    invite.add_argument("--note", help="Notiz, z. B. für wen")
    invite.add_argument("--days", type=int, help="Gültigkeit in Tagen")
    invite.add_argument("--admin-id", help="ID des ausstellenden Admins (Standard: erster Admin)")
    invite.set_defaults(handler=_create_invite)

    sync = commands.add_parser("sync-catalog", help="Katalog aus TCGdex importieren")
    sync.add_argument("--languages", nargs="+", help="z. B. de en ja (Standard: alle)")
    sync.add_argument("--full", action="store_true", help="alle Sets neu laden")
    sync.set_defaults(handler=_sync_catalog)

    images = commands.add_parser(
        "fill-images", help="Fehlende Bilder aus anderen Sprachfassungen ergänzen"
    )
    images.set_defaults(handler=_fill_images)

    _add_image_commands(commands)

    _add_cardmarket_commands(commands)

    details = commands.add_parser(
        "sync-card-details", help="Kartendetails (Seltenheit, Varianten) aus TCGdex holen"
    )
    details.add_argument("--limit", type=int, help="höchstens so viele Karten (zum Testen)")
    details.set_defaults(handler=_sync_card_details)

    prices = commands.add_parser(
        "refresh-prices", help="Preise aller vorgemerkten Karten jetzt aktualisieren"
    )
    prices.set_defaults(handler=_refresh_prices)

    card_prices = commands.add_parser("prices", help="Preise der ersten Trefferkarte anzeigen")
    card_prices.add_argument("query")
    card_prices.add_argument("--language")
    card_prices.set_defaults(handler=_prices)

    check = commands.add_parser(
        "collection-check", help="Probe-Sammlung mit echten Preisen (wird nicht gespeichert)"
    )
    check.add_argument("--email", required=True, help="E-Mail des Nutzers für die Probe")
    check.set_defaults(handler=_collection_check)

    scan = commands.add_parser("scan", help="Ein Foto erkennen (speichert nichts)")
    scan.add_argument("file", help="Pfad zum Foto")
    scan.add_argument("--email", required=True, help="Nutzer (für eigene Referenzbilder)")
    scan.add_argument("--language", help="Sprache vorgeben, z. B. ja")
    scan.set_defaults(handler=_scan_photo)

    evaluation = commands.add_parser("scan-eval", help="Scanner mit einem Testsatz messen")
    evaluation.add_argument("--photos", required=True, help="Ordner mit Testfotos")
    evaluation.add_argument("--expected", required=True, help="soll.csv")
    evaluation.add_argument("--email", required=True, help="Nutzer (für eigene Referenzbilder)")
    evaluation.add_argument("--out", help="Bericht als Markdown-Datei (sonst Ausgabe)")
    evaluation.set_defaults(handler=_scan_eval)

    warmup = commands.add_parser("scanner-warmup", help="OCR-Modelle laden bzw. herunterladen")
    warmup.add_argument("--korean", action="store_true", help="auch das koreanische Modell")
    warmup.set_defaults(handler=_scanner_warmup)

    search = commands.add_parser("search", help="Katalog durchsuchen")
    search.add_argument("query")
    search.add_argument("--language")
    search.add_argument("--limit", type=int, default=15)
    search.set_defaults(handler=_search)
    return parser


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    engine = create_engine(settings.database_url)
    try:
        handler: Command = args.handler
        await handler(create_session_factory(engine), settings, args)
    except ServiceError as exc:
        raise SystemExit(f"Fehler: {exc.message}") from exc
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    main()
