#!/usr/bin/env bash
# Spike: PSA-Zertifikat über die offizielle PSA Public API nachschlagen (kostenlos).
#   bash deploy/phase5_psa_api.sh [Zertifikatsnummer]
# Ergebnis: docs/phase5/psa_api.md (enthält keinen Token)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase5/psa_api.md"
mkdir -p docs/phase5
docker compose exec -T -e PSA_CERT="${1:-73270136}" api python - < deploy/spikes/psa_api.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
cat "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike PSA API' && git push"
