#!/usr/bin/env bash
# Phase 5: Fehlende Kartenbilder aus weiteren Quellen (pokemontcg.io, pokemon.com,
# offizielle Datenbanken Japan und Taiwan).
#   1. App und Backend neu bauen (Migration 0006, neue Bildadressen in der App)
#   2. Probelauf: Quellen testen, nichts speichern → docs/phase5/bildimport_probe.md
#   3. Den eigentlichen Import erledigt der Worker im Hintergrund (startet ca. 5 min nach
#      dem Neustart, dauert wegen 1 Anfrage/s einige Stunden). Fortschritt:
#        docker compose exec -T api python -m app.cli image-status
#
#   bash deploy/phase5_bilder.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }

[[ -f backend/app/services/image_import.py ]] || fail "Alter Stand – bitte zuerst 'git pull' ausführen."

step "1/3 App und Backend bauen (ca. 5–15 min)"
bash deploy/phase5_app.sh

step "2/3 Probelauf der Bildquellen (ca. 2 min, speichert nichts)"
docker compose exec -T api python -m app.cli import-images --dry-run \
  --sources pokemon.com jp tw --out /tmp/bildimport_probe.md > /dev/null
docker compose exec -T api cat /tmp/bildimport_probe.md > docs/phase5/bildimport_probe.md
{
  echo
  echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
} >> docs/phase5/bildimport_probe.md
cat docs/phase5/bildimport_probe.md

step "3/3 Hintergrund-Import"
sleep 5
docker compose logs --tail 20 worker | grep -E "image_import|error" || true
echo
echo "Der Worker startet den Import ca. 5 Minuten nach dem Neustart und braucht einige Stunden."
echo "Stand abfragen (jederzeit):"
echo "  cd ~/Pokemon_Tracker/Pokemon_Tracker && docker compose exec -T api python -m app.cli image-status"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Bildimport Probelauf' && git push"
