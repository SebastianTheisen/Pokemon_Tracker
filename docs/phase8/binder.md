# Binder-Scan: Messung der Zerlegung (28.10.2026)

Anlass: Rückmeldung „Erkennung einer Binderseite sehr miserabel“. Ursache im Code: Fand die
Konturensuche nicht alle Karten (typisch: Glanzstreifen der Schutzhüllen verdecken Umrisse),
**fielen die übrigen Karten stillschweigend weg** und Reihe/Spalte verrutschten. Ohne Umrisse
wurde das *ganze Foto* inklusive Tisch in 3×3 geteilt – die Zellen schnitten durch die Karten.

Messaufbau: `deploy/spikes/binder_bench.py` – synthetische Seiten aus den Testkarten
(Hüllen, dunkle Seite, Tisch, Schräglage, Glanz). Gezählt: Zelle an richtiger Stelle zeigt
per Bildabgleich die richtige Karte; fehlende Zellen zählen als falsch.

| Fall | vorher | nachher |
|---|---|---|
| 9er randlos | 9/9 | 9/9 |
| 9er mit Tisch 12 % | 9/9 | 9/9 |
| 9er Tisch + schräg | 9/9 | 9/9 |
| 9er Tisch + schräg + Glanz | **0/9** | 9/9 |
| 12er quer + Tisch | 12/12 | 12/12 |
| 9er randlos + Glanz | **0/9** | 8/9 |
| 9er Tisch + 2× Glanz | 9/9 | 9/9 |
| 12er quer + Glanz | **5/12** | 12/12 |
| 9er Tisch 20 % + schräg | 9/9 | 9/9 |
| **Gesamt** | **62/87 (71 %)** | **86/87 (99 %)** |

Zusätzlich: In allen geschätzten Zellen (Position berechnet statt Umriss gefunden) findet die
Einzelkarten-Erkennung die ganze Karte (27/27) – wichtig für die Texterkennung, die anders als
der Bildabgleich keine halben Karten verzeiht.

Änderungen: Raster aus den gefundenen Karten vervollständigen (Kartengröße, Abstand,
Lücken, Ränder), ohne Umrisse erst die Seite im Foto suchen und sie teilen, in geschätzten
Zellen die Karte selbst zuschneiden.

Grenze der Messung: synthetische Seiten, Bildabgleich gegen dieselben Bilder. Echte Fotos
(Spiegelungen, gewölbte Hüllen, abweichende Katalogbilder) fehlen noch – dafür 2–3 Fotos
echter Binderseiten.
