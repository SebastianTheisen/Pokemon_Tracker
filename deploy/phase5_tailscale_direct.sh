#!/usr/bin/env bash
# Direkte Verbindung Handy ↔ Kartenkiste über Tailscale (statt Umweg über Relay „DERP“).
#
# Der Container „tailscale“ bekommt einen eigenen UDP-Port (Standard 41642, änderbar über
# TS_PORT in .env). Der Port 41641 des Tailscale direkt auf dem VPS (anderes Gerät) und die
# Firewall werden nicht angefasst – die Firewall wird nur angezeigt.
#
#   bash deploy/phase5_tailscale_direct.sh
#
# Danach am Handy die App öffnen (das stößt die Verbindung an) und das Skript erneut starten:
# beim Ping sollte dann „via <IP>:<Port>“ statt „via DERP(…)“ stehen.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }
mask() { sed -E 's/\.[a-z0-9-]+\.ts\.net/.<tailnet>.ts.net/g'; }

port="$(grep -E '^TS_PORT=' .env 2>/dev/null | cut -d= -f2 || true)"
port="${port:-41642}"

step "1/4 Ist UDP-Port ${port} frei?"
owner="$(ss -Huanp "sport = :${port}" 2>/dev/null || true)"
if [[ -n "${owner}" && "${owner}" != *docker-proxy* ]]; then
  echo "${owner}"
  fail "Port ${port} ist belegt. Anderen Port in .env setzen (TS_PORT=…) und erneut starten."
fi
echo "frei (oder schon von Kartenkiste belegt)"

step "2/4 Firewall (nur Anzeige, keine Änderung)"
if command -v ufw >/dev/null; then
  ufw status 2>&1 | head -5
  echo "Hinweis: Von Docker veröffentlichte Ports gelten auch bei aktivem ufw."
else
  echo "ufw nicht installiert."
fi

step "3/4 Container „tailscale“ mit eigenem Port neu starten (App ca. 10 s nicht erreichbar)"
docker compose up -d tailscale
for _ in $(seq 1 30); do
  if docker compose exec -T tailscale tailscale status >/dev/null 2>&1; then break; fi
  sleep 1
done
docker compose port --protocol udp tailscale "${port}" || true

step "4/4 Weg zum Handy"
status="$(docker compose exec -T tailscale tailscale status 2>&1 | mask)"
echo "${status}"
phone_ip="$(awk '$4 == "iOS" || $4 == "android" {print $1; exit}' <<< "${status}")"
if [[ -n "${phone_ip}" ]]; then
  docker compose exec -T tailscale tailscale ping -c 5 --timeout 5s "${phone_ip}" 2>&1 | mask || true
  echo
  echo "„via DERP(…)“ = noch Umweg. Dann am Handy die App öffnen und das Skript nochmal starten."
  echo "„via <IP>:<Port>“ = direkt verbunden."
else
  echo "Kein Handy im Tailnet gefunden."
fi
