#!/usr/bin/env bash
# Phase 5, Schritt 1: Tailscale direkt auf dem VPS einrichten und die API per HTTPS
# (Zertifikat unter *.ts.net) im eigenen Tailnet erreichbar machen.
#
#   bash deploy/phase5_tailscale.sh
#
# Interaktiv: Beim ersten Mal erscheint ein Login-Link (am Handy öffnen und bestätigen),
# ggf. ein Link zum Freischalten von HTTPS/Serve. Danach läuft das Skript allein weiter.
# Ergebnis: docs/phase5/tailscale.md (Tailnet-Name wird darin nicht gespeichert)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/phase5"
RESULT="${OUT_DIR}/tailscale.md"
HOSTNAME_TS="kartenkiste"
cd "${REPO_ROOT}"
mkdir -p "${OUT_DIR}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "Bitte als root ausführen."
curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null \
  || fail "API läuft nicht auf 127.0.0.1:8000 – zuerst: docker compose up -d"

step "1/4 Tailscale installieren (offizielles Skript, nur falls noch nicht vorhanden)"
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled >/dev/null 2>&1 || true
tailscale version | head -1

step "2/4 Anmelden (Link am Handy öffnen, mit deinem Tailscale-Konto bestätigen)"
state="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState",""))' || true)"
if [[ "${state}" == "Running" ]]; then
  # Nie umbenennen: Der VPS kann schon für andere Apps im Tailnet hängen (Name = deren URL).
  fail "Tailscale läuft hier schon (anderer Gerätename). Skript bricht ab, um nichts zu überschreiben."
else
  tailscale up --hostname="${HOSTNAME_TS}"
fi

dns_name="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
ts_ip="$(tailscale ip -4 | head -1)"
[[ -n "${dns_name}" ]] || fail "Kein Tailscale-Name – ist MagicDNS im Tailscale-Admin aktiviert?"
echo "Name im Tailnet: ${dns_name} (${ts_ip})"

step "3/4 HTTPS einrichten: https://${dns_name} → API (127.0.0.1:8000)"
echo "Falls ein Link zum Freischalten erscheint: öffnen, „Enable“ bestätigen, Skript wartet."
tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status

step "4/4 Prüfen: Health-Check über HTTPS im Tailnet"
health="keine Antwort"
for _ in $(seq 1 30); do  # das erste Zertifikat kann ein paar Sekunden dauern
  if health="$(curl -fsS --max-time 20 --resolve "${dns_name}:443:${ts_ip}" "https://${dns_name}/api/v1/health" 2>&1)"; then
    break
  fi
  sleep 3
done
echo "Antwort: ${health}"
[[ "${health}" == *'"database":"ok"'* ]] || fail "HTTPS-Check fehlgeschlagen: ${health}"
public_check="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo 0.0.0.0):8000/api/v1/health" || true)"

tailnet_masked="${HOSTNAME_TS}.<tailnet>.ts.net"
{
  echo "# Phase 5 – Tailscale auf dem VPS"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Tailscale: \`$(tailscale version | head -1)\`"
  echo "- Adresse: \`https://${tailnet_masked}\` (vollständiger Name bewusst nicht im Repo)"
  echo "- Health über HTTPS im Tailnet: \`${health}\`"
  echo "- API von außen über die öffentliche IP, Port 8000 (Erwartung: keine Verbindung = 000): \`${public_check}\`"
  echo
  echo '```'
  tailscale serve status 2>&1 | sed "s/${dns_name}/${tailnet_masked}/g"
  echo '```'
} > "${RESULT}"

step "Fertig"
echo "Am Handy (Tailscale-App verbunden) im Browser öffnen:"
echo "  https://${dns_name}/api/v1/health"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Phase 5: Tailscale auf dem VPS' && git push"
