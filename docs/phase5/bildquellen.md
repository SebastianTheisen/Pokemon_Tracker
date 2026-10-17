# Spike: offizielle Kartendatenbanken als Bildquelle

## Deutsch und Englisch

### Karten ohne Bild in unserem Katalog (Stichprobe)

| Sprache | Karte | Set | TCGdex-Bild direkt | pokemontcg.io | pokemon.com |
|---|---|---|---|---|---|
| de | Wagong SV068 | swsh4.5sv | – | 404 image/png 186316 B | 404 text/html 345 B |
| de | Pelzebub SV084 | swsh4.5sv | – | 404 image/png 186316 B | 404 text/html 345 B |
| de | Cryospino 035 | B2a | – | 404 image/png 186316 B | 404 text/html 345 B |
| de | Nio TG24 | swsh10tg | – | 200 image/png 718366 B | 200 image/png 195961 B |
| de | Evoli GX SM242 | smp | – | 200 image/png 325292 B | 200 image/png 143663 B |
| de | Jugong H06 | ecard3 | – | 404 image/png 186316 B | 404 text/html 345 B |
| de | Guardevoir TG05 | swsh12tg | – | 200 image/png 701751 B | 200 image/png 194702 B |
| de | Chelast GG31 | swsh12.5gg | – | 404 image/png 186316 B | 404 text/html 345 B |
| en | Rillaboom V SV105 | swsh4.5sv | – | 404 image/png 186316 B | 404 text/html 345 B |
| en | Weavile 021 | mep | – | 404 image/png 186316 B | 404 text/html 345 B |
| en | Lightning Energy 6 | tk-hs-r | – | 404 image/png 186316 B | 404 text/html 345 B |
| en | Mesagoza 093 | B2a | – | 404 image/png 186316 B | 404 text/html 345 B |
| en | Blastoise GX SM189 | smp | 404 text/html, image/webp 146 B | 200 image/png 385645 B | 200 image/png 144379 B |
| en | Falinks TG07 | swsh10tg | – | 200 image/png 622890 B | 200 image/png 55708 B |
| en | Hau 19 | tk-sm-r | – | 404 image/png 186316 B | 404 text/html 345 B |
| en | Poochyena GG33 | swsh12.5gg | – | 404 image/png 186316 B | 404 text/html 345 B |

### Offizielle Bild-Adressen von pokemon.com (bekannte Karten)

- Nachtara VMAX DE (alt): 200 image/png 217610 B – `https://assets.pokemon.com/assets/cms2-de-de/img/cards/web/SWSH7/SWSH7_DE_215.png`
- Nachtara VMAX DE (neu): 200 image/png 217610 B – `https://assets.pokemon.com/static-assets/content-assets/cms2-de-de/img/cards/web/SWSH7/SWSH7_DE_215.png`
- Umbreon VMAX EN (alt): 200 image/png 59004 B – `https://assets.pokemon.com/assets/cms2/img/cards/web/SWSH7/SWSH7_EN_215.png`
- Umbreon VMAX EN (neu): 200 image/png 59004 B – `https://assets.pokemon.com/static-assets/content-assets/cms2/img/cards/web/SWSH7/SWSH7_EN_215.png`
- SV08 162 DE: 200 image/png 141982 B – `https://assets.pokemon.com/static-assets/content-assets/cms2-de-de/img/cards/web/SV08/SV08_DE_162.png`
- SV08 162 EN: 200 image/png 134906 B – `https://assets.pokemon.com/static-assets/content-assets/cms2/img/cards/web/SV08/SV08_EN_162.png`
- Grundset Glurak EN: 404 text/html 345 B – `https://assets.pokemon.com/assets/cms2/img/cards/web/BS/BS_EN_4.png`
- Kartendatenbank DE: 200 text/html 458429 B
- pokemontcg.io API (swsh7 215): 200 application/json 2036 B
- pokemontcg.io Bild (swsh7 215): 200 image/png 792631 B

## Japan – pokemon-card.com

- robots.txt: 404
- Suche `(alle)`: HTTP 200, Treffer 23492, Seiten 603, Felder: ['cardID', 'cardNameAltText', 'cardNameViewText', 'cardThumbFile']
- Suche `ピカチュウex`: HTTP 200, Treffer 23492, Seiten 603, Felder: ['cardID', 'cardNameAltText', 'cardNameViewText', 'cardThumbFile']
  - Beispiel: `{'cardID': '50613', 'cardThumbFile': '/assets/images/card_images/large/M6a/050613_P_TAMATAMA.jpg', 'cardNameAltText': 'タマタマ', 'cardNameViewText': 'タマタマ'}`
  - Detail HTTP 200: Name タマタマ, Nummer &nbsp;001&nbsp;/&nbsp;103&nbsp;, Regulierung/Set M6a
  - Bild-URL: `https://www.pokemon-card.com/assets/images/card_images/large/M6a/050613_P_TAMATAMA.jpg`
  - Bild ohne Referer: HTTP 200, image/jpeg, 241463 Bytes, CORS: –
  - Bild fremder Referer: HTTP 200, image/jpeg, 241463 Bytes, CORS: –
  - Bild fremder Origin: HTTP 200, image/jpeg, 241463 Bytes, CORS: –
- Suche `ルギア`: HTTP 200, Treffer 23492, Seiten 603, Felder: ['cardID', 'cardNameAltText', 'cardNameViewText', 'cardThumbFile']
- Suche `コイキング`: HTTP 200, Treffer 23492, Seiten 603, Felder: ['cardID', 'cardNameAltText', 'cardNameViewText', 'cardThumbFile']

## Korea – pokemoncard.co.kr

- robots.txt: 410
- Suche: HTTP 410, kein JSON: '<html>\r\n<head><title>410 Gone</title></head>\r\n<body bgcolor="white">\r\n<center><h1>410 Gone</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'

## Taiwan (traditionelles Chinesisch) – asia.pokemon-card.com/tw

- robots.txt: `leer`
- Liste HTTP 200: 20 Karten auf Seite 1, Gesamt: 14587
  - Detail HTTP 200: 基礎
             
                        蛋蛋, Nummer 001/103
  - Bild-URL: `https://asia.pokemon-card.com/tw/card-img/tw00019913.png`
  - Bild ohne Referer: HTTP 200, image/png, 1599657 Bytes, CORS: –
  - Bild fremder Referer: HTTP 200, image/png, 1599657 Bytes, CORS: –
  - Bild fremder Origin: HTTP 200, image/png, 1599657 Bytes, CORS: –

## Abdeckung unseres Katalogs (mit Bild / gesamt)

Vorher:
```
de: 14860/20233
en: 21990/23770
ja: 3882/13006
ko: 0/239
zh-cn: 0/877
zh-tw: 2146/7436
```
Ersatzbilder aus anderer Sprachfassung: Ersatzbilder gesetzt: 7733

Nachher:
```
de: 19331/20233
en: 22076/23770
ja: 4036/13006
ko: 239/239
zh-cn: 829/877
zh-tw: 4100/7436
```

_Lauf: 2026-10-17 23:48 UTC, Stand 146580e_
