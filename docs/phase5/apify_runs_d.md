# Spike Apify, Stufe D: Testläufe

- Verfügbare Proxy-Gruppen im Tarif: ['BUYPROXIES94952', 'GOOGLE_SERP', 'RESIDENTIAL', 'UNBLOCKER']

## eBay.de · epicscrapers (mit Ausschlusswörtern)

- Anbieter: `epicscrapers/ebay-sold-listings-api`
- Eingabe: `{"keywords": ["Glurak 183/165 PSA 10"], "site": "ebay.de", "maxItems": 20, "days": 90}`
- Status: SUCCEEDED Done: saved 18 sold listing(s) for 1 search(es) on ebay.de. See SUMMARY in the key-value store. · Dauer 6 s
- Kosten: 5e-05 $ (Ereignisse: {"apify-actor-start": 1, "apify-default-dataset-item": 0})
- Ergebnisse: 18
- Felder: ["bestOfferAccepted", "bidCount", "buyerProtectionFee", "categoryId", "categoryName", "condition", "conditionDetails", "currency", "displayedPrice", "freeReturns", "hasBestOffer", "imageUrl", "isPromoted", "itemLocation", "listingId", "listingType", "quantitySold", "returnsAccepted", "searchQuery", "searchUrl", "seller", "sellerType", "shippingIsEstimate", "shippingPrice", "shippingText", "site", "soldAt", "soldDateText", "soldPrice", "title", "totalPrice", "url"]
- Sprachen: {'None': 18} · Zustände: {'Gebraucht': 5, 'Neu (Sonstige)': 13}
  - Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch · 25.51 · Gebraucht · Verkauft 18. Okt 2026 · {"username": "wow--5737", "feedbackScore": 513, "feedbackPercent": 100, "isStore": false}
  - Glurak ex 183/165 151 Holo (Deutsch) PSA 10 · 153 · Neu (Sonstige) · Verkauft 18. Okt 2026 · {"username": "7tkqd-84", "feedbackScore": 103, "feedbackPercent": 100, "isStore": false}
  - Pokémon TCG Glurak ex EX 183/165 Deutsch Holo 151 Double Rare KP 330 Phase 2 · 39 · Gebraucht · Verkauft 18. Okt 2026 · {"username": "monsterkarten", "feedbackScore": 44, "feedbackPercent": 100, "isStore": fal…
  - POKEMON KARTEN 151 DEUTSCH | Alle Karten Auswahl - NEAR MINT · 1.29 · Gebraucht · Verkauft 17. Okt 2026 · {"username": "sleeveede", "feedbackScore": 1812, "feedbackPercent": 99.7, "isStore": fals…
  - Pokémon Glurak / Charizard ex Full Art 183/165 Karmesin & Purpur 151 DE NM · 37.99 · Gebraucht · Verkauft 15. Okt 2026 · {"username": "wojciolive", "feedbackScore": 46, "feedbackPercent": 100, "isStore": false}
  - Glurak ex 183/165 151 Holo (Deutsch) PSA 10 · 227 · Neu (Sonstige) · Verkauft 12. Okt 2026 · {"username": "6iv_ditto31", "feedbackScore": 2, "feedbackPercent": 100, "isStore": false}
- Erster Eintrag vollständig: `{"searchQuery": "Glurak 183/165 PSA 10", "searchUrl": null, "site": "ebay.de", "listingId": "407297300047", "title": "Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch", "url": "https://www.ebay.de/itm/407297300047", "imageUrl": "https://i.ebayimg.com/images/g/t-UAAeSw0jlq06vV/s-l225.jpg", "soldPrice": 25.51, "currency": "EUR", "displayedPrice": 25.51, "buyerProtectionFee": null, "shippingPrice": null, "shippingIsEstimate": false, "shippingText": "Keine Angaben zum Versand", "totalPrice": null, "listingType": "auction", "bidCount": 6, "bestOfferAccepted": false, "condition": "Gebraucht", "conditionDetails": null, "categoryId": "183454", "categoryName": "TCG Einzelkarten", "soldAt": "2026-10-18T00:00:00.000Z", "soldDateText": "Verkauft 18. Okt 2026", "seller": {"username": "wow--5737", "feedbackScore": 513, "feedbackPercent": 100, "isStore": false}, "sellerType": null,…`

## eBay.de · scrape.badger

- Anbieter: `scrape.badger/ebay-sold-items-scraper`
- Eingabe: `{"mode": "sold", "query": "Glurak 183/165 PSA 10", "domain": "ebay.de", "max_items": 20}`
- Auswahl `mode`: „sold“ → „None“ (möglich: ["Search Sold & Completed"])
- Auswahl `domain`: „ebay.de“ → „de“ (möglich: ["com", "co.uk", "de"])
- ❌ Start: HTTP 400: {
  "error": {
    "type": "invalid-input",
    "message": "Input is not valid: Field input.mode must be equal to one of the allowed values: \"Search Sold & Completed\""
  }
}

## eBay.de · astronomical_reception (Median, Empfehlung)

- Anbieter: `astronomical_reception/ebay-sold-lite`
- Eingabe: `{"searchQueries": ["Glurak 183/165 PSA 10"], "maxItemsPerQuery": 20, "soldWithinDays": 90, "ebaySite": "ebay.de"}`
- Status: SUCCEEDED  · Dauer 9 s
- Kosten: 0.01 $ (Ereignisse: {"apify-actor-start": 1, "query-completed": 0})
- Ergebnisse: 0

## eBay.de · memo23 (Titel muss Begriffe enthalten)

- Anbieter: `memo23/ebay-search-scraper-ppe`
- Eingabe: `{"searchQueries": ["Glurak 183/165 PSA 10"], "marketplace": "ebay.de", "mode": "sold", "soldWithinDays": 90, "titleMustInclude": ["183/165", "PSA 10"], "maxItems": 20}`
- ❌ Start: HTTP 400: {
  "error": {
    "type": "invalid-input",
    "message": "Input is not valid: Field input.titleMustInclude must be string"
  }
}

## eBay.de · harvestlab (nur verkauft)

- Anbieter: `harvestlab/ebay-scraper`
- Eingabe: `{"searchQuery": "Glurak 183/165 PSA 10", "ebaySite": "ebay.de", "soldOnly": true, "maxItems": 20}`
- Status: SUCCEEDED No sold eBay products were scraped. Completed-sale pages may be blocked by eBay (HTTP 403), the query may have no recent sold results, or filters may be too narrow. Try a residential proxy matched to… · Dauer 21 s
- Kosten: 0.0002 $ (Ereignisse: {"apify-actor-start": 4, "apify-default-dataset-item": 0, "product-scraped": 0, "sold-listing-scraped": 0, "sold-summary-generated": 0, "sold-trend-detected": 0, "ai-analysis-completed": 0})
- Ergebnisse: 0

## Cardmarket · Turtok-ex 151 deutsch NM (englische Seite)

- Anbieter: `phantom_coder/cardmarket-listings-scraper`
- Eingabe: `{"productUrl": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200", "language": "German", "minCondition": "NM", "maxResults": 10}`
- Status: SUCCEEDED Scraped 1 card. · Dauer 72 s
- Kosten: 5e-05 $ (Ereignisse: {"card-listing": 0, "iq-analysis": 0, "apify-actor-start": 1})
- Ergebnisse: 10
- Felder: ["cardName", "condition", "currency", "eurUsdRate", "game", "language", "price", "priceUsd", "productUrl", "quantity", "sellerComment", "sellerName", "setName"]
- Sprachen: {'German': 10} · Zustände: {'NM': 10}
  - Blastoise ex (MEW 200) · 114.99 · NM · German · HomgCards
  - Blastoise ex (MEW 200) · 114.99 · NM · German · TjallingV
  - Blastoise ex (MEW 200) · 117 · NM · German · DJ-Billy
  - Blastoise ex (MEW 200) · 119 · NM · German · KaiserCards
  - Blastoise ex (MEW 200) · 120 · NM · German · Mieskomsich
  - Blastoise ex (MEW 200) · 120 · NM · German · Bragrock
- Erster Eintrag vollständig: `{"cardName": "Blastoise ex (MEW 200)", "setName": "151", "game": "Pokémon", "sellerName": "HomgCards", "condition": "NM", "language": "German", "quantity": 1, "price": 114.99, "currency": "EUR", "priceUsd": 129.18, "sellerComment": "13423", "eurUsdRate": 1.1234, "productUrl": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200?language=3&minCondition=2"}`

## Cardmarket · Turtok-ex 151 alle Sprachen ab NM (englische Seite)

- Anbieter: `phantom_coder/cardmarket-listings-scraper`
- Eingabe: `{"productUrl": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200", "language": "any", "minCondition": "NM", "maxResults": 10}`
- Status: SUCCEEDED Scraped 1 card. · Dauer 120 s
- Kosten: 5e-05 $ (Ereignisse: {"card-listing": 0, "iq-analysis": 0, "apify-actor-start": 1})
- Ergebnisse: 10
- Felder: ["cardName", "condition", "currency", "eurUsdRate", "game", "language", "price", "priceUsd", "productUrl", "quantity", "sellerComment", "sellerName", "setName"]
- Sprachen: {'Italian': 10} · Zustände: {'NM': 10}
  - Blastoise ex (MEW 200) · 98 · NM · Italian · Stefsod26
  - Blastoise ex (MEW 200) · 99.99 · NM · Italian · LaughTaleSR
  - Blastoise ex (MEW 200) · 99.99 · NM · Italian · Corra00
  - Blastoise ex (MEW 200) · 100 · NM · Italian · Bro2storeSRL
  - Blastoise ex (MEW 200) · 100 · NM · Italian · NachNoCap
  - Blastoise ex (MEW 200) · 100 · NM · Italian · giovanni11o
- Erster Eintrag vollständig: `{"cardName": "Blastoise ex (MEW 200)", "setName": "151", "game": "Pokémon", "sellerName": "Stefsod26", "condition": "NM", "language": "Italian", "quantity": 1, "price": 98, "currency": "EUR", "priceUsd": 110.09, "sellerComment": "SIMONE", "eurUsdRate": 1.1234, "productUrl": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200?minCondition=2"}`

## Cardmarket · Glurak M6a per idProduct, englisch, ohne Filter

- Anbieter: `phantom_coder/cardmarket-listings-scraper`
- Eingabe: `{"productUrl": "https://www.cardmarket.com/en/Pokemon/Products?idProduct=907902", "language": "any", "minCondition": "PO", "maxResults": 5}`
- Status: FAILED  · Dauer 3 s
- Kosten: 0 $ (Ereignisse: {"card-listing": 0, "iq-analysis": 0, "apify-actor-start": 1})
- Ergebnisse: 0

**Verbrauch diesen Monat danach: 0.5315452301422808 $ von 5 $**

_Lauf: 2026-10-21 14:40 UTC, Stand e2631da_
