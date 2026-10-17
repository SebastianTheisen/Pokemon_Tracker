#!/usr/bin/env bash
# Phase 5, Schritt 1: Kartenkiste als eigenes Tailscale-Gerät „kartenkiste“ (Docker-Container).
# Ein Tailscale, das direkt auf dem VPS für andere Apps läuft, wird NICHT angefasst.
#
#   bash deploy/phase5_tailscale.sh
#
# Beim ersten Start ohne TS_AUTHKEY erscheint ein Login-Link (am Handy öffnen, bestätigen).
# Ergebnis: docs/phase5/tailscale.md (Tailnet-Name wird darin nicht gespeichert)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/phase5"
RESULT="${OUT_DIR}/tailscale.md"
cd "${REPO_ROOT}"
mkdir -p "${OUT_DIR}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }
mask() { sed -E 's/\.[a-z0-9-]+\.ts\.net/.<tailnet>.ts.net/g'; }
json_field() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }
ts() { docker compose exec -T tailscale tailscale "$@"; }

[[ -f .env ]] || fail ".env fehlt – zuerst Phase 1 ausführen."

step "1/5 Tailscale direkt auf dem VPS prüfen (wird nicht verändert)"
host_dns=""
if command -v tailscale >/dev/null; then
  host_dns="$(tailscale status --json 2>/dev/null | json_field 'd["Self"]["DNSName"]' 2>/dev/null || true)"
  echo "VPS-Gerät: ${host_dns:-nicht angemeldet}" | mask
  if [[ "${host_dns}" == kartenkiste.* ]]; then
    fail "Das VPS-Gerät heißt noch „kartenkiste“. Erst alten Namen zurücksetzen: tailscale set --hostname=<alter Name>"
  fi
else
  echo "Kein Tailscale direkt auf dem VPS."
fi

step "2/5 Container „tailscale“ starten"
docker compose up -d tailscale

step "3/5 Anmelden (falls ein Link erscheint: am Handy öffnen und bestätigen)"
shown_link=""
state=""
for _ in $(seq 1 120); do
  state="$(ts status --json 2>/dev/null | json_field 'd.get("BackendState","")' 2>/dev/null || true)"
  [[ "${state}" == "Running" ]] && break
  link="$(docker compose logs tailscale 2>&1 | grep -oE 'https://login\.tailscale\.com/[A-Za-z0-9/._-]+' | tail -1 || true)"
  if [[ -n "${link}" && "${link}" != "${shown_link}" ]]; then
    printf '\n  Login-Link: \033[1m%s\033[0m\n\n' "${link}"
    shown_link="${link}"
  fi
  sleep 5
done
[[ "${state}" == "Running" ]] || { docker compose logs --tail 30 tailscale; fail "Nicht angemeldet (Status: ${state:-unbekannt})."; }

status_json="$(ts status --json)"
dns_name="$(json_field 'd["Self"]["DNSName"].rstrip(".")' <<<"${status_json}")"
ts_ip="$(json_field 'd["Self"]["TailscaleIPs"][0]' <<<"${status_json}")"
echo "Gerät im Tailnet: ${dns_name}" | mask
[[ "${dns_name}" == kartenkiste.* ]] || echo "Hinweis: Name ist nicht „kartenkiste“ (Name schon vergeben?)."

step "4/5 HTTPS-Weiterleitung (aus deploy/tailscale/serve.json)"
serve_status="$(ts serve status 2>&1 || true)"
echo "${serve_status}" | mask

step "5/5 Health-Check über HTTPS im Tailnet"
health="nicht geprüft (kein Tailscale direkt auf dem VPS) – bitte am Handy öffnen"
if [[ -n "${host_dns}" ]]; then
  health="keine Antwort"
  for _ in $(seq 1 30); do  # das erste Zertifikat dauert ein paar Sekunden
    if health="$(curl -fsS --max-time 20 --resolve "${dns_name}:443:${ts_ip}" "https://${dns_name}/api/v1/health" 2>&1)"; then
      break
    fi
    sleep 3
  done
  echo "Antwort: ${health}"
  [[ "${health}" == *'"database":"ok"'* ]] || fail "HTTPS-Check fehlgeschlagen: ${health}"
fi
host_serve="$( (tailscale serve status 2>&1 || true) | mask)"

{
  echo "# Phase 5 – Tailscale (eigenes Gerät „kartenkiste“ im Container)"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Tailscale im Container: \`$(ts version | head -1)\`"
  echo "- Adresse: \`https://${dns_name}\`" | mask
  echo "- Health über HTTPS im Tailnet: \`${health}\`"
  echo
  echo "## Weiterleitung des Containers"
  echo
  echo '```'
  echo "${serve_status}" | mask
  echo '```'
  echo
  echo "## Tailscale direkt auf dem VPS (andere Apps, unverändert)"
  echo
  echo '```'
  echo "${host_serve:-kein Tailscale auf dem VPS}"
  echo '```'
} > "${RESULT}"

step "Fertig"
echo "Am Handy (Tailscale-App verbunden) im Browser öffnen:"
echo "  https://${dns_name}/api/v1/health"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Phase 5: Tailscale-Container' && git push"
