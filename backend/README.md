# Backend

FastAPI-Backend des Pokémon-Karten-Trackers. Details und Status: [`../UMSETZUNGSPLAN.md`](../UMSETZUNGSPLAN.md).

## Entwicklung

Voraussetzung: PostgreSQL 16 mit einer Test-Datenbank. Standard ist
`postgresql+asyncpg://tracker:tracker@localhost:5432/tracker_test`, änderbar über `PT_TEST_DATABASE_URL`.

```bash
cd backend
uv sync                                  # Abhängigkeiten inkl. Dev-Tools
uv run ruff check . && uv run ruff format .
uv run mypy                              # Typprüfung (strict)
uv run pytest --cov                      # Tests mit Coverage (baut Schema per Alembic)
uv run alembic upgrade head              # Migrationen (nutzt PT_DATABASE_URL)
uv run uvicorn app.main:app --reload     # Dev-Server, API-Doku unter /api/docs
```

## Kommandozeile

```bash
uv run python -m app.cli create-admin --email ich@example.com --name "Ich"
uv run python -m app.cli create-invite --note "für Max"
uv run python -m app.cli sync-catalog [--languages de en] [--full]
uv run python -m app.cli search "nachtara 215"
```

Im Container stellst du jedem Befehl `docker compose exec api` voran.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `app/core` | Konfiguration, Logging, Sicherheit (Passwörter, Tokens) |
| `app/db` | Engine, Sitzungen, deklarative Basis |
| `app/models` | ORM-Modelle |
| `app/schemas` | Pydantic-Schemas der API |
| `app/services` | Fachlogik (Auth, Admin, Katalog-Import, Suche); kennt kein HTTP |
| `app/providers` | Externe Quellen (TCGdex) |
| `app/api/v1` | Router; nur Ein- und Ausgabe, keine Fachlogik |
| `alembic/` | Datenbank-Migrationen |
| `scripts/` | Spike-Skripte aus Phase 0 |
