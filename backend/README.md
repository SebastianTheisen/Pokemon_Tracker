# Backend

FastAPI-Backend des Pokémon-Karten-Trackers. Details und Status: [`../UMSETZUNGSPLAN.md`](../UMSETZUNGSPLAN.md).

## Entwicklung

```bash
cd backend
uv sync                       # Abhängigkeiten inkl. Dev-Tools
uv run ruff check .           # Lint
uv run ruff format .          # Formatieren
uv run mypy                   # Typprüfung (strict)
uv run pytest --cov           # Tests mit Coverage
uv run uvicorn app.main:app --reload   # Dev-Server, Doku unter /api/docs
```

## Spikes

```bash
uv run python scripts/spike_datasources.py --out ../docs/spikes/datenquellen.md
```
