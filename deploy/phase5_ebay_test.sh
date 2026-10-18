#!/usr/bin/env bash
# eBay „Verkaufte Artikel“ – Zugriff vom VPS testen: direkt und (optional) über Tor.
#
# Ehrlicher Test: eine Anfrage je Weg, ehrlicher User-Agent, kein Wechsel von Adressen,
# keine Tricks gegen Sperren. Gemeldet werden nur HTTP-Status und ob Verkäufe zu sehen sind.
# Ergebnis: docs/phase5/ebay_zugriff.md
#
#   bash deploy/phase5_ebay_test.sh                      # nur direkt
#   bash deploy/phase5_ebay_test.sh --tor                # zusätzlich über Tor
#   EBAY_SEARCH="Glurak+Base+Set+4" bash deploy/phase5_ebay_test.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
RESULT="docs/phase5/ebay_zugriff.md"
SEARCH="${EBAY_SEARCH:-Nachtara+VMAX+215}"
URL="https://www.ebay.de/sch/i.html?_nkw=${SEARCH}&LH_Sold=1&LH_Complete=1"
UA="Kartenkiste/0.1 (private Sammel-App; 1 Anfrage je Test)"
use_tor=false
[[ "${1:-}" == "--tor" ]] && use_tor=true

probe() {  # probe <Name> [curl-Optionen …]
  local name="$1"; shift
  local body; body="$(mktemp)"
  local code
  code="$(curl -sS -m 40 -A "${UA}" -o "${body}" -w '%{http_code}' "$@" "${URL}" 2>&1)" || code="Fehler: ${code}"
  local size sold items challenge
  size="$(wc -c < "${body}")"
  sold="$(grep -ciE 'Verkauft|Sold' "${body}" || true)"
  items="$(grep -ciE 's-item__title|s-card__title' "${body}" || true)"
  challenge="$(grep -ciE 'captcha|Pardon Our Interruption|splashui|robot|Zugriff.*verweigert' "${body}" || true)"
  rm -f "${body}"
  echo "| ${name} | ${code} | ${size} | ${items} | ${sold} | ${challenge} |"
}

{
  echo "# eBay-Zugriff vom VPS (Test)"
  echo
  echo "Suche: \`${SEARCH}\` (Verkaufte Artikel). Eine Anfrage je Weg, ehrlicher User-Agent."
  echo
  echo "| Weg | HTTP | Bytes | Treffer-Titel | „Verkauft“-Zeilen | Sperr-Hinweise |"
  echo "|---|---|---:|---:|---:|---:|"
  probe "direkt vom VPS"
  if ${use_tor}; then
    docker compose --profile tor up -d --build tor >/dev/null
    for _ in $(seq 1 40); do
      docker compose logs tor 2>&1 | grep -q "Bootstrapped 100%" && break
      sleep 2
    done
    probe "über Tor" --socks5-hostname 127.0.0.1:9050
    docker compose --profile tor stop tor >/dev/null
  fi
  echo
  echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
  echo
  echo "Deutung: HTTP 200 mit Treffer-Titeln und „Verkauft“-Zeilen = Seite wird normal geliefert."
  echo "Sperr-Hinweise > 0 oder HTTP 403/429/503 = eBay weist den Weg ab."
} | tee "${RESULT}"

echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'eBay-Zugriffstest' && git push"
