#!/usr/bin/env bash
# Spike: PSA-Zertifikat über die offizielle PSA Public API (kostenlos).
#   bash deploy/phase5_psa_api.sh [Zertifikatsnummer]
# Fragt einmal aus dem API-Container und einmal direkt vom VPS (curl) – so sieht man, ob
# Cloudflare die Server-IP blockt. Ergebnis: docs/phase5/psa_api.md (enthält keinen Token)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
cert="${1:-73270136}"
out="docs/phase5/psa_api.md"
mkdir -p docs/phase5
docker compose exec -T -e PSA_CERT="${cert}" api python - < deploy/spikes/psa_api.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"

{
  echo "## Direkt vom VPS (curl, ohne Docker)"
  echo
  token="$(grep '^PT_PSA_TOKEN=' .env | head -1 | cut -d= -f2- || true)"
  if command -v curl >/dev/null; then
    code="$(curl -s -o /tmp/psa_body.txt -w '%{http_code}' \
      -H "Authorization: bearer ${token}" -H 'Accept: application/json' \
      "https://api.psacard.com/publicapi/cert/GetByCertNumber/${cert}" || echo fehler)"
    echo "- HTTP ${code}"
    echo "- Inhalt: \`$(head -c 400 /tmp/psa_body.txt | tr '\n' ' ')\`"
    rm -f /tmp/psa_body.txt
  else
    echo "- curl nicht installiert"
  fi
  echo
  echo "- Öffentliche IP des VPS (Anbieter): $(curl -s https://ipinfo.io/org || echo unbekannt)"
} >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
cat "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike PSA API 2' && git push"
