#!/usr/bin/env bash
# Phase 6: Sicherung und Überwachung einrichten.
#   1. ntfy-Thema erzeugen (einmalig, geheim, nur in .env) und anzeigen → in der ntfy-App abonnieren
#   2. Dienste „backup“ und „monitor“ bauen und starten (Worker neu: Lebenszeichen)
#   3. Erste Sicherung sofort, dann Überwachung einmal prüfen
# Ergebnis (ohne Geheimnisse): docs/phase6/setup.md
#
#   bash deploy/phase6_setup.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
OUT="docs/phase6/setup.md"
mkdir -p docs/phase6 backups
[[ -f .env ]] || { echo ".env fehlt – zuerst Phase 1 ausführen." >&2; exit 1; }

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

step "ntfy-Thema"
if grep -q '^PT_NTFY_TOPIC=' .env; then
  topic="$(grep '^PT_NTFY_TOPIC=' .env | cut -d= -f2-)"
  echo "Schon eingerichtet."
else
  topic="kartenkiste-$(openssl rand -hex 12)"
  printf 'PT_NTFY_TOPIC=%s\n' "${topic}" >> .env
  chmod 600 .env
  echo "Neu erzeugt und in .env gespeichert."
fi
cat <<INFO

  In der App „ntfy“ (App Store / Google Play) auf „+“ tippen und dieses Thema abonnieren:

      ${topic}

  Server: ntfy.sh (Standard). Das Thema ist geheim wie ein Passwort – nicht weitergeben.
INFO

step "Dienste bauen und starten"
docker compose up -d --build api worker backup monitor

step "Erste Sicherung"
docker compose exec -T backup sh /backup.sh now
ls -lh backups | tail -n +2

step "Überwachung einmal prüfen (Worker-Lebenszeichen braucht bis zu 5 Minuten)"
sleep 20
checks="$(docker compose exec -T monitor python -m app.monitor --once 2>/dev/null | grep -E '^(OK|FEHLER)' || true)"
echo "${checks}"

{
  echo "# Phase 6: Einrichtung ($(date -u '+%Y-%m-%d %H:%M UTC'))"
  echo
  echo "## Sicherungen"
  echo '```'
  ls -lh backups | tail -n +2
  echo '```'
  echo
  echo "## Überwachung (einmalige Prüfung)"
  echo '```'
  echo "${checks}"
  echo '```'
} > "${OUT}"

echo
echo "Fertig: ${OUT}. Auf dem Handy sollte jetzt „Kartenkiste: Überwachung läuft“ ankommen."
echo "Bitte pushen: git add docs/phase6 && git commit -m 'Phase 6 Einrichtung' && git push"
