"""Letzte Collectr-Vorschau anzeigen: was das Lesezeichen geliefert hat (Rohzeilen je Kachel)
und welche Katalogkarten der Server vorgeschlagen hat. Nur lesend, im api-Container.

    docker compose exec -T -e FILTER="Kahili" api python - < deploy/spikes/collectr_last.py

FILTER (optional): nur Kacheln, deren Text das enthält, oder ein Status
(``matched``, ``check``, ``missing``, ``unlesbar``).
"""

from __future__ import annotations

import json
import os

from app.core.config import get_settings

folder = get_settings().scanner_data_dir / "collectr"
files = sorted(folder.glob("*.json"), key=lambda f: f.stat().st_mtime) if folder.exists() else []
if not files:
    print("Noch keine Collectr-Vorschau gespeichert – Lesezeichen einmal ausführen.")
    raise SystemExit
data = json.loads(files[-1].read_text(encoding="utf-8"))
wanted = os.environ.get("FILTER", "").strip().casefold()
rows = data["rows"]
counts: dict[str, int] = {}
for row in rows:
    counts[row["status"]] = counts.get(row["status"], 0) + 1
print(f"# Portfolio: {data.get('portfolio')} · {len(rows)} Kacheln · {counts}\n")
for row in rows:
    text = " | ".join(row["lines"])
    if wanted and wanted not in text.casefold() and wanted != row["status"]:
        continue
    print(f"[{row['index']:>3}] {row['status']:<8} {text}")
    for match in row["matches"][:3]:
        print(
            f"        → {match['score']:.2f}  {match['set']} {match['number']} "
            f"{match['name']} ({match['language']})"
        )
