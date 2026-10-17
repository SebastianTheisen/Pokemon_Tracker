#!/usr/bin/env bash
# Phase 0 auf dem VPS: Abhängigkeiten installieren, Tests und alle Spikes ausführen.
# Ergebnisse landen in docs/spikes/ und zusätzlich als Archiv docs/spikes_ergebnisse.tar.gz.
#
# Aufruf aus dem Repo-Wurzelverzeichnis:
#   bash deploy/phase0_vps.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPIKE_DIR="${REPO_ROOT}/docs/spikes"
PHOTO_DIR="${REPO_ROOT}/scanner_testset"
SUMMARY="${SPIKE_DIR}/zusammenfassung.md"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[Hinweis]\033[0m %s\n' "$*"; }

mkdir -p "${SPIKE_DIR}"
{
  echo "# Phase 0 – Ergebnisse vom VPS"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- System: $(. /etc/os-release && echo "${PRETTY_NAME}") · $(nproc) CPU · $(free -h | awk '/Mem:/ {print $2}') RAM"
  echo "- Git-Stand: $(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  echo
} > "${SUMMARY}"

step "1/6 Systempakete prüfen"
missing=()
for pkg in git curl libglib2.0-0; do
  dpkg -s "${pkg}" >/dev/null 2>&1 || missing+=("${pkg}")
done
if ((${#missing[@]})); then
  echo "Installiere: ${missing[*]}"
  sudo apt-get update -qq && sudo apt-get install -y -qq "${missing[@]}"
fi

step "2/6 uv (Python-Paketmanager) prüfen"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi
uv --version

step "3/6 Python-Abhängigkeiten installieren"
cd "${REPO_ROOT}/backend"
uv python install 3.12
uv sync --all-groups

step "4/6 Tests und Qualitätsprüfungen"
check_status="✅ grün"
if ! (uv run ruff check . && uv run mypy && uv run pytest -q); then
  check_status="❌ fehlgeschlagen (Ausgabe oben)"
fi
echo "- Tests/Lint/Typen: ${check_status}" >> "${SUMMARY}"

step "5/6 Spike Datenquellen (TCGdex, pokemontcg.io, 1× Cardmarket)"
if uv run python scripts/spike_datasources.py --out "${SPIKE_DIR}/datenquellen.md"; then
  echo "- Spike Datenquellen: ✅ Bericht in docs/spikes/datenquellen.md" >> "${SUMMARY}"
else
  echo "- Spike Datenquellen: ⚠️ mindestens eine Quelle nicht erreichbar – siehe docs/spikes/datenquellen.md" >> "${SUMMARY}"
fi

step "6/6 Spike Scanner"
shopt -s nullglob nocaseglob
photos=("${PHOTO_DIR}"/*.{jpg,jpeg,png,webp,heic,heif})
shopt -u nullglob nocaseglob
if ((${#photos[@]})); then
  expected_args=()
  [[ -f "${PHOTO_DIR}/soll.csv" ]] && expected_args=(--expected "${PHOTO_DIR}/soll.csv")
  if uv run --group spike python scripts/spike_scanner.py \
      --photos "${PHOTO_DIR}" --out "${SPIKE_DIR}/scanner.md" "${expected_args[@]}"; then
    echo "- Spike Scanner: ✅ ${#photos[@]} Fotos, Bericht in docs/spikes/scanner.md" >> "${SUMMARY}"
  else
    echo "- Spike Scanner: ❌ Skript abgebrochen" >> "${SUMMARY}"
  fi
else
  warn "Keine Fotos in ${PHOTO_DIR} – Scanner-Spike übersprungen."
  echo "- Spike Scanner: ⏭️ übersprungen (keine Fotos in scanner_testset/)" >> "${SUMMARY}"
fi

step "Zusatz: Docker-Build und Health-Check"
cd "${REPO_ROOT}"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  created_env=false
  if [[ ! -f .env ]]; then cp .env.example .env; created_env=true; fi
  if docker compose up --build -d; then
    health="❌ keine Antwort"
    for _ in $(seq 1 30); do
      if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
        health="✅ $(curl -fsS http://127.0.0.1:8000/api/v1/health)"
        break
      fi
      sleep 2
    done
    echo "- Docker: Build ok, Health-Check ${health}" >> "${SUMMARY}"
    docker compose down
  else
    echo "- Docker: ❌ Build/Start fehlgeschlagen" >> "${SUMMARY}"
  fi
  if [[ "${created_env}" == true ]]; then rm -f .env; fi
else
  warn "Docker nicht installiert – Docker-Test übersprungen (kommt in Phase 6)."
  echo "- Docker: ⏭️ nicht installiert" >> "${SUMMARY}"
fi

tar -czf "${REPO_ROOT}/docs/spikes_ergebnisse.tar.gz" -C "${REPO_ROOT}/docs" spikes
step "Fertig"
cat "${SUMMARY}"
echo
echo "Ergebnis-Archiv: ${REPO_ROOT}/docs/spikes_ergebnisse.tar.gz"
