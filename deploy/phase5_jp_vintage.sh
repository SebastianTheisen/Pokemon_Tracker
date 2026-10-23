#!/usr/bin/env bash
# Spike: Bilder japanischer Vintage-Karten von PriceCharting (Apify, ~0,03 $, speichert nichts).
# Ergebnis: docs/phase5/jp_vintage.md (enthält keinen Token)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase5/jp_vintage.md"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/jp_vintage.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
if grep -q "apify_api_" "${out}"; then
  echo "Achtung: Der Bericht enthält etwas Token-Ähnliches – nicht pushen!" >&2
  exit 1
fi
tail -30 "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike JP Vintage' && git push"
