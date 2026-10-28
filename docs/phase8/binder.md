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

Grenze der Messung: synthetische Seiten, Bildabgleich gegen dieselben Bilder.

## Echtes Foto (28.10.2026)

Foto vom Nutzer: 3×3-Seite, neun japanische SAR aus SV8a (Evoli-Familie, 202–224/187) in
Toploadern in den Binderhüllen, Handy-Foto mit Spiegelungen. Sollwerte von Hand abgelesen.

**Zerlegung.** Vorher fiel das Verfahren auf „3×3 über das ganze Foto“ zurück: Ein Glanz-
Schein-Viereck (Konturfläche kartengroß, Rechteck darum über die halbe Seite und bis y = −72)
„überlappte“ alle Karten der oberen Hälfte und verdrängte sie. Jetzt werden Vierecke, die über
den Bildrand ragen, verworfen, und jedes Viereck wird als Kartenmaß probiert → „konturen“,
6 Umrisse + 3 berechnete Zellen, jede Zelle genau eine Karte (Test
`test_binder_ignores_outlines_beyond_the_photo` baut das Schein-Viereck nach; scheitert mit
dem alten Code).

**Kartennummern** (echte OCR, RapidOCR):

| Variante | richtig gelesen |
|---|---|
| Zelle wie bisher | 3/9 (202, 212, 217) |
| + vergrößert nachlesen, wenn keine Nummer und Karte < 900 px | 5/9 (+206, +224) |
| nur unterer Streifen der inneren Karte | 0/9 (verworfen) |

223 wird als „273/167“ gelesen, 203/205/209 bleiben unlesbar – die Ziffern sind im Foto nur
10–15 px hoch und liegen hinter zwei Lagen Kunststoff.

**Namen** liest die OCR fast immer, aber verfälscht: kleine Kana als große („リーフイア“,
„シヤワーズ“) und das ex-Logo als „X“, „EX“, „OX“, „ビX“. Die Datenbanksuche fand deshalb
*keinen einzigen* Namen. Jetzt: Vergleichsschlüssel mit großen Kana (Python und SQL gleich),
lateinische Reste hinter asiatischen Namen fallen weg, zusätzlich Suche ohne das letzte Zeichen.

**Set der Seite.** Stammen mindestens zwei sicher erkannte Zellen (und die Mehrheit) aus einem
Set, werden die unsicheren Zellen mit diesem Set neu bewertet (+0,15, Begründung „Gleiches Set
wie die übrigen Karten der Seite“). Das macht eine Zelle nie allein *sicher*.

**Ende zu Ende** (API, echte OCR, Mini-Katalog: SV8a mit den neun SAR und den RR-Fassungen
derselben Pokémon, dazu Evoli-Helden und ein weiteres Set mit gleichen Namen; ohne
Katalogbilder, also ohne Bildabgleich):

| | vorher | nachher |
|---|---|---|
| richtige Karte auf Platz 1 | 5/9 | **9/9** |
| davon „sicher“ | 0 | 3 |
| davon nur Gleichstand mit der RR-Fassung gleichen Namens | – | 4 |

Die vier Gleichstände (nur Name lesbar, Set passt) entscheidet im Betrieb der Bildabgleich
gegen die Katalogbilder; ohne ihn ist die Reihenfolge Zufall. Laufzeit: +~4 s je 9er-Seite
für das Nachlesen.
