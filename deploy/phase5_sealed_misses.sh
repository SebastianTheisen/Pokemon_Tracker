#!/usr/bin/env bash
# Spike: Warum bekommen versiegelte Produkte kein Bild? (kostenlos, ~2–5 Minuten, nur lesend)
# Ergebnis: docs/phase5/sealed_images_misses.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase5/sealed_images_misses.md"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/sealed_images_misses.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
tail -40 "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Sealed-Bilder Fehlschlaege' && git push"
