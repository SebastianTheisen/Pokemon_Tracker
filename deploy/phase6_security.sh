#!/usr/bin/env bash
# Phase 6: Sicherheits-Check auf dem VPS (liest nur, ändert nichts).
# Ergebnis ohne Geheimnisse und ohne Tailnet-Namen: docs/phase6/security.md
#
#   bash deploy/phase6_security.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
OUT="docs/phase6/security.md"
mkdir -p docs/phase6
mask() { sed -E 's/[a-z0-9-]+\.ts\.net/<tailnet>.ts.net/g; s/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/<mail>/g'; }

{
  echo "# Sicherheits-Check ($(date -u '+%Y-%m-%d %H:%M UTC'))"
  echo
  echo "## Offene Ports von außen (alles außer localhost)"
  echo '```'
  ss -tlnH | awk '{print $4}' | grep -vE '^(127\.|\[::1\]|::1)' | sort -u || true
  echo '```'
  echo
  echo "## Firewall (ufw)"
  echo '```'
  if command -v ufw >/dev/null; then ufw status verbose 2>&1 | head -30; else echo "ufw nicht installiert"; fi
  echo '```'
  echo
  echo "## Veröffentlichte Container-Ports"
  echo '```'
  docker compose ps --format '{{.Service}}: {{.Ports}}'
  echo '```'
  echo
  echo "## Benutzer in den Containern (soll nicht root sein)"
  echo '```'
  for svc in api worker monitor; do
    printf '%s: ' "${svc}"; docker compose exec -T "${svc}" id -un 2>/dev/null || echo "läuft nicht"
  done
  echo '```'
  echo
  echo "## Rechte der .env (soll 600 sein)"
  echo '```'
  stat -c '%a %U' .env
  echo '```'
  echo
  echo "## Sicherheits-Header der App"
  echo '```'
  curl -sI http://127.0.0.1:8000/api/v1/health | grep -iE '^(x-content|x-frame|referrer|permissions|strict)' || echo "keine"
  echo '```'
  echo
  echo "## Ohne Anmeldung (soll 401 sein)"
  echo '```'
  for path in /api/v1/collection/items /api/v1/admin/users /api/v1/cards/search?q=pikachu; do
    printf '%s → %s\n' "${path}" "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000${path}")"
  done
  echo '```'
  echo
  echo "## Tailscale"
  echo '```'
  docker compose exec -T tailscale tailscale serve status 2>&1 | mask | head -10
  printf 'Geräte im Tailnet sichtbar: '
  docker compose exec -T tailscale tailscale status 2>/dev/null | grep -c . || true
  echo '```'
} > "${OUT}"

cat "${OUT}"
echo
echo "Bitte pushen: git add docs/phase6 && git commit -m 'Sicherheits-Check' && git push"
