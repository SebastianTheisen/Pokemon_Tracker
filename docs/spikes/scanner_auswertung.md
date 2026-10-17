# Auswertung Spike Scanner (17.10.2026)

Testsatz: 7 Fotos des Nutzers (`scanner_testset/`): 1× DE, 5× JP, 1× ZH, davon 2 PSA-Slabs, 1 Toploader, 1 Sleeve, 2 Screenshots. Rohbericht: [`scanner.md`](scanner.md).

## Ergebnis Lauf 1 (Pipeline wie geplant: Kontur → Entzerren → OCR in Zonen)

| Kennzahl | Wert |
|---|---|
| Karte „gefunden“ | 7/7, aber **nur 2/7 mit richtigem Ausschnitt** (02, 06 knapp) |
| Name korrekt | 0/7 (02 fast: „Team Rockets MewtuCx“) |
| Nummer korrekt | 1/7 |
| Zeit pro Foto | ca. 0,5 s (CPU, 4 Kerne) |

## Gegenprobe: OCR auf dem ganzen Foto (ohne Kartenerkennung)

| Datei | Gelesen | Bewertung |
|---|---|---|
| 01 Schiggy-Slab (Screenshot) | Slab-Label ist zensiert („0000 XXXX“), alte Karte hat keine Bruchnummer | nicht lösbar per Nummer → Bildabgleich nötig |
| 02 Mewtu ex (DE) | `231/182`, `Team RocketsMewtuCx`, Setcode-Teil `DR` | ✅ Nummer und Name |
| 03 Lugia V (Toploader) | `S12 110/098 SR` (als `512110/098SR`) | ✅ Nummer und Setcode |
| 04 Lugia V (Slab, Daumen) | Label: `2022 POKEMON JPN.SWSH`, `FA/LUGIA V`, `#110`, `PARADIGM TRIGGER`, `GEM MT 10` | ✅ **Slab-Label komplett lesbar** (Set, Name, Nummer, Note) |
| 05 Nachtara ex (289×435 px) | fast nichts | ❌ Auflösung zu gering |
| 06 Lugia (JP) | `142/103` | ✅ Nummer |
| 07 Karpador (ZH) | `跳跃高手` (Attacke), `G306C` ≈ Setcode `30th C`, Nummer verstümmelt (`E0L/591`) | ⚠️ chinesischer Text gut, Nummer nicht |

## Erkenntnisse

1. **Kartenerkennung per Kontur reicht nicht.** Bei Händen, Slabs, Toploadern, unruhigem Hintergrund und Screenshots greift sie das falsche Viereck. Nur bei „Karte flach auf Tisch“ funktioniert sie.
2. **Die Nummer ist das stärkste Merkmal.** Sie ist sprachunabhängig (lateinische Ziffern) und wurde gelesen, wann immer sie sichtbar und scharf war (3 von 4 Fällen). Dazu kommt oft der Setcode (`S12`, `DR…`, `30th C`).
3. **Namen per OCR taugen nur für DE/EN.** Das Standardmodell von RapidOCR ist Chinesisch + Englisch. Chinesisch klappt gut, **Japanisch (Katakana) nicht** („ルギアV“ → „半刀V“). Für JP/KO wären zusätzliche OCR-Modelle nötig.
4. **Slab-Labels sind sehr gut lesbar.** PSA-Label liefert Set, Name, Nummer und Note. Grading-Erkennung ist realistisch.
5. **Ohne Bildabgleich geht es nicht:** alte Karten ohne Bruchnummer (01), verdeckte Nummern, kleine Screenshots. Der Bildabgleich gegen Katalogbilder ist der zweite Pfeiler. Er ist **noch nicht testbar**, weil die Katalogbilder (TCGdex) hier gesperrt sind.
6. Geschwindigkeit ist unkritisch (≈ 0,5 s pro Foto auf CPU).

## Vorschlag für die Scanner-Strategie (Entscheidung durch den Nutzer)

- **Live-Scan:** Die App zeigt einen Kartenrahmen (wie im Original). Erkannt wird nur im Rahmenausschnitt, das ersetzt die fehleranfällige Konturerkennung.
- **Galerie-Fotos:** zuerst Kontur, und wenn diese unplausibel ist, OCR auf dem ganzen Bild.
- **Identifikation in dieser Reihenfolge:**
  1. Setcode + Nummer (sprachunabhängig).
  2. Bildabgleich gegen die Katalogbilder der Kandidaten.
  3. Name nur als Zusatzsignal.
- **Slab:** Label-OCR (PSA/BGS/CGC) als eigener Pfad, liefert auch die Note.
- **JP/KO-OCR-Modelle** erst ergänzen, wenn Setcode + Nummer + Bild nicht reichen.

**Go/No-Go:** **Go mit Anpassung.** Der OCR-Pfad über Nummer und Setcode ist tragfähig. Die Konturerkennung als alleiniger Einstieg ist es nicht. Der Bildabgleich muss noch nachgewiesen werden, sobald Katalogbilder erreichbar sind.
