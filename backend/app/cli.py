"""Kommandozeile für Einrichtung und Wartung.

Beispiele (im Container: ``docker compose exec api python -m app.cli ...``)::

    python -m app.cli create-admin --email ich@example.com --name "Sebastian"
    python -m app.cli create-invite --note "für Max"
    python -m app.cli sync-catalog                 # alle Sprachen, inkrementell
    python -m app.cli sync-catalog --languages de en --full
    python -m app.cli search "nachtara 215"
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.models import Role, User
from app.providers.tcgdex import TcgdexClient
from app.services.admin import AdminService
from app.services.catalog_search import search_cards
from app.services.catalog_sync import sync_catalog
from app.services.errors import ServiceError

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


Command = Callable[
    [async_sessionmaker[AsyncSession], Settings, argparse.Namespace], Awaitable[None]
]


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
