"""Erzeugt ``app/data/species_names.json`` aus den offenen PokéAPI-Daten.

Quelle: https://github.com/PokeAPI/pokeapi (``data/v2/csv/pokemon_species_names.csv``).
Enthält je Pokémon (nationale Pokédex-Nummer) den Namen auf Deutsch, Englisch, Japanisch
(Kana), Koreanisch und Chinesisch (traditionell/vereinfacht) – die Sprachen des Katalogs.

Aufruf (aus ``backend/``, nur bei neuen Pokémon nötig)::

    uv run python scripts/build_species_names.py
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import httpx

SOURCE = (
    "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/pokemon_species_names.csv"
)
# PokéAPI-Sprach-IDs → Katalogsprachen
LANGUAGES = {"1": "ja", "3": "ko", "4": "zh-tw", "6": "de", "9": "en", "12": "zh-cn"}
TARGET = Path(__file__).resolve().parents[1] / "app" / "data" / "species_names.json"


def main() -> None:
    response = httpx.get(SOURCE, timeout=60, follow_redirects=True)
    response.raise_for_status()
    species: dict[int, dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(response.text)):
        language = LANGUAGES.get(row["local_language_id"])
        if language and row["name"]:
            species.setdefault(int(row["pokemon_species_id"]), {})[language] = row["name"]
    data = {
        "source": SOURCE,
        "license": "PokéAPI (BSD-3-Clause); Namen © Nintendo/Creatures/GAME FREAK",
        "species": {str(key): species[key] for key in sorted(species)},
    }
    TARGET.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(species)} Pokémon geschrieben: {TARGET}")


if __name__ == "__main__":
    main()
