# Auswertung Spike Datenquellen – Lauf 1 (VPS, 17.10.2026)

Rohbericht: [`datenquellen.md`](datenquellen.md) · Zusammenfassung: [`zusammenfassung.md`](zusammenfassung.md)

## TCGdex: ✅ Go als Hauptquelle

| Sprache | Sets |
|---|---|
| de | 155 |
| en | 220 |
| ja | 186 |
| ko | 95 |
| zh-tw | 98 |
| zh-cn | 57 |

- Alle Zielsprachen sind vorhanden. Die Spalte „Beispielkarte: nein“ bei JP/KO/ZH ist **kein Fehler**: Asiatische Sets haben eigene IDs (z. B. `S12` statt `swsh12`). Lauf 2 prüft deshalb gezielt Karten aus asiatischen Sets.
- **Preise (DE-Karte):** Der Block `pricing.cardmarket` liefert Folgendes:

  | Feld | Bedeutung |
  |---|---|
  | `avg` | Durchschnitt |
  | `low` | günstigstes Angebot |
  | `trend` | Trendpreis |
  | `avg1`, `avg7`, `avg30` | Durchschnitt über 1, 7 und 30 Tage |
  | `*-holo` | dieselben Werte für die Holo-/Reverse-Variante |

  Dazu kommen `unit` (EUR), `updated` (Datum) und **`idProduct`**. Über `idProduct` lässt sich ein Link zur Cardmarket-Produktseite bauen, das ist der Beleglink. Zusätzlich gibt es `pricing.tcgplayer` (USD).
- **Beispiel Nachtara VMAX 215:**

  | Feld | Wert |
  |---|---|
  | `trend` | 1.805,90 € |
  | `avg` | 1.830,92 € |
  | `low` | 220 € |

  Der `low`-Wert zeigt, dass der günstigste Preis stark vom Zustand abhängt. Zum Vergleich: SCNDX zeigte für „ab Near Mint“ 1.699,99 €.
- **Felder für Katalog und Scanner** sind vollständig: `localId` (Nummer), `set.id`, `set.cardCount`, `image`, `rarity`, `variants`, `regulationMark` und weitere.
- Noch offen (Lauf 2): Preise für JP/KO/ZH-Karten und der Abruf der Katalogbilder.

## pokemontcg.io: ⚠️ HTTP 500

- Die Anfrage endete mit einem Serverfehler.
- Die Quelle ist nicht nötig: TCGdex liefert dieselben Cardmarket- und TCGplayer-Daten und ist mehrsprachig.
- **Vorschlag:** pokemontcg.io aus dem Plan streichen.

## Cardmarket direkt: ❌ Cloudflare-Sperre

- Schon die **erste einzelne** Anfrage wird mit HTTP 403 und der Cloudflare-Prüfseite („Just a moment“) beantwortet.
- Ohne Umgehung (Browser-Imitation, Captcha-Lösen, IP-Rotation) ist kein Abruf möglich. Laut Plan (5.3) wird keine Umgehung gebaut.
- **Folge:** Der `CardmarketListingProvider` ist so nicht umsetzbar. Zustandspreise kommen dann aus TCGdex (`low`, `trend`, `avg`) und der markierten Schätzung.
- **Entscheidung durch den Nutzer nötig.**

## Docker: ❌ → behoben (nicht verifiziert)

- **Ursache:** `pyproject.toml` verweist auf `README.md`. Die Datei wurde nicht ins Image kopiert, deshalb schlug der Projekt-Build fehl. Lokal nachgestellt mit der Meldung „Readme file does not exist: README.md“.
- **Korrektur:** `README.md` wird jetzt ins Image kopiert. Ins Image kommen nur Laufzeit-Abhängigkeiten (`--no-default-groups`).
- Verifikation im VPS-Lauf 2.

---

# Lauf 2 (VPS, 17.10.2026, Stand `5a2cb1e`)

## Asiatische Karten in TCGdex (Stichprobe: je 2 neueste Sets, je 2 Karten)

| Sprache | Cardmarket-Preis | Katalogbild |
|---|---|---|
| ja | 4/4 (z. B. Lapras ex Promo: Trend 2,22 €) | **0/4** |
| zh-tw | 0/4 | 2/4 |
| zh-cn | 3/4 | **0/4** |

- **Preise:** Für JP-Karten gibt es Cardmarket-Preise, für ZH teilweise. TCGplayer-Preise fehlen bei asiatischen Karten vollständig.
- **Bilder:** Bei asiatischen Karten fehlen sie oft. Das deckt sich mit dem Bildabgleich-Spike, wo bei JP-Kandidaten 50–80 % ohne Bild waren.
- **Katalogbilder (DE):** `low.webp` 27 KB, `high.webp` 112 KB, `high.png` 326 KB, alle abrufbar. Für den Abgleich reicht `high.webp`.

## pokemontcg.io

- Diesmal erreichbar, aber der Cardmarket-Preisstand ist **vom 18.11.2025**, also etwa 11 Monate alt.
- TCGdex liefert aktuelle Preise (Stand 16.10.2026).
- **Empfehlung bleibt: streichen.**

## Cardmarket direkt

Unverändert 403 von Cloudflare. Entscheidung siehe Plan 5.3.

## Docker

✅ Build ok, Health-Check `{"status":"ok","version":"0.1.0"}`. Die Korrektur aus Lauf 1 wirkt.

## OCR-Modell Koreanisch

✅ Download und Start ok (diesmal mit echtem Foto getestet, also aussagekräftig).
