# Spike: offizielle Kartendatenbanken als Bildquelle

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
