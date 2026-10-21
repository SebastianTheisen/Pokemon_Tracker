# Spike Apify, Stufe K: Testläufe

- Verfügbare Proxy-Gruppen im Tarif: ['BUYPROXIES94952', 'GOOGLE_SERP', 'RESIDENTIAL', 'UNBLOCKER']

## Produkt-Details · parsebird

- Anbieter: `parsebird/pricecharting-product-scraper`
- Eingabefelder: ["includeRecentSales", "maxConcurrency", "maxItems", "priceChartingToken", "products", "proxyConfiguration", "requestDelaySecs", "scrapeProductDetails"]
- Eingabe: `{"products": ["https://www.pricecharting.com/game/pokemon-scarlet-&-violet-151/charizard-ex-199", "https://www.pricecharting.com/game/pokemon-japanese-paradigm-trigger/lugia-v-110"], "maxItems": 2, "scrapeProductDetails": true, "includeRecentSales": true}`
- Status: SUCCEEDED Scraped 2/2 products · Dauer 6 s
- Kosten: 5e-05 $ (Ereignisse: {"apify-actor-start": 1, "product-scraped": 0})
- Ergebnisse: 2
- Felder: ["asin", "category", "consoleName", "currency", "epid", "flags", "fullPrices", "genre", "imageUrl", "images", "populationReport", "priceHistory", "prices", "productId", "productName", "recentSales", "releaseDate", "salesVolume", "scrapedAt", "source", "upc", "url"]
- Sprachen: {'None': 2} · Zustände: {'None': 2}
  - 5809582 · {"loose": 305, "cib": 241, "new": 301.25, "graded": 358, "boxOnly": 554.5, "manualOnly": … · September 22, 2023
  - 4334493 · {"loose": 741.17, "cib": null, "new": 448.4, "graded": 562.5, "boxOnly": 675.48, "manualO… · November 11, 2022
- Erster Eintrag vollständig: `{"productId": 5809582, "productName": "Charizard ex #199", "consoleName": "Pokemon Scarlet & Violet 151", "category": "pokemon-cards", "url": "https://www.pricecharting.com/game/pokemon-scarlet-&-violet-151/charizard-ex-199", "releaseDate": "September 22, 2023", "genre": "Pokemon Card", "upc": null, "epid": "17062924371", "asin": null, "imageUrl": "https://storage.googleapis.com/images.pricecharting.com/2z2r3eie25dtigmj/1600.jpg", "images": ["https://storage.googleapis.com/images.pricecharting.com/2z2r3eie25dtigmj/1600.jpg", "https://storage.googleapis.com/images.pricecharting.com/5mb67avd4i4yenin/1600.jpg", "https://storage.googleapis.com/images.pricecharting.com/iw6my5kudqza2bji/1600.jpg", "https://storage.googleapis.com/images.pricecharting.com/nzjmagbxdzi7lsp7/1600.jpg"], "flags": {"isSystem": false, "isCard": true, "isDisc": false, "isComic": false, "isCoin": false, "isProofCoin": false, "isLegoSet": false, "isFunkoPop": false, "isOld": false}, "currency": "USD", "prices": {"loose": 305, "cib": 241, "new": 301.25, "graded": 358, "boxOnly": 554.5, "manualOnly": 1284.99}, "fullPrices": {"Ungraded": 305, "Grade 1": 331.62, "Grade 2": 100, "Grade 3": 111, "Grade 4": 131, "Grade 5": 154, "Grade 6": 193, "Grade 7": 241, "Grade 8": 301.25, "Grade 9": 358, "TAG 10": 1112.5, "ACE 10": 835.46, "SGC 10": 622.38, "CGC 10": 579.25, "PSA 10": 1284.99, "BGS 10": 6000, "BGS 10 Black": 30000, "CGC 10 Pristine": 1812.5, "Grade 9.5": 554.5}, "salesVolume": {"Ungraded": 60, "BGS 10 Black": 1, "PSA 10": 30, "BGS 10": 8, "CGC 10": 30, "SGC 10": 22, "TAG 10": 30, "ACE 10": 23, "Grade 9": 30, "Grade 8": 30, "Grade 7": 30, "Grade 6": 18, "Grade 5": 2, "Grade 4": 1, "Grade 3": 2, "Grade 2": 1, "Grade 1": 3, "CGC 10 Prist.": 30, "Grade 9.5": 30}, "populationReport": {"CGC": {"1": 0, "2": 0, "3": 0, "4": 1, "5": 11, "6": 35, "7": 171, "8": 1022, "9": 1869, "10": 2095}, "PSA": {"1": 21, "2": 9, "3": 27, "4": 70, "5": 175, "6": 886, "7": 3283, "8": 17805, "9": 47519, "10": 27631}}, "recentSales": {"Ungraded": [{"date": "2026-10-20", "title": "Pokemon Charizard ex 199/165 SV Scarlet & Violet 151 SIR Full Art Holo EN 199/165", "price": 309, "source": "ebay", "itemId": "128146938591", "url": "https://www.ebay.com/itm/128146938591"}, {"date": "2026-10-20", "title": "Pokemon 2023 Scarlet & Violet 151 Charizard EX SAR #199/165 199/165", "price": 299.95, "source": "ebay", "itemId": "168790166279", "url": "https://www.ebay.com/itm/168790166279"}, {"date": "2026-10-20", "title": "Pokemon Charizard EX Holo Rare Card 199/165 SV Scarlet & Violet 151 Clean Nm !! 199/165", "price": 320, "source": "ebay", "itemId": "940022137833", "url": "https://www.ebay.com/itm/940022137833"}, {"date": "2026-10-20", "title": "Charizard EX (199) Pokemon Scarlet & Violet 151", "price": 284.5, "source": "ebay", "itemId": "298671912650", "url": "https://www.ebay.com/itm/298671912650"}, {"date": "2026-10-20", "title": "Pokémon Scarlet & Violet 151 Charizard ex #199/165 Special Illustration Rare 199/165", "price": 270, "source": "ebay", "itemId": "137857348718", "url": "https://www.ebay.com/itm/137857348718"}, {"date": "2026-10-20", "title": "Charizard ex - 199/165 #199 Near Mint English", "price": 297.99, "source": "tcgplayer", "itemId": "5m5akEtmi202", "url": "https://partner.tcgplayer.com/c/3029031/1780961/21018"}, {"date": "2026-10-20", "title": "🔥 Charizard ex 199/165 Scarlet & Violet 151 Special Illustration Rare MINT 199/165", "price": 325, "source": "ebay", "itemId": "407302135192", "url": "https://www.ebay.com/itm/407302135192"}, {"date": "2026-10-20", "title": "2023 Pokemon SV 151 Charizard ex Special Illustration Rare #199/165 #SV151", "price": 345, "source": "ebay", "itemId": "800786164747", "url": "https://www.ebay.com/itm/800786164747"}, {"date": "2026-10-20", "title": "2023 Pokemon SV 151 Charizard ex Special Illustration Rare #199/165", "price": 295, "source": "ebay", "itemId": "377570994398", "url": "https://www.ebay.com/itm/377570994398"}, {"date": "2026-10-19", "titl…`

## Produkt-Details · ecomscrape

- Anbieter: `ecomscrape/pricecharting-product-details-page-scraper`
- Eingabefelder: ["max_retries_per_url", "proxy", "urls"]
- Eingabe: `{"urls": ["https://www.pricecharting.com/game/pokemon-scarlet-&-violet-151/charizard-ex-199", "https://www.pricecharting.com/game/pokemon-japanese-paradigm-trigger/lugia-v-110"]}`
- ❌ Start: HTTP 403: {
  "error": {
    "type": "full-permission-actor-not-approved",
    "message": "This Actor requires full access to your account. You must approve its permissions before running it: https://console.apify.com/actors/IvlJmH1VlNm208g1j?approvePermissions=true",
    "data": {
      "approvalUrl": "http…

## Echte Kosten je Lauf (30 s nach dem letzten Lauf)

- Produkt-Details · parsebird: **0.00605 $** {}

**Verbrauch diesen Monat danach: 1.8292458679864527 $ von 8 $**

_Lauf: 2026-10-21 21:32 UTC, Stand 301b589_
