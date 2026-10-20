#!/usr/bin/env bash
# Spike Apify, Stufe A (kostenlos, startet nichts): Konto, Guthaben, Eingabefelder der Kandidaten.
# Ergebnis: docs/phase5/apify_probe.md (enthält keinen Token)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/apify_probe.py > docs/phase5/apify_probe.md 2>&1 \
  || echo "(Exit-Code $?)" >> docs/phase5/apify_probe.md
echo >> docs/phase5/apify_probe.md
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> docs/phase5/apify_probe.md
if grep -q "apify_api_" docs/phase5/apify_probe.md; then
  echo "Achtung: Der Bericht enthält etwas Token-Ähnliches – nicht pushen!" >&2
  exit 1
fi
cat docs/phase5/apify_probe.md
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Apify Stufe A' && git push"
