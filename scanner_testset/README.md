# Scanner-Testsatz

Fester Testsatz für den Scanner (`python -m app.cli scan-eval`, Phase-0-Spikes in `backend/scripts/`). Die Soll-Werte stehen in `soll.csv`:

- `karte` (optional): erwartete TCGdex-ID. Leer = Treffer mit gleicher Nummer und Sprache zählt als richtig.
- `karte = -`: Karte ist nicht im Katalog. Richtig ist dann, dass der Scanner **unsicher** meldet.

Neue Fotos einfach in den Ordner legen und eine Zeile in `soll.csv` ergänzen.

| Datei | Karte | Sprache | Besonderheit |
|---|---|---|---|
| 01.jpg | Schiggy (ゼニガメ), Intro Pack, No. 007 | JP | PSA-10-Slab, Website-Screenshot, alte Karte ohne Setnummer |
| 02.jpg | Team Rockets Mewtu ex, 231/182 | DE | Full Art, liegt auf Bettlaken, klein im Bild |
| 03.jpg | Lugia V (ルギアV), s12, 110/098 SR | JP | Toploader, in der Hand, Spiegelungen |
| 04.jpg | Lugia V (ルギアV), 110/098 SR | JP | PSA-10-Slab, Daumen verdeckt die Nummer, Slab-Label lesbar |
| 05.jpg | Nachtara ex (ブラッキーex), 217/187 | JP | Kleiner Screenshot (289×435 px) |
| 06.jpg | Lugia (ルギア), 142/103 | JP | Liegt flach auf dunklem Untergrund, gute Bedingungen |
| 07.jpg | Karpador (鲤鱼王), 165/103 | ZH (vereinfacht) | Sleeve, in der Hand, unruhiger Hintergrund |
