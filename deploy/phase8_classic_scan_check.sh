#!/usr/bin/env bash
# Classic-Binder: letzter Scan, Katalogbilder der Classic-Karten und ihrer Doppelgänger.
# Nur lesend. Ergebnis: docs/phase8/classic_scan_check.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase8/classic_scan_check.md"
mkdir -p docs/phase8
docker compose exec -T api python - < deploy/spikes/classic_scan_check.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
cat "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase8 && git commit -m 'Classic: Scan-Prüfung' && git push"
