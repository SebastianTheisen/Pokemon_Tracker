#!/usr/bin/env bash
# Spike Apify, echte Testläufe (max. 0,10 $ je Lauf), dauert einige Minuten.
#   bash deploy/phase5_apify_runs.sh      → Stufe B (docs/phase5/apify_runs.md)
#   bash deploy/phase5_apify_runs.sh C    → Stufe C (docs/phase5/apify_runs_c.md)
#   bash deploy/phase5_apify_runs.sh D    → Stufe D (docs/phase5/apify_runs_d.md)
#   bash deploy/phase5_apify_runs.sh E    → Stufe E (docs/phase5/apify_runs_e.md)
#   bash deploy/phase5_apify_runs.sh F [Zertifikatsnummer] → PSA-Abfrage (apify_runs_f.md)
#   bash deploy/phase5_apify_runs.sh G    → Versiegeltes mit Bild von Cardmarket (apify_runs_g.md)
#   bash deploy/phase5_apify_runs.sh H    → parselab-Karten KO/ZH/JA (apify_runs_h.md)
# Berichte enthalten keinen Token.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
stage="${1:-B}"
out="docs/phase5/apify_runs.md"
[[ "${stage}" != "B" ]] && out="docs/phase5/apify_runs_$(echo "${stage}" | tr '[:upper:]' '[:lower:]').md"
mkdir -p docs/phase5
docker compose exec -T -e APIFY_SPIKE_STAGE="${stage}" -e PSA_CERT="${2:-73270136}" api python - < deploy/spikes/apify_runs.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
if grep -q "apify_api_" "${out}"; then
  echo "Achtung: Der Bericht enthält etwas Token-Ähnliches – nicht pushen!" >&2
  exit 1
fi
cat "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Apify Stufe ${stage}' && git push"
