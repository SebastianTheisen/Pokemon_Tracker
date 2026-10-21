"""Spike: offizielle PSA Public API – Zertifikat nachschlagen (Karte, Note).

Doku: https://www.psacard.com/publicapi/documentation – ``GET
https://api.psacard.com/publicapi/cert/GetByCertNumber/{nummer}`` mit
``Authorization: bearer <Token>``. Spike 1 bekam HTTP 403 mit Cloudflare-Seite „Just a moment…“.
Dieser Lauf klärt die Ursache:

1. genau wie dokumentiert (Token, ``Accept: application/json``),
2. ohne Token – blockt Cloudflare schon vorher (403 + HTML) oder antwortet die API (401/500)?

Der Token kommt aus ``PT_PSA_TOKEN`` (.env) und wird nie ausgegeben.

    docker compose exec -T -e PSA_CERT=73270136 api python - < deploy/spikes/psa_api.py
"""

from __future__ import annotations

import os

import httpx

URL = "https://api.psacard.com/publicapi/cert/GetByCertNumber/{cert}"
CERT = os.environ.get("PSA_CERT", "73270136")


def describe(label: str, response: httpx.Response) -> None:
    body = response.text.replace("\n", " ")[:600]
    blocked = "Just a moment" in body or "cf-" in response.headers.get("server", "").lower()
    print(f"## {label}\n")
    print(f"- HTTP {response.status_code} · Server: {response.headers.get('server')} · ")
    print(f"  cf-ray: {response.headers.get('cf-ray')} · Cloudflare-Seite: {blocked}")
    print(f"- Inhalt: `{body}`\n")


def main() -> None:
    print("# Spike PSA Public API (2)\n")
    token = os.environ.get("PT_PSA_TOKEN", "").strip()
    print(f"- Token vorhanden: {bool(token)} (Länge {len(token)})\n")
    url = URL.format(cert=CERT)
    with httpx.Client(timeout=30) as client:
        if token:
            describe(
                "Wie dokumentiert (mit Token)",
                client.get(
                    url,
                    headers={"Authorization": f"bearer {token}", "Accept": "application/json"},
                ),
            )
        describe("Ohne Token", client.get(url, headers={"Accept": "application/json"}))
        describe("Doku-Seite psacard.com", client.get("https://www.psacard.com/publicapi"))


main()
