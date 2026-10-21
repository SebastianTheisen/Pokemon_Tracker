"""Spike: offizielle PSA Public API – Zertifikat nachschlagen (Karte, Note, Population).

psacard.com selbst blockt Abrufe vom Server (Cloudflare, Spike F). PSA bietet dafür eine
offizielle Schnittstelle mit kostenlosem Token (laut PSA begrenzte Abrufe pro Tag).

    docker compose exec -T -e PSA_CERT=73270136 api python - < deploy/spikes/psa_api.py

Der Token kommt aus ``PT_PSA_TOKEN`` (.env) und wird nie ausgegeben.
"""

from __future__ import annotations

import json
import os

import httpx

API = "https://api.psacard.com/publicapi"
CERT = os.environ.get("PSA_CERT", "73270136")


def main() -> None:
    print("# Spike PSA Public API\n")
    token = os.environ.get("PT_PSA_TOKEN", "").strip()
    if not token:
        print("❌ `PT_PSA_TOKEN` fehlt – zuerst `bash deploy/set_secret.sh PT_PSA_TOKEN`.")
        return
    headers = {"Authorization": f"bearer {token}", "User-Agent": "Kartenkiste/0.1 (Spike)"}
    with httpx.Client(headers=headers, timeout=30) as client:
        for path in (f"/cert/GetByCertNumber/{CERT}", f"/cert/GetImagesByCertNumber/{CERT}"):
            response = client.get(f"{API}{path}")
            print(f"## `{path}` → HTTP {response.status_code}\n")
            try:
                body = response.json()
            except ValueError:
                body = response.text[:500]
            print("```json")
            print(json.dumps(body, ensure_ascii=False, indent=2)[:4000])
            print("```\n")


main()
