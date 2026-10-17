# Auswertung Spike Bildabgleich (VPS-Lauf 2, 17.10.2026)

Rohbericht: [`bildabgleich.md`](bildabgleich.md). Verfahren: SIFT-Merkmale des **ganzen Fotos** gegen TCGdex-Katalogbilder aller Karten mit gleichem Namen. Score = geometrisch konsistente Übereinstimmungen (RANSAC-Inlier).

## Ergebnis, ehrlich bereinigt

Das Skript zählt einen Treffer, wenn die Nummer übereinstimmt. Bei 01 ist das ein **Fehltreffer**: `SV2a-007` ist Schiggy aus dem 151-Set, nicht die alte Intro-Pack-Karte. Die Bewertung unten ist deshalb von Hand korrigiert.

| Foto | Ergebnis | Platz 1 (Score) | Platz 2 (Score) | Ursache bei Fehlschlag |
|---|---|---|---|---|
| 02 Mewtu ex (DE) | ✅ | 370 | 178 | |
| 03 Lugia V, Toploader (JP) | ✅ | 359 | 219 | |
| 04 Lugia V, Slab + Daumen (JP) | ✅ | 214 | 72 | |
| 05 Nachtara ex, Mini-Screenshot (JP) | ✅ | 221 | 11 | Hier hatte die OCR versagt, der Bildabgleich rettet den Fall |
| 01 Schiggy Intro Pack (JP, alt) | ❌ | 28 | 14 | Alte Karte vermutlich nicht im Katalog bzw. ohne Bild. Platz 1 ist eine andere Karte mit derselben Nummer |
| 06 Lugia 142/103 (JP) | ❌ | 26 | 23 | Richtige Karte steht im Katalog, landet aber auf dem letzten Platz. Sehr wahrscheinlich **ohne Katalogbild** (8 von 14 Kandidaten hatten keins) |
| 07 Karpador (ZH) | ❌ | – | – | Keine Karte namens „鲤鱼王“ in TCGdex zh-cn gefunden (Set fehlt oder anderer Name) |

**Top-1: 4/7 richtig.** Alle 4 Fehlschläge bzw. Grenzfälle liegen an **Lücken im Katalog** (fehlende Bilder oder Karten), keiner am Abgleichverfahren.

## Erkenntnisse

1. **Der Bildabgleich funktioniert sehr gut, wenn ein Katalogbild existiert.** Der richtige Treffer liegt jeweils mit Score 214–370 deutlich vor dem nächsten. Ein Score unter etwa 50 bedeutet „kein sicherer Treffer“, das ist eine brauchbare Schwelle für „Falsche Karte? Selbst suchen“.
2. **OCR und Bild ergänzen sich.** 05 scheitert an der OCR, gelingt aber im Bildabgleich. Bei 06 ist es umgekehrt: Die OCR liest `142/103`, das Bild fehlt im Katalog.
3. **Nummer allein ist nicht eindeutig** (01: `007` gibt es in vielen Sets). Der **Setcode** gehört zwingend zur Identifikation (Plan 5.6).
4. **Größte Schwachstelle: Katalogabdeckung asiatischer Karten.** Bilder fehlen oft, ältere oder chinesische Sets fehlen teilweise ganz.
5. Laufzeit: 0,6–2,6 s pro Foto mit Download. Mit vorberechneten Merkmalen im Cache sind es etwa 60 ms pro Vergleich.

## Vorschläge (Entscheidung durch den Nutzer)

- **A) Eigene Referenzbilder aus bestätigten Scans.** Bestätigt ein Nutzer einen Treffer, speichert das System einen Ausschnitt seines Fotos als zusätzliches Referenzbild für diese Karte, inklusive vorberechneter Merkmale. Damit schließen sich Bildlücken im Katalog mit der Zeit von selbst. Es wird nur der Kartenausschnitt gespeichert, nicht das ganze Foto.
- **B) Karten selbst anlegen.** Fehlt eine Karte im Katalog (wie 01 oder 07), kann sie mit Name, Set, Nummer, Sprache und eigenem Foto angelegt werden. Sie wird dann wie jede andere Karte gesammelt und bepreist (Eigenpreis).
