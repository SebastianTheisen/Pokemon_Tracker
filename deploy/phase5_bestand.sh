#!/usr/bin/env bash
# Bestandsaufnahme: Wo sind Karten, Preise, Bilder, Versiegeltes und Scanner lückenhaft?
# Nur lesend, kostenlos, ca. 1 Minute. Ergebnis: docs/phase5/bestand.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase5/bestand.md"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/bestand.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
head -30 "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Bestandsaufnahme' && git push"
