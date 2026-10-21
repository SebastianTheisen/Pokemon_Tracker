# Spike Apify: Store-Suche Cardmarket und eBay

- Treffer gesamt: 398, davon zu Cardmarket/eBay: 120

## Cardmarket (19)

| Dienst | Bewertung | Nutzer 30 T. / ges. | Preis | geändert |
|---|---|---|---|---|
| `phantom_coder/cardmarket-listings-scraper` | ✅ Sprache ✅ Zustand ✅ Angebote 🃏 Pokémon | 19 / 83 | je Ereignis: card-listing=0.005, iq-analysis=0.07, apify-ac… |  |
| `lowlanddata/cardmarket-deal-finder` | ✅ Sprache ✅ Zustand ✅ Angebote 🃏 Pokémon | 6 / 15 | je Ereignis: apify-default-dataset-item=0.01, apify-actor-s… |  |
| `crawloop/cardmarket-listings-scraper` | ✅ Sprache ✅ Zustand ✅ Angebote 🃏 Pokémon | 3 / 23 | je Ereignis: apify-actor-start=5e-05, listing=0.00319 |  |
| `jdepablos/pokemon-card-price-checker` | ✅ Sprache ✅ Angebote 🃏 Pokémon | 1 / 10 | je Ereignis: apify-actor-start=0.005, apify-default-dataset… |  |
| `parselab/pokemon-tcg-cards-scraper` | ✅ Sprache 🃏 Pokémon | 2 / 3 | je Ereignis: apify-actor-start=0.001, result-item=0.018 |  |
| `unfenced-group/tcg-card-price-api` | ✅ Zustand 🃏 Pokémon | 1 / 2 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `scrap_them_all/cardmarket-onepiece-trend-scraper` | ✅ Sprache | 3 / 13 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `unfenced-group/cardmarket-scraper` | ✅ Angebote 🃏 Pokémon | 3 / 10 | je Ereignis: apify-actor-start=0.001, catalogue-row=0.00019… |  |
| `scrap_them_all/cardmarket-riftbound-trend-scraper` | ✅ Sprache | 2 / 7 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `scrap_them_all/cardmarket-pokemon-trend-scraper` | ✅ Sprache | 1 / 33 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `scrap_them_all/cardmarket-lorcana-trend-scraper` | ✅ Sprache | 1 / 3 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `scrap_them_all/cardmarket-magic-trend-scraper` | ✅ Sprache | 1 / 3 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `scrap_them_all/cardmarket-yugioh-trend-scraper` | ✅ Sprache | 1 / 2 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `codingfrontend/cardmarket-trend-scraper` | ✅ Angebote 🃏 Pokémon | 1 / 2 | je Ereignis: apify-default-dataset-item=0.00399, apify-acto… |  |
| `lowlanddata/tcg-price-movers` | ✅ Angebote 🃏 Pokémon | 1 / 1 | je Ereignis: spike-alert=0.0199, price-mover=0.00499, apify… |  |
| `lowlanddata/cardmarket-price-guide` | 🃏 Pokémon | 7 / 20 | je Ereignis: apify-default-dataset-item=0.001, apify-actor-… |  |
| `lulzasaur/cardmarket-scraper` | 🃏 Pokémon | 5 / 25 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `kempt_horizon_yzk/pokemon-tcg-price-monitor` | 🃏 Pokémon | 1 / 2 | je Ereignis: apify-actor-start=0.001, card=0.002, alert=0.01 |  |
| `ahmed_jasarevic/cardmarket-scraper` | 🃏 Pokémon | 1 / 2 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |

### Details der besten 12

- `phantom_coder/cardmarket-listings-scraper` – Cardmarket Listings Scraper
  - Scrape all seller listings from any Cardmarket card page — condition, language, quantity, price in EUR/USD. Optional Fair Value Analysis for Scarlet & Violet and Mega Evolution sets adds AI pricing, PSA data, gem rate, and deal score.
  - Eingabefelder: productUrl, productUrls, minCondition, language, minPrice, maxPrice, sellerCountry, maxResults, enableFairValue, foil, isSigned, isAltered, isFirstEd, isPlayset, sellerType
- `lowlanddata/cardmarket-deal-finder` – Cardmarket Listings Scraper - Live Offers, Stock & Prices
  - Cardmarket listings scraper and deal finder in one: every live offer of the cards you search (price, condition, language, ship-from country), or only offers 25%+ under the official trend price - condition- and language-aware. Pokémon, Magic, Yu-Gi-Oh!, Lorcan…
  - Eingabefelder: game, searchQuery, productType, minDiscountPct, minCondition, languages, priceMinEur, priceMaxEur, maxProducts, maxItems, proxyConfiguration, reportFailures
- `crawloop/cardmarket-listings-scraper` – Cardmarket Listings Scraper — Offers, Shops & Prices
  - Scrape Cardmarket listings by product URL, seller shop, or keyword — a Cardmarket API alternative for EU TCG shops. Export seller, condition, language, quantity, and EUR price as JSON.
  - Eingabefelder: searchKeywords, sellerUsernames, shopQuery, startUrls, game, locale, minCondition, language, sellerCountry, sellerType, sort, minPrice, maxPrice, isFoil, isReverseHolo, isSigned, isAltered, isFirstEd, isPlayset, maxItems, maxPages, monitorMode, monitorStoreName, resetMonitorState, proxyConfiguration
- `jdepablos/pokemon-card-price-checker` – Pokemon Card Price Checker: TCGplayer & Cardmarket Prices
  - What is your Pokemon card worth? Current market prices from TCGplayer (USD) and Cardmarket (EUR): market, low, mid and high, plus 7 and 30 day averages. Finds the exact card and set from a free-text query. Raw cards only, graded (PSA) not covered. Built for c…
  - Eingabefelder: query, items, language, justTcgApiKey, monitorMode, monitorEmail
- `parselab/pokemon-tcg-cards-scraper` – Pokemon TCG Card and Price Scraper
  - Search Pokemon cards by name, set, rarity, type, illustrator, HP or legality and get TCGplayer prices in USD plus Cardmarket prices in EUR with 7 and 30 day trends. Look up a card list to value a collection. Includes attacks, abilities, images and 7 languages…
  - Eingabefelder: maxItems, mode, language, names, cardNames, sets, series, rarities, types, categories, stages, illustrators, regulationMarks, minHp, maxHp, standardLegalOnly, minPriceUsd, maxPriceUsd, sortBy
- `unfenced-group/tcg-card-price-api` – TCG Card Price API — Cardmarket and TCGplayer
  - Price any trading card on Cardmarket (EUR) and TCGplayer (USD) in one call: every printing, TCGplayer market price, recent sales and 30-day trend, the matched Cardmarket trend and averages, and the EU vs US price gap. 17 games. HTTP API or batch.
  - Eingabefelder: game, card, set, number, maxResults, includeSales, includeTrend
- `scrap_them_all/cardmarket-onepiece-trend-scraper` – Cardmarket One Piece Card Game Trend Scraper
  - Track One Piece Card Game prices on Cardmarket — Europe's largest trading-card marketplace. Scrape Weekly Top Cards and Best Bargains. Returns ranked cards with stable productId, expansion, current EUR price, thumbnail and product URL. Built for arbitrage, pr…
  - Eingabefelder: mode, language, maxResults, proxyConfiguration, debugSaveHtml
- `unfenced-group/cardmarket-scraper` – Cardmarket Scraper
  - Daily EU trading card market prices from Cardmarket for 20 games. Trend price, lowest listing, 1/7/30-day averages and foil variants for both single cards and sealed product, with real set names and price movement since your last run.
  - Eingabefelder: game, searchQuery, productType, expansionNames, priceMinEur, priceMaxEur, onlyPriced, includeUsPrices, sortBy, maxResults
- `scrap_them_all/cardmarket-riftbound-trend-scraper` – Cardmarket Riftbound (League of Legends TCG) Trend Scraper
  - Track Riftbound (Riot Games' League of Legends TCG) prices on Cardmarket — Europe's largest trading-card marketplace. Scrape Weekly Top Cards and Best Bargains. Returns ranked cards with stable productId, expansion, current EUR price, thumbnail and product UR…
  - Eingabefelder: mode, language, maxResults, proxyConfiguration, debugSaveHtml
- `scrap_them_all/cardmarket-pokemon-trend-scraper` – Cardmarket Pokémon Trend Scraper
  - Scrape Cardmarket Pokémon Weekly Top Cards and Best Bargains. Get card name, expansion, current price, price change, rarity and product URL.
  - Eingabefelder: mode, language, maxResults, proxyConfiguration, debugSaveHtml
- `scrap_them_all/cardmarket-lorcana-trend-scraper` – Cardmarket Disney Lorcana Trend Scraper
  - Track Disney Lorcana prices on Cardmarket — Europe's largest trading-card marketplace. Scrape Weekly Top Cards and Best Bargains. Returns ranked cards with stable productId, expansion, current EUR price, thumbnail and product URL. Built for arbitrage, price a…
  - Eingabefelder: mode, language, maxResults, proxyConfiguration, debugSaveHtml
- `scrap_them_all/cardmarket-magic-trend-scraper` – Cardmarket Magic: The Gathering Trend Scraper
  - Track Magic: The Gathering prices on Cardmarket — Europe's largest trading-card marketplace. Scrape Weekly Top Cards and Best Bargains. Returns ranked cards with stable productId, expansion, current EUR price, thumbnail and product URL. Built for arbitrage, p…
  - Eingabefelder: mode, language, maxResults, proxyConfiguration, debugSaveHtml

## eBay (101)

| Dienst | Bewertung | Nutzer 30 T. / ges. | Preis | geändert |
|---|---|---|---|---|
| `astronomical_reception/ebay-sold-lite` | ✅ ebay.de ✅ verkauft 🃏 Karten-Bezug | 34 / 265 | je Ereignis: apify-actor-start=0.01, query-completed=0.07 |  |
| `harvestlab/ebay-scraper` | ✅ ebay.de ✅ verkauft 🃏 Karten-Bezug | 22 / 226 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `epicscrapers/ebay-sold-listings-api` | ✅ ebay.de ✅ verkauft 🃏 Karten-Bezug | 16 / 43 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `scrape.badger/ebay-sold-items-scraper` | ✅ ebay.de ✅ verkauft 🃏 Karten-Bezug | 9 / 11 | je Ereignis: standard-call=0.002 |  |
| `abotapi/ebay-com-scraper` | ✅ ebay.de ✅ verkauft 🃏 Karten-Bezug | 5 / 8 | je Ereignis: apify-default-dataset-item=0.0018, detail-enri… |  |
| `scrapesage/ebay-scraper` | ✅ ebay.de ✅ verkauft 🃏 Karten-Bezug | 4 / 32 | je Ereignis: item=0.0015, itemDetail=0.003, sellerLead=0.00… |  |
| `xtracto/ebay-sold-comps-scraper` | ✅ ebay.de ✅ verkauft 🃏 Karten-Bezug | 2 / 48 | je Ereignis: apify-actor-start=0.005, apify-default-dataset… |  |
| `axery/ebay-sold-comps-scraper` | ✅ ebay.de ✅ verkauft 🃏 Karten-Bezug | 2 / 3 | je Ereignis: apify-default-dataset-item=0.002, apify-actor-… |  |
| `caffein.dev/ebay-sold-listings` | ✅ ebay.de ✅ verkauft | 880 / 4125 | je Ereignis: apify-default-dataset-item=0.004, apify-actor-… |  |
| `memo23/ebay-search-scraper-ppe` | ✅ ebay.de ✅ verkauft | 283 / 754 | je Ereignis: detail-item=0.005, fast-item=0.003, sold-summa… |  |
| `automation-lab/ebay-scraper` | ✅ ebay.de ✅ verkauft | 177 / 1078 | je Ereignis: start=0.001, product=0.00345 |  |
| `delicious_zebu/ebay-product-listing-scraper` | ✅ ebay.de ✅ verkauft | 120 / 1068 | je Ereignis: apify-default-dataset-item=0.003, apify-actor-… |  |
| `parseforge/ebay-scraper` | ✅ ebay.de ✅ verkauft | 51 / 348 | je Ereignis: result-item=0.005, apify-actor-start=0.065 |  |
| `memo23/apify-ebay-search-cheerio` | ✅ ebay.de ✅ verkauft | 36 / 327 | je Ereignis: detail-item=0.005, fast-item=0.003, sold-summa… |  |
| `khadinakbar/ebay-all-in-one-scraper` | ✅ ebay.de ✅ verkauft | 30 / 334 | je Ereignis: actor-start=5e-05, result=0.003, detailed-resu… |  |
| `kestrel/ebay-search-scraper` | ✅ ebay.de ✅ verkauft | 19 / 28 | je Ereignis: item=0.003 |  |
| `parsebird/ebay-sold-listings-scraper` | ✅ ebay.de ✅ verkauft | 12 / 67 | je Ereignis: apify-actor-start=5e-05, listing-scraped=0.0034 |  |
| `sync-network/ebay-sold-listings-scraper` | ✅ ebay.de ✅ verkauft | 10 / 149 | je Ereignis: apify-default-dataset-item=0.002, apify-actor-… |  |
| `crawloop/ebay-sold-listings-scraper` | ✅ ebay.de ✅ verkauft | 10 / 76 | je Ereignis: apify-actor-start=5e-05, sold-listing=0.004, m… |  |
| `marielise.dev/ebay-sold-listings-intelligence` | ✅ ebay.de ✅ verkauft | 9 / 370 | je Ereignis: search-query=0.15, sold-comp=0.005 |  |
| `datascrapers/ebay-scraper` | ✅ ebay.de ✅ verkauft | 9 / 18 | je Ereignis: apify-actor-start=5e-05, dataset-item=0.001, p… |  |
| `apt_marble/ebay-sold-items-scraper` | ✅ ebay.de ✅ verkauft | 8 / 39 | je Ereignis: apify-default-dataset-item=0.0012 |  |
| `trakk/ebay-seller-intelligence` | ✅ ebay.de ✅ verkauft | 8 / 65 | je Ereignis: listing_item=0.0025, seller_profile=0.003, sel… |  |
| `damilo/ebay-search-apify` | ✅ ebay.de ✅ verkauft | 7 / 124 | je Ereignis: apify-default-dataset-item=0.0035 |  |
| `blackfalcondata/ebay-scraper` | ✅ ebay.de ✅ verkauft | 6 / 18 | je Ereignis: apify-actor-start=0.02, detail-item=0.004, fas… |  |
| `epicscrapers/ebay-motors-scraper` | ✅ ebay.de ✅ verkauft | 5 / 6 | je Ereignis: listing=0.002, listing-with-details=0.003 |  |
| `apt_marble/ebay-product-scraper` | ✅ ebay.de ✅ verkauft | 5 / 9 | je Ereignis: apify-default-dataset-item=0.002 |  |
| `midwest_united/ebay-sold-comps` | ✅ ebay.de ✅ verkauft | 4 / 36 | je Ereignis: pricing-report-generated=0.1, comp-record-retu… |  |
| `santamaria-automations/ebay-sold-scraper` | ✅ ebay.de ✅ verkauft | 4 / 13 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `unfenced-group/ebay-scraper` | ✅ ebay.de ✅ verkauft | 4 / 10 | je Ereignis: apify-default-dataset-item=0.00099 |  |
| `charitable_trousseau/ebay-search-scraper` | ✅ ebay.de ✅ verkauft | 4 / 4 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `burbn/ebay-search-scraper` | ✅ ebay.de ✅ verkauft | 4 / 28 | je Ereignis: apify-actor-start=0.02, apify-default-dataset-… |  |
| `convertfleetdotonline/ebay-sold-listings-search` | ✅ ebay.de ✅ verkauft | 3 / 8 | kostenlos (nur Plattform) |  |
| `brilliant_gum/ebay-scraper` | ✅ ebay.de ✅ verkauft | 3 / 17 | je Ereignis: apify-actor-start=0.01, apify-default-dataset-… |  |
| `nice_dev/ebay-listings-scraper` | ✅ ebay.de ✅ verkauft | 3 / 4 | je Ereignis: apify-actor-start=0.019, result=0.00063, resul… |  |
| `santamaria-automations/ebay-scraper` | ✅ ebay.de ✅ verkauft | 3 / 9 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `scrapeworks/ebay-sold-price-analytics` | ✅ ebay.de ✅ verkauft | 2 / 17 | je Ereignis: apify-actor-start=5e-05, result=0.004 |  |
| `sourabhbgp/ebay-scraper` | ✅ ebay.de ✅ verkauft | 2 / 5 | je Ereignis: apify-actor-start=5e-05, result=0.004 |  |
| `valev-lab/ebay-search-scraper` | ✅ ebay.de ✅ verkauft | 2 / 11 | je Ereignis: product-scraped=0.003, apify-actor-start=0.001 |  |
| `henrycrawl/ebay-seller-scraper` | ✅ ebay.de ✅ verkauft | 2 / 3 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `renzomacar/ebay-products` | ✅ ebay.de ✅ verkauft | 2 / 8 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `scrapers_lat/ebay-scraper` | ✅ ebay.de ✅ verkauft | 2 / 3 | je Ereignis: result=0.008, details=0.009231, ai_description… |  |
| `epicscrapers/ebay-keyword-tool` | ✅ ebay.de ✅ verkauft | 2 / 3 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `superslowsloth/ebay-listings` | ✅ ebay.de ✅ verkauft | 2 / 3 | je Ereignis: actor-start=0.002, listing-scraped=0.0014 |  |
| `burbn/ebay-products-by-category` | ✅ ebay.de ✅ verkauft | 2 / 3 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `curious_coder/ebay-search-scraper` | ✅ ebay.de ✅ verkauft | 2 / 11 | je Ereignis: apify-actor-start=0.005, apify-default-dataset… |  |
| `bgfc97/ebay-scraper` | ✅ ebay.de ✅ verkauft | 2 / 3 | je Ereignis: item-scraped=0.001 |  |
| `tortuga/ebay-scraper` | ✅ ebay.de ✅ verkauft | 2 / 3 | je Ereignis: result=0.002, detail=0.0015 |  |
| `scrapeworks/ebay-search-scraper` | ✅ ebay.de | 50 / 90 | je Ereignis: result=0.0015, apify-actor-start=5e-05 |  |
| `apt_marble/ebay-search-scraper` | ✅ ebay.de | 30 / 38 | je Ereignis: apify-default-dataset-item=0.0007, full-item-d… |  |
| `delicious_zebu/ebay-product-details-scraper` | ✅ ebay.de | 18 / 208 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `jungle_synthesizer/goldin-auctions-marketplace-scraper` | ❌ kein ebay.de ✅ verkauft 🃏 Karten-Bezug | 16 / 60 | je Ereignis: orbtop-actor-start=0.0001, data-record=0.0015 |  |
| `shahidirfan/eBay-Product-Listing-Scraper` | ✅ ebay.de | 6 / 8 | je Ereignis: apify-actor-start=0.0005, apify-default-datase… |  |
| `programmx/ebay-business-leads` | ✅ ebay.de | 5 / 10 | je Ereignis: apify-actor-start=5e-05, unique-business-selle… |  |
| `burbn/ebay-product-details-scraper` | ✅ ebay.de | 4 / 7 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `sian.agency/ebay-data-scraper` | ✅ ebay.de | 4 / 33 | je Ereignis: apify-actor-start=0.05, search-result=0.009, c… |  |
| `tagadanar/ebay-sold-comps` | ❌ kein ebay.de ✅ verkauft 🃏 Karten-Bezug | 3 / 30 | je Ereignis: sold-listing=0.0025, actor-start=0.001 |  |
| `benthepythondev/ebay-scraper` | ✅ ebay.de | 3 / 11 | je Ereignis: apify-default-dataset-item=0.003, apify-actor-… |  |
| `gio21/ebay-scraper` | ✅ ebay.de | 3 / 4 | je Ereignis: listing-scraped=0.0001 |  |
| `ponderable_hydrometer/ebay-parts` | ✅ ebay.de | 3 / 3 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `lulzasaur/ebay-sold-scraper` | ❌ kein ebay.de ✅ verkauft 🃏 Karten-Bezug | 2 / 16 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `glowing_glove/ebay-sold-listings-price-intelligence` | ❌ kein ebay.de ✅ verkauft 🃏 Karten-Bezug | 2 / 3 | je Ereignis: analyzedSoldComps=0.02 |  |
| `datablow/ebay-product-scraper` | ✅ ebay.de | 2 / 3 | je Ereignis: apify-actor-start=0.01, apify-default-dataset-… |  |
| `sovanza.inc/advanced-ebay-scraper-extract-product-data-prices-reviews` | ✅ ebay.de | 2 / 31 | je Ereignis: apify-actor-start=0.01, apify-default-dataset-… |  |
| `joseolmedosotoaguirre/ebay-listings-scraper` | ✅ ebay.de | 2 / 3 | je Ereignis: apify-actor-start=0.0001, apify-default-datase… |  |
| `lentic_clockss/ecommerce-scraper` | ✅ ebay.de | 2 / 3 | je Ereignis: apify-actor-start=0.003, apify-default-dataset… |  |
| `w3crawler/ebay-motors-scraper` | ✅ ebay.de | 2 / 2 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `piotrv1001/ebay-seller-feedback-scraper` | ✅ ebay.de | 2 / 4 | je Ereignis: apify-actor-start=5e-05, feedback=0.001 |  |
| `blackfalcondata/ebay-sold-listings-scraper` | ❌ kein ebay.de ✅ verkauft | 26 / 69 | je Ereignis: apify-actor-start=0.01, fast-item=0.0024, deta… |  |
| `cirkit/ebay-product-scraper` | ❌ kein ebay.de ✅ verkauft | 17 / 104 | kostenlos (nur Plattform) |  |
| `e-commerce/store-ebay` | ❌ kein ebay.de ✅ verkauft | 15 / 195 | je Ereignis: start=0.0001, result=0.005 |  |
| `ivanvs/ebay-scraper-pay-per-result` | ❌ kein ebay.de ✅ verkauft | 12 / 403 | je Ereignis: apify-default-dataset-item=0.004 |  |
| `piotrv1001/ebay-listings-scraper` | ❌ kein ebay.de ✅ verkauft | 11 / 149 | je Ereignis: product-listing=0.004, item-detail=0.007 |  |
| `bovi/ebay-scraper` | ❌ kein ebay.de ✅ verkauft | 6 / 12 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `tnodes/ebay-sold-scraper` | ❌ kein ebay.de ✅ verkauft | 5 / 45 | je Ereignis: apify-actor-start=1e-05, apify-default-dataset… |  |
| `ahmed_jasarevic/ebay-scraper` | ❌ kein ebay.de ✅ verkauft | 4 / 37 | je Ereignis: apify-default-dataset-item=0.0025, apify-actor… |  |
| `night111/ebay-sold-comps-valuator` | ❌ kein ebay.de ✅ verkauft | 2 / 3 | je Ereignis: apify-actor-start=4e-05, actionable-insight=0.… |  |
| `w3crawler/ebay-sold-comps-scraper` | ❌ kein ebay.de ✅ verkauft | 2 / 3 | je Ereignis: apify-actor-start=0.001, apify-default-dataset… |  |
| `devcake/ebay-listings-scraper` | ❌ kein ebay.de ✅ verkauft | 2 / 6 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `crawloop/ebay-live-shows-scraper` | ❌ kein ebay.de ✅ verkauft | 2 / 6 | je Ereignis: apify-actor-start=5e-05, live-show=0.00119, li… |  |
| `santamaria-automations/kleinanzeigen-de-scraper` | ❔ ebay.de nur in Beschreibung | 2 / 30 | je Ereignis: apify-actor-start=5e-05, directory-serp-result… |  |
| `gio21/kleinanzeigen-scraper` | ❔ ebay.de nur in Beschreibung | 2 / 14 | je Ereignis: listing-scraped=0.003 |  |
| `dtrungtin/ebay-items-scraper` | ❌ kein ebay.de | 40 / 2107 | je Ereignis: apify-actor-start=0.08, apify-default-dataset-… |  |
| `delicious_zebu/ebay-store-scraper` | ❌ kein ebay.de | 11 / 251 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `dtrungtin/ebay-search-scraper` | ❌ kein ebay.de | 6 / 143 | je Ereignis: apify-default-dataset-item=0.018, apify-actor-… |  |
| `sian.agency/alibaba-1688-wholesale-scraper` | ❌ kein ebay.de | 6 / 88 | je Ereignis: apify-actor-start=0.14, search-item-result=0.0… |  |
| `m3web/german-price-comparison-actor` | ❌ kein ebay.de | 5 / 11 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `3x1t/ebay-scraper` | ❌ kein ebay.de | 4 / 75 | kostenlos (nur Plattform) |  |
| `xtracto/ebay-product-scraper` | ❌ kein ebay.de | 3 / 9 | je Ereignis: apify-actor-start=0.005, apify-default-dataset… |  |
| `getdataforme/Ebay-Product-Scraper` | ❌ kein ebay.de | 3 / 37 | je Ereignis: apify-actor-start=0.005, apify-default-dataset… |  |
| `wilcode/ebay-scraper` | ❌ kein ebay.de | 2 / 6 | je Ereignis: product-scraped=0.004, apify-default-dataset-i… |  |
| `vulnv/ebay-product-scraper` | ❌ kein ebay.de | 2 / 31 | je Ereignis: apify-actor-start=0.005, apify-default-dataset… |  |
| `scrapeai/ebay-scraper` | ❌ kein ebay.de | 2 / 27 | je Ereignis: apify-default-dataset-item=0.00249, apify-acto… |  |
| `maximedupre/ebay-seller-scraper` | ❌ kein ebay.de | 2 / 4 | je Ereignis: seller-profile=0.00445, feedback-review=0.00045 |  |
| `anyxsolutions/kleinanzeigen-scraper` | ❌ kein ebay.de | 2 / 4 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `saswave/ebay-review-scraper` | ❌ kein ebay.de | 2 / 3 | je Ereignis: apify-default-dataset-item=0.001, apify-actor-… |  |
| `enezli/shopify-ebay-product-research` | ❌ kein ebay.de | 2 / 3 | je Ereignis: actor-start=0.0001, item-scraped=0.005 |  |
| `thenetaji/ebay-category-products-scraper` | ❌ kein ebay.de | 2 / 3 | je Ereignis: apify-actor-start=5e-05, apify-default-dataset… |  |
| `oneary/ebay-pricing-scraper` | ❌ kein ebay.de | 2 / 3 | je Ereignis: apify-default-dataset-item=0.0042, apify-actor… |  |
| `neuralverge/neuralverge-ebay-item-search` | ❌ kein ebay.de | 2 / 3 | je Ereignis: apify-default-dataset-item=0.002 |  |
| `antishock/ebay-scraper` | ❌ kein ebay.de | 2 / 3 | je Ereignis: apify-actor-start=0.002, apify-default-dataset… |  |

### Details der besten 12

- `astronomical_reception/ebay-sold-lite` – eBay Sold Listing/Prices Scraper — Cheap, Fast, & Lightweight
  - Get real eBay sold prices in under 10 seconds at a low cost. Returns up to 200 recent sales with avg, median, and recommended price. The fastest and cheapest way to get sold comps.
  - Eingabefelder: searchQueries, maxItemsPerQuery, soldWithinDays, sort, condition, listingType, freeShippingOnly, minPrice, maxPrice, ebaySite
- `harvestlab/ebay-scraper` – eBay Product Scraper - Prices, Auctions & Buy It Now
  - Scrape active eBay listings across 13 markets: prices, shipping, sellers, auction bids, Buy It Now offers, fallback listing recovery, and diagnostics.
  - Eingabefelder: searchQuery, query, q, search, keyword, searchTerm, productUrls, urls, links, ebayDomain, domain, ebaySite, listingType, sortBy, minPrice, maxPrice, itemCondition, maxProducts, fetchDetails, soldOnly, soldDateLookback, maxItems, enableAiAnalysis, llmProvider, llmModel, openrouterApiKey, anthropicApiKey, googleApiKey, openaiApiKey, ollamaBaseUrl, proxyConfiguration
- `epicscrapers/ebay-sold-listings-api` – eBay Sold Listings API
  - Extract recent sold eBay listings with prices, shipping costs, sale dates, conditions, sellers, and URLs. Search eight marketplaces with date, condition, and price filters, then export structured data or access it through the Apify API.
  - Eingabefelder: startUrls, keywords, site, maxItems, days, onlyNewSales, excludeKeywords, sellerType, skipOtherModels, condition, listingType, categoryId, minPrice, maxPrice, includeSummary
- `scrape.badger/ebay-sold-items-scraper` – eBay Sold Items Scraper — Completed Listings & Prices
  - Scrape eBay sold and completed listings — the real transaction prices behind any keyword. Filter by category, condition and price range across every eBay domain. For resale pricing, market research and comps.
  - Eingabefelder: mode, query, domain, category_id, page, per_page, sort_by, condition, min_price, max_price, max_items
- `abotapi/ebay-com-scraper` – eBay Scraper - Products, Sellers, Prices & Monitoring
  - Scrape eBay by keyword, category, seller or pasted link across 16 country storefronts. Returns id, title, condition, price, buying format, delivery, returns, seller feedback and more, with optional item specifics and full descriptions. Incremental mode tracks…
  - Eingabefelder: mode, queries, sellerUsernames, marketplace, categoryId, condition, buyingFormat, minPrice, maxPrice, freeShippingOnly, freeReturnsOnly, returnsAcceptedOnly, itemLocation, sortBy, sortOrder, keywords, ebaySite, subcategoryId, itemCondition, conditionId, aspectFilter, postalCode, urls, minSellerFeedbackPercent, fetchDetails, maxReviewsPerProduct, maxItems, maxPages, proxy, resumeFromRunId, increme…
- `scrapesage/ebay-scraper` – Listing Scraper for eBay - Prices, Item Details & Seller Leads
  - Scrape active eBay listings by keyword, link or seller on 10 marketplaces: price, condition, shipping, bids, units sold, seller feedback. Add item details (specifics, GTIN, photos, returns) and seller leads with EU/UK business contacts. Monitor mode. Independ…
  - Eingabefelder: mode, searchQueries, startUrls, sellerNames, marketplace, categoryId, condition, listingType, priceMin, priceMax, freeShippingOnly, sort, enrichItemDetails, includeDescription, emitSellerLeads, maxItems, maxSellers, deduplicateResults, monitorMode, monitorKey, maxConcurrency, proxyConfiguration, urlsFromFile
- `xtracto/ebay-sold-comps-scraper` – eBay Sold Comps Scraper
  - Pull eBay sold/completed listings for any keyword and get a reseller-grade price band (min, median, p90) per query.
  - Eingabefelder: queries, domain, maxPagesPerQuery, maxConcurrency, maxRequestRetries, proxyConfiguration
- `axery/ebay-sold-comps-scraper` – eBay Sold Comps & Realized Price Scraper
  - Scrape eBay sold and completed listings to find historical market values, realized sale prices, shipping fees, total bids, seller ratings & sold dates.
  - Eingabefelder: query, maxItems, country, condition, proxyConfiguration
- `caffein.dev/ebay-sold-listings` – eBay Sold Listings Search
  - Get confirmed eBay sold prices. Search by keyword across 8 marketplaces, filter by date range, and export clean structured data for comps, resale pricing, and market research.
  - Eingabefelder: keywords, keyword, search, categoryId, subcategoryId, ebaySite, daysToScrape, count, sortOrder, minPrice, maxPrice, buyingFormat, itemLocation, itemCondition, conditionId, aspectFilter, includeCompletedListings
- `memo23/ebay-search-scraper-ppe` – eBay Scraper — Active & Sold Listings, Prices & Analytics
  - Scrape eBay active & sold listings across 17 marketplaces. Search by keyword or URL — get prices, sold price & date, sell-through rate, condition, shipping, item specifics, identifiers (UPC/MPN), images & seller details. Fast/full-detail modes + change monito…
  - Eingabefelder: startUrls, detailedItems, includeDescription, includeLegacyFields, categoryPageMode, searchQuery, searchQueries, marketplace, mode, soldWithinDays, includeSummary, titleMustMatchQuery, titleMustInclude, condition, minPrice, maxPrice, sortBy, listingType, freeShipping, returnsAccepted, seller, category, motorsCategory, minYear, maxYear, monitoringMode, enablePriceMonitoring, feedbackProfiles, feed…
- `automation-lab/ebay-scraper` – eBay Scraper
  - Scrape eBay listings for price monitoring: prices, shipping, condition, seller ratings, bids, sold counts, discounts, and images. Filter by condition, listing type, and price range.
  - Eingabefelder: searchQueries, marketplace, maxProductsPerSearch, maxSearchPages, sort, condition, listingType, minPrice, maxPrice, maxRequestRetries
- `delicious_zebu/ebay-product-listing-scraper` – eBay Scraper - Listings, Prices & 8 Markets
  - Scrape eBay search results, filtered listings and category pages across 8 marketplaces. Build a search from built-in filters - keywords, category, price, condition, seller, location - or paste URLs. Returns title, price, currency, condition, seller rating, sh…
  - Eingabefelder: keywords, ebaySite, keywordMatch, excludeKeywords, searchTitleDescription, category, minPrice, maxPrice, buyingFormat, condition, freeShipping, locatedIn, availableTo, sellers, sellersMode, listingUrls, maxPages, sortBy, splitByPrice, proxyCountry


_Lauf: 2026-10-21 14:33 UTC, Stand 8d6b6f5_
