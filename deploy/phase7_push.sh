#!/usr/bin/env bash
# Phase 7: Preisalarme mit Mitteilungen aufs Handy (Web-Push der PWA) einrichten.
#   1. API, Worker und Überwachung neu bauen (neue Tabellen werden beim Start angelegt)
#   2. VAPID-Schlüssel erzeugen (einmalig, geheim, nur in .env – wird nicht angezeigt)
#   3. Kontaktadresse für die Push-Dienste = Adresse der App (https://kartenkiste.<tailnet>.ts.net)
#   4. API und Worker mit den neuen Einstellungen starten, Web-App neu bauen
#   5. Stand prüfen
# Ergebnis (ohne Geheimnisse): docs/phase7/push.md
#
#   bash deploy/phase7_push.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
OUT="docs/phase7/push.md"
mkdir -p docs/phase7
[[ -f .env ]] || { echo ".env fehlt – zuerst Phase 1 ausführen." >&2; exit 1; }

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }

wait_for_api() {
  for _ in $(seq 1 60); do
    if docker compose exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  fail "API antwortet nicht – Protokoll: docker compose logs --tail 50 api"
}

step "1/5 API, Worker und Überwachung bauen und starten"
docker compose up -d --build api worker monitor
wait_for_api

step "2/5 VAPID-Schlüssel"
if grep -q '^PT_PUSH_VAPID_PRIVATE_KEY=' .env; then
  echo "Schon eingerichtet."
else
  key="$(docker compose exec -T api python -m app.cli push-key | tr -d '\r\n')"
  [[ "${key}" =~ ^[A-Za-z0-9_-]{43}$ ]] || fail "Schlüssel nicht erzeugt."
  printf 'PT_PUSH_VAPID_PRIVATE_KEY=%s\n' "${key}" >> .env
  unset key
  chmod 600 .env
  echo "Neu erzeugt und in .env gespeichert (wird nicht angezeigt)."
fi

step "3/5 Kontaktadresse für die Push-Dienste"
if grep -q '^PT_PUSH_SUBJECT=' .env; then
  echo "Schon eingerichtet."
else
  dns_name="$(docker compose exec -T tailscale tailscale status --json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')" \
    || fail "Tailscale-Container läuft nicht – zuerst: bash deploy/phase5_tailscale.sh"
  printf 'PT_PUSH_SUBJECT=https://%s\n' "${dns_name}" >> .env
  echo "https://kartenkiste.<tailnet>.ts.net"
fi

step "4/5 API und Worker mit den neuen Einstellungen starten, Web-App bauen"
docker compose up -d --force-recreate api worker
wait_for_api
bash deploy/phase5_app.sh --force

step "5/5 Stand"
status="$(docker compose exec -T api python -m app.cli push-status)"
echo "${status}"
grep -q "Push eingerichtet: ja" <<<"${status}" || fail "Push ist nicht eingerichtet."

{
  echo "# Phase 7: Preisalarme mit Web-Push ($(date -u '+%Y-%m-%d %H:%M UTC'))"
  echo
  echo '```'
  echo "${status}"
  echo '```'
} > "${OUT}"

cat <<INFO

Fertig: ${OUT}

Auf dem iPhone:
  1. Kartenkiste vom Home-Bildschirm öffnen (nicht in Safari) – ggf. ganz schließen und neu öffnen.
  2. Mehr → Preisalarme → „Einschalten“ → Mitteilungen erlauben.
  3. „Probe senden“ – die Mitteilung kommt nach wenigen Sekunden.

Bitte pushen: git add docs/phase7 && git commit -m 'Phase 7 Push eingerichtet' && git push
INFO
