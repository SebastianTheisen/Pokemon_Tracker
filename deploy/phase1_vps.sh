#!/usr/bin/env bash
# Phase 1 auf dem VPS: Backend starten, ersten Admin anlegen, Katalog importieren, Suche prüfen.
# Ergebnisse landen in docs/phase1/.
#
# Aufruf aus dem Repo-Wurzelverzeichnis:
#   bash deploy/phase1_vps.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/phase1"
RESULT="${OUT_DIR}/ergebnis.md"
cd "${REPO_ROOT}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[Hinweis]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }

command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 \
  || fail "Docker mit Compose-Plugin wird benötigt."
mkdir -p "${OUT_DIR}"

step "1/6 Konfiguration (.env)"
if [[ ! -f .env ]]; then
  cp .env.example .env
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
  sed -i "s/^PT_JWT_SECRET=.*/PT_JWT_SECRET=$(openssl rand -hex 32)/" .env
  sed -i "s/^PT_ENVIRONMENT=.*/PT_ENVIRONMENT=production/" .env
  chmod 600 .env
  echo ".env mit zufälligem Datenbank-Passwort und JWT-Schlüssel angelegt (nur für root lesbar)."
  # Der Docker-Test aus Phase 0 hat ein leeres Datenbank-Volume mit dem Platzhalter-Passwort
  # hinterlassen. Mit dem neuen Passwort wäre es nicht mehr nutzbar → einmalig entfernen.
  if docker volume ls -q | grep -q "_db-data$"; then
    warn "Entferne das leere Test-Datenbank-Volume aus Phase 0 (enthält keine Daten)."
    docker compose down -v
  fi
else
  echo ".env vorhanden – wird unverändert verwendet."
fi
set -a; source .env; set +a

step "2/6 Backend bauen und starten"
docker compose up --build -d
health="keine Antwort"
for _ in $(seq 1 60); do
  if health_json="$(curl -fsS http://127.0.0.1:8000/api/v1/health 2>/dev/null)"; then
    health="${health_json}"
    break
  fi
  sleep 2
done
[[ "${health}" == *'"database":"ok"'* ]] || {
  docker compose logs --tail 60 api
  fail "API nicht gesund: ${health}"
}
echo "Health: ${health}"

psql_db() {
  docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc "$1"
}

step "3/6 Erster Admin"
admin_count="$(psql_db "SELECT count(*) FROM users WHERE role = 'admin'")"
if [[ "${admin_count}" == "0" ]]; then
  read -r -p "E-Mail des Admins: " admin_email
  read -r -p "Anzeigename des Admins: " admin_name
  docker compose exec api python -m app.cli create-admin --email "${admin_email}" --name "${admin_name}"
else
  echo "Es gibt bereits ${admin_count} Admin(s) – übersprungen."
fi

step "4/6 Katalog importieren (alle Sprachen; beim ersten Mal einige Minuten)"
sync_status="✅"
if ! docker compose exec -T api python -m app.cli sync-catalog | tee "${OUT_DIR}/katalog_sync.txt"; then
  sync_status="⚠️ mit Fehlern (siehe katalog_sync.txt)"
fi

step "5/6 Katalog zählen"
counts="$(psql_db "SELECT s.language, count(DISTINCT s.id), count(c.id), count(c.image_url)
                   FROM card_sets s LEFT JOIN cards c ON c.set_id = s.id
                   GROUP BY s.language ORDER BY s.language" | tr '|' ' ')"
echo "${counts}"

step "6/6 Suche testen"
searches=("nachtara 215" "umbreon 215" "NACHTRA 215" "glurak" "Team Rockets Mewtu ex 231" "ルギアV 110" "ブラッキーex 217" "鲤鱼王" "7")
search_output=""
for query in "${searches[@]}"; do
  result="$(docker compose exec -T api python -m app.cli search "${query}" --limit 5 2>&1 || true)"
  search_output+=$'\n'"### \`${query}\`"$'\n\n```\n'"${result}"$'\n```\n'
  printf '\n> %s\n%s\n' "${query}" "${result}"
done

{
  echo "# Phase 1 – Ergebnisse vom VPS"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Git-Stand: $(git rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  echo "- Health: \`${health}\`"
  echo "- Katalog-Import: ${sync_status}"
  echo
  echo "## Katalog je Sprache"
  echo
  echo "| Sprache | Sets | Karten | mit Bild |"
  echo "|---|---|---|---|"
  while read -r lang sets cards images; do
    [[ -n "${lang}" ]] && echo "| ${lang} | ${sets} | ${cards} | ${images} |"
  done <<< "${counts}"
  echo
  echo "## Import-Protokoll"
  echo
  echo '```'
  cat "${OUT_DIR}/katalog_sync.txt"
  echo '```'
  echo
  echo "## Suchtests"
  echo "${search_output}"
} > "${RESULT}"

step "Fertig"
echo "Ergebnis: ${RESULT}"
echo
echo "Ergebnisse zurückschicken:"
echo "  git add docs/phase1 && git commit -m 'Phase 1: Ergebnisse vom VPS' && git push"
