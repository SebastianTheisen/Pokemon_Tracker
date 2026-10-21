#!/usr/bin/env bash
# Spike: Bilder für versiegelte Produkte aus tcgcsv.com (kostenlos, ~2–5 Minuten).
# Ergebnis: docs/phase5/sealed_images.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase5/sealed_images.md"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/sealed_images.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
cat "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Sealed-Bilder' && git push"
