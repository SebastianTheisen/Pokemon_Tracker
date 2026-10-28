#!/usr/bin/env bash
# Japanische Classic Collection (CLL/CLF/CLK) erstmals importieren – danach läuft der Abgleich
# mit dem täglichen Cardmarket-Import mit. Quelle tcgcsv.com (3 Abrufe), Verknüpfung mit den
# schon importierten Cardmarket-Ausgaben 5527–5529. Ergebnis: docs/phase8/classic_import.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase8/classic_import.md"
mkdir -p docs/phase8
{
  docker compose exec -T api python -m app.cli classic-import 2>&1 | grep -v -E '^\{|\[(info|debug) ' \
    || echo "(Exit-Code $?)"
  echo
  echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
} > "${out}"
cat "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase8 && git commit -m 'Classic Collection: Import' && git push"
