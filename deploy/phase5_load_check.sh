#!/usr/bin/env bash
# Lädt die App am Handy nicht („Datei nicht geladen: /main.dart.js“)? Prüft nacheinander:
#   1. Ist main.dart.js nach dem Bauen vollständig da?
#   2. Liefert die API sie direkt aus (127.0.0.1)?
#   3. Kommt sie über Tailscale (HTTPS *.ts.net) an – vom VPS aus über das Tailnet?
#   4. Ist das Handy im Tailnet erreichbar, direkt oder über Umweg (Relay)?
#   5. Meldungen von Tailscale der letzten 10 Minuten.
# Nur lesend; die Tailnet-Adresse wird in der Ausgabe unkenntlich gemacht.
#
#   bash deploy/phase5_load_check.sh [IP-des-Handys-im-Tailnet]
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

phone_ip="${1:-}"
mask() { sed -E 's/\.[a-z0-9-]+\.ts\.net/.<tailnet>.ts.net/g'; }
step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
timing='%{http_code} · %{size_download} Bytes · %{time_total} s\n'

step "1/5 Datei main.dart.js"
ls -la app/build/web/main.dart.js 2>&1

step "2/5 Direkt von der API"
curl -sS -o /dev/null -w "lokal: ${timing}" -H 'Accept-Encoding: gzip' \
  http://127.0.0.1:8000/main.dart.js 2>&1

step "3/5 Über Tailscale (HTTPS)"
host="$(docker compose exec -T tailscale tailscale status --json 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' \
  2>/dev/null)"
if [[ -n "${host}" ]]; then
  curl -sS -o /dev/null --max-time 60 -w "tailnet: ${timing}" -H 'Accept-Encoding: gzip' \
    "https://${host}/main.dart.js" 2>&1 | mask
else
  echo "Tailscale-Adresse nicht ermittelt (Container läuft?)"
fi

step "4/5 Geräte im Tailnet und Weg zum Handy"
status="$(docker compose exec -T tailscale tailscale status 2>&1 | mask)"
echo "${status}"
if [[ -z "${phone_ip}" ]]; then
  phone_ip="$(awk '$4 == "iOS" || $4 == "android" {print $1; exit}' <<< "${status}")"
fi
if [[ -n "${phone_ip}" ]]; then
  echo "Ping an ${phone_ip}:"
  docker compose exec -T tailscale tailscale ping -c 3 --timeout 5s "${phone_ip}" 2>&1 | mask
else
  echo "Kein Handy im Tailnet gefunden."
fi

step "5/5 Tailscale-Meldungen (10 min)"
docker compose logs --since 10m tailscale 2>&1 \
  | grep -viE "magicsock|netcheck|derp" | tail -10 | mask
echo
