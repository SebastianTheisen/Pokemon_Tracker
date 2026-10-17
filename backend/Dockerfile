# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /srv
# Nur Laufzeit-Abhängigkeiten: keine Dev- und Spike-Gruppen (siehe [tool.uv] default-groups).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project

# README.md wird beim Bauen des Projekts benötigt (pyproject: readme = "README.md").
COPY README.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN uv sync --frozen --no-default-groups

RUN useradd --create-home --uid 1000 tracker
USER tracker

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')"

ENV PATH="/srv/.venv/bin:${PATH}"
# Beim Start zuerst Datenbank-Migrationen, dann die API.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
