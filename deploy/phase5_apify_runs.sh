#!/usr/bin/env bash
# Spike Apify, Stufe B: echte Testläufe (max. 0,10 $ je Lauf, 5 Läufe), dauert einige Minuten.
# Ergebnis: docs/phase5/apify_runs.md (enthält keinen Token)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/apify_runs.py > docs/phase5/apify_runs.md 2>&1 \
  || echo "(Exit-Code $?)" >> docs/phase5/apify_runs.md
echo >> docs/phase5/apify_runs.md
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> docs/phase5/apify_runs.md
if grep -q "apify_api_" docs/phase5/apify_runs.md; then
  echo "Achtung: Der Bericht enthält etwas Token-Ähnliches – nicht pushen!" >&2
  exit 1
fi
cat docs/phase5/apify_runs.md
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Apify Stufe B' && git push"
