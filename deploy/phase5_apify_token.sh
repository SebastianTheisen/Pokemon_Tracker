#!/usr/bin/env bash
# Apify-API-Token verdeckt abfragen und in die .env eintragen (nie ins Repo, nicht in die
# Shell-Historie). Danach werden API und Worker neu gestartet, damit sie den Token kennen.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
[[ -f .env ]] || { echo ".env fehlt – zuerst Phase 1 ausführen." >&2; exit 1; }

read -r -s -p "Apify-API-Token einfügen (wird nicht angezeigt): " token
echo
token="$(printf '%s' "${token}" | tr -d '[:space:]')"
if [[ ! "${token}" =~ ^[A-Za-z0-9_-]{20,}$ ]]; then
  echo "Das sieht nicht wie ein Apify-Token aus (erwartet z. B. apify_api_…). Nichts geändert." >&2
  exit 1
fi

# Alte Zeile entfernen, neue anhängen; Datei bleibt nur für root lesbar.
tmp="$(mktemp)"
grep -v '^PT_APIFY_TOKEN=' .env > "${tmp}" || true
printf 'PT_APIFY_TOKEN=%s\n' "${token}" >> "${tmp}"
cat "${tmp}" > .env
rm -f "${tmp}"
chmod 600 .env
echo "Token in .env eingetragen (Ende: …${token: -4})."

docker compose up -d --force-recreate api worker
echo "API und Worker neu gestartet."
