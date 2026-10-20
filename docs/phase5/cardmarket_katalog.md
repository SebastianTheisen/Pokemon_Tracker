# Spike: offizielle Cardmarket-Downloads (Pokémon)

## Produkte (Einzelkarten)

- `https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json` → HTTP 200, 13714709 Bytes, application/json
- Schlüssel oben: ['createdAt', 'products', 'version']
- version: 1
- createdAt: 2026-10-20T14:24:46+0200
- Einträge: 74822; Felder: ['categoryName', 'dateAdded', 'idCategory', 'idExpansion', 'idMetacard', 'idProduct', 'name']
  - Beispiel: `{"idProduct": 273532, "name": "Weedle [Multiply]", "idCategory": 51, "categoryName": "Pokémon Single", "idExpansion": 1585, "idMetacard": 340471, "dateAdded": "0000-00-00 00:00:00"}`
  - Beispiel: `{"idProduct": 273533, "name": "Kakuna [Bug Bite | Primal Clash]", "idCategory": 51, "categoryName": "Pokémon Single", "idExpansion": 1585, "idMetacard": 340472, "dateAdded": "0000-00-00 00:00:00"}`
  - Beispiel: `{"idProduct": 273534, "name": "Beedrill [Allergic Shock | Twineedle]", "idCategory": 51, "categoryName": "Pokémon Single", "idExpansion": 1585, "idMetacard": 340473, "dateAdded": "0000-00-00 00:00:00"}`
- Produkt 908315: `{"idProduct": 908315, "name": "Charizard [Energy Burn | Fire Spin]", "idCategory": 51, "categoryName": "Pokémon Single", "idExpansion": 6603, "idMetacard": 211560, "dateAdded": "2026-09-11 10:28:18"}`

## Produkte (versiegelt)

- `https://downloads.s3.cardmarket.com/productCatalog/productList/products_nonsingles_6.json` → HTTP 200, 951389 Bytes, application/json
- Schlüssel oben: ['createdAt', 'products', 'version']
- version: 1
- createdAt: 2026-10-20T14:24:49+0200
- Einträge: 5085; Felder: ['categoryName', 'dateAdded', 'idCategory', 'idExpansion', 'idMetacard', 'idProduct', 'name']
  - Beispiel: `{"idProduct": 271439, "name": "Phantom Forces Booster", "idCategory": 52, "categoryName": "Pokémon Booster", "idExpansion": 1521, "idMetacard": 0, "dateAdded": "2007-01-01 00:00:00"}`
  - Beispiel: `{"idProduct": 271440, "name": "Phantom Forces Booster Box", "idCategory": 53, "categoryName": "Pokémon Display", "idExpansion": 1521, "idMetacard": 0, "dateAdded": "2007-01-01 00:00:00"}`
  - Beispiel: `{"idProduct": 271823, "name": "Base Set Booster", "idCategory": 52, "categoryName": "Pokémon Booster", "idExpansion": 1523, "idMetacard": 0, "dateAdded": "2007-01-01 00:00:00"}`
- Produkt 908315: `nicht gefunden`

## Preisführer

- `https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json` → HTTP 200, 15683764 Bytes, application/json
- Schlüssel oben: ['createdAt', 'priceGuides', 'version']
- version: 1
- createdAt: 2026-10-20T02:44:49+0200
- Einträge: 79804; Felder: ['avg', 'avg-holo', 'avg1', 'avg1-holo', 'avg30', 'avg30-holo', 'avg7', 'avg7-holo', 'idCategory', 'idProduct', 'low', 'low-holo', 'trend', 'trend-holo']
  - Beispiel: `{"idProduct": 271439, "idCategory": 52, "avg": 149, "low": 150, "trend": 279.1, "avg1": null, "avg7": null, "avg30": null, "avg-holo": null, "low-holo": null, "trend-holo": 3.93, "avg1-holo": null, "avg7-holo": null, "avg30-holo": null}`
  - Beispiel: `{"idProduct": 271440, "idCategory": 53, "avg": 2103, "low": 100000, "trend": 2239.24, "avg1": null, "avg7": null, "avg30": null, "avg-holo": null, "low-holo": null, "trend-holo": 178.28, "avg1-holo": null, "avg7-holo": null, "avg30-holo": null}`
  - Beispiel: `{"idProduct": 271823, "idCategory": 52, "avg": 695.97, "low": 320, "trend": 695.86, "avg1": null, "avg7": null, "avg30": null, "avg-holo": null, "low-holo": null, "trend-holo": 90.03, "avg1-holo": null, "avg7-holo": null, "avg30-holo": null}`
- Produkt 908315: `{"idProduct": 908315, "idCategory": 51, "avg": 98.24, "low": 70, "trend": 66.34, "avg1": 71.99, "avg7": 76.19, "avg30": 85.72, "avg-holo": null, "low-holo": null, "trend-holo": 0, "avg1-holo": null, "avg7-holo": null, "avg30-holo": null}`

## Suche „137“ in Produkten mit „30“ oder „M6a“ im Namen


_Lauf: 2026-10-20 21:22 UTC, Stand 77480db_
