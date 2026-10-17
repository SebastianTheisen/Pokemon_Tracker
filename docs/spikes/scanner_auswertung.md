# Auswertung Spike Scanner (17.10.2026)

Testsatz: 7 Fotos des Nutzers (`scanner_testset/`): 1× DE, 5× JP, 1× ZH, davon 2 PSA-Slabs, 1 Toploader, 1 Sleeve, 2 Screenshots. Aktueller Rohbericht: [`scanner.md`](scanner.md).

## Lauf 1: Kontur → Entzerren → OCR in Zonen (RapidOCR 1.4, Modell CH/EN)

| Kennzahl | Wert |
|---|---|
| Richtiger Kartenausschnitt (laut Debug-Bildern) | **2/7** |
| Name korrekt | 0/7 |
| Nummer korrekt | 1/7 |

Ursachen: Die Konturerkennung greift bei Händen, Slabs, Toploadern, unruhigem Hintergrund und Screenshots das falsche Viereck. Das CH/EN-Modell liest kein Japanisch („ルギアV“ → „半刀V“).

## Lauf 2: OCR auf dem ganzen Foto + Kartenausschnitt (RapidOCR 3.10, PP-OCRv6 mitgeliefert)

| Datei | Soll | Name im Text | Nummer im Text | Bemerkung |
|---|---|---|---|---|
| 01 Schiggy-Slab (Screenshot) | ゼニガメ · 007 | ✅ | ✅ | `No.007` gelesen, Label zensiert |
| 02 Mewtu ex (DE) | Team Rockets Mewtu ex · 231/182 | ≈ | ✅ | „Team Rockets Mewtu“ – das „ex“ ist ein Logo; Setcode `DR` |
| 03 Lugia V (Toploader) | ルギアV · 110/098 | ✅ | ✅ | `S12 F 110/098 SR` |
| 04 Lugia V (Slab, Daumen) | ルギアV · 110/098 | ✅ | ❌ (verdeckt) | Slab-Label: `FA/LUGIA V`, `#110`, `PARADIGM TRIGGER`, `GEM MT 10` |
| 05 Nachtara ex (289×435 px) | ブラッキーex · 217/187 | ≈ | ❌ | „ブラッキー“ ohne „ex“-Logo; Nummer zu klein |
| 06 Lugia (JP) | ルギア · 142/103 | ✅ | ✅ | |
| 07 Karpador (ZH) | 鲤鱼王 · 165/103 | ❌ | ✅ | Setcode `G 30th C` gelesen, Name auf Glitzerfolie nicht |

**Summe:** Name 4/7 exakt (6/7 inkl. „≈“, also ohne Logo-Zusatz), Nummer 5/7. **In jedem der 7 Fotos** ist mindestens ein starkes Merkmal (Nummer, Name oder Slab-Label) vorhanden. Zeit: ca. 0,7 s pro OCR-Durchlauf auf 4 CPU-Kernen (der Spike rechnet doppelt: Foto + Ausschnitt).

## Erkenntnisse

1. **OCR auf dem ganzen Foto schlägt die Konturerkennung.** Sie ist robust gegen Hände, Slabs, Hüllen und Screenshots. Für den Live-Scan begrenzt ein Kartenrahmen in der App den Ausschnitt.
2. **Nummer + Setcode sind die stärksten Merkmale**, sprachunabhängig.
3. **Namen:** DE/EN/JP/ZH werden mit PP-OCRv6 gelesen. Logos wie „ex“, „V“ und „VMAX“ fehlen oft, das muss der Abgleich unscharf auffangen.
4. **Slab-Labels** (PSA) sind komplett lesbar, inklusive Note.
5. **Grenzen:** Sehr kleine Bilder (05) und Namen auf Glitzerfolie (07). Hier muss der Bildabgleich gegen Katalogbilder helfen. Er ist noch nicht testbar (TCGdex hier gesperrt).
6. **Koreanisch:** Dafür gibt es ein eigenes Modell (`korean_PP-OCRv5_rec_mobile`), das heruntergeladen werden muss. Der Download wird auf dem VPS geprüft. Es gibt noch kein koreanisches Testfoto.

## Entscheidung (Nutzer, 17.10.2026)

**Go mit angepasster Strategie inkl. JP/KO-OCR**, siehe Plan-Abschnitt 5.6.
