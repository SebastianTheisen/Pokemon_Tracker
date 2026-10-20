# Spike Apify, Stufe A: Kandidaten und Eingabefelder

- Konto: commendable_treeline · Tarif: FREE
- Verbrauch diesen Monat: 0 $ von 5 $ (bis 2026-11-19T23:59:59.999Z)

## Cardmarket-Angebote

### `phantom_coder/cardmarket-listings-scraper`

- Titel: Cardmarket Listings Scraper
- Preis: je Ereignis – apify-actor-start: None $ (Actor Start); card-listing: None $ (Card listing); iq-analysis: None $ (Add-on: Fair Value Analysis)
- Nutzer gesamt / 30 Tage: 80 / 18, zuletzt geändert 2026-10-20T14:10:55.083Z
- Beschreibung: Scrape all seller listings from any Cardmarket card page — condition, language, quantity, price in EUR/USD. Optional Fair Value Analysis for Scarlet & Violet and Mega Evolution sets adds AI pricing, PSA data, gem rate, and deal score.
- Eingabefelder (14):
  - `productUrl` (string, Pflicht, prefill=https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200): Cardmarket product URL
    - Cardmarket product page URL for the specific card you want to scrape.
  - `minCondition` (string, enum=["MT", "NM", "EX", "GD", "LP", "MP", "HP", "PO"], default=NM): Minimum condition
    - Only return listings at or better than this condition.
  - `language` (string, enum=["any", "English", "French", "German", "Spanish", "Italian", "S-Chinese", "Japanese", "Portuguese", "Russian", "Korean"], default=any): Language
    - Only return listings in this language.
  - `minPrice` (number): Min price (EUR)
    - Only return listings at or above this price in EUR.
  - `maxPrice` (number): Max price (EUR)
    - Only return listings at or below this price in EUR.
  - `sellerCountry` (string, enum=["any", "AT", "BE", "BG", "CA", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IS", "IE", "IT", "JP", "LV…, default=any): Seller country
    - Only show listings from sellers in this country.
  - `maxResults` (integer, default=10): Max results
    - Maximum number of listings to return per run. Runs return at most 50 listings: the cheapest ones matching your filters.
  - `enableFairValue` (boolean, default=false): 💎 Enable Fair Value Analysis ($)
    - Enrich each listing with an AI-powered fair value estimate, blended market price, PSA grade prices, price momentum, gem rate, and PSA population data. Available for Scarlet & Violet and Mega Evolution sets.
  - `foil` (string, enum=["any", "foil", "nonFoil"], default=any): Foil / reverse holo
    - Filter listings by foil finish. For Pokémon cards, this filters reverse holos.
  - `isSigned` (boolean, default=false): Signed cards only
    - Only return listings for signed cards.
  - `isAltered` (boolean, default=false): Altered art only
    - Only return listings for altered art cards.
  - `isFirstEd` (boolean, default=false): First edition only
    - Only return first edition listings.
  - `isPlayset` (boolean, default=false): Playsets only
    - Only return playset listings (4 copies).
  - `sellerType` (string, enum=["any", "private", "commercial"], default=any): Seller type
    - Filter by seller type.

### `crawloop/cardmarket-listings-scraper`

- Titel: Cardmarket Listings Scraper — Offers, Shops & Prices
- Preis: je Ereignis – apify-actor-start: 5e-05 $ (Actor Start); listing: None $ (Cardmarket listing)
- Nutzer gesamt / 30 Tage: 23 / 3, zuletzt geändert 2026-10-13T13:16:11.599Z
- Beschreibung: Scrape Cardmarket listings by product URL, seller shop, or keyword — a Cardmarket API alternative for EU TCG shops. Export seller, condition, language, quantity, and EUR price as JSON.
- Eingabefelder (25):
  - `searchKeywords` (array): Search keywords
    - Cardmarket product search queries (e.g. charizard, black lotus). Each keyword finds matching products, then seller offers on those product pages. Results are merged and deduplicated by listing ID.
  - `sellerUsernames` (array): Seller usernames
    - Walk each seller's Cardmarket shop inventory (Offers / Singles). Handles without @, e.g. CardGameCorner. Game-scoped — set game below. Optional shopQuery filters by card name.
  - `shopQuery` (string): Shop name filter
    - When walking seller shops (usernames or /Users/ URLs), only keep listings whose card name matches this filter. Leave empty for full inventory. Does not apply to marketplace keyword search.
  - `startUrls` (array, prefill=[{"url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200"}]): Start URLs
    - Cardmarket product, seller/shop, or search URLs. Product pages scrape seller offers. /Users/{handle}/Offers walks that shop. Search URLs parse searchString and game.
  - `game` (string, enum=["Pokemon", "Magic", "YuGiOh", "OnePiece", "Lorcana", "DragonBallSuper", "Digimon", "FleshAndBlood", "StarWarsUnlimited…, default=Pokemon): Game
    - Cardmarket catalog for keyword search and seller shops. Ignored when a start URL already contains the game path (e.g. /en/Magic/...).
  - `locale` (string, enum=["en", "de", "fr", "es", "it"], default=en): Site language
    - Cardmarket locale prefix (/en, /de, /fr, /es, /it). Prices stay in EUR.
  - `minCondition` (string, enum=["any", "MT", "NM", "EX", "GD", "LP", "PL", "PO"], default=any): Minimum condition
    - Only return listings at or better than this condition. Site grades: MT NM EX GD LP PL PO (Played is PL; MP is accepted as PL).
  - `language` (string, enum=["any", "English", "French", "German", "Spanish", "Italian", "S-Chinese", "Japanese", "Portuguese", "Russian", "Korean"…, default=any): Card language
    - Only return listings in this print language.
  - `sellerCountry` (string, enum=["any", "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", "GR", "HR", "HU", "IE", "IT", "LT…, default=any): Seller country
    - Only show listings from sellers in this country (ISO code).
  - `sellerType` (string, enum=["any", "private", "commercial", "professional", "powerseller"], default=any): Seller type
    - Filter by Cardmarket seller type. Commercial = professional + powerseller.
  - `sort` (string, enum=["best_match", "price_asc", "price_desc", "name_asc"], default=best_match): Sort
    - Sort for keyword search and seller shops. Product offer tables stay in Cardmarket price order.
  - `minPrice` (number): Min price (EUR)
    - Drop listings cheaper than this EUR amount.
  - `maxPrice` (number): Max price (EUR)
    - Drop listings more expensive than this EUR amount.
  - `isFoil` (boolean, default=false): Foil only
    - Only return foil listings when the product exposes a foil flag.
  - `isReverseHolo` (boolean, default=false): Reverse holo only
    - Only return reverse-holo listings.
  - `isSigned` (boolean, default=false): Signed cards only
    - Only return listings for signed cards.
  - `isAltered` (boolean, default=false): Altered art only
    - Only return listings for altered art cards.
  - `isFirstEd` (boolean, default=false): First edition only
    - Only return first-edition listings.
  - `isPlayset` (boolean, default=false): Playsets only
    - Only return playset listings (typically 4 copies).
  - `maxItems` (integer, default=100, prefill=8): Max items
    - Maximum listing rows to collect across all keywords, shops, and URLs. 0 = unlimited (subject to maxPages). Cardmarket product pages cap at 300 offers unless you tighten filters. Store / Console Try prefill is 8 so the 5…
  - `maxPages` (integer, default=20, prefill=1): Max pages per product / shop / search
    - Safety cap on pagination. Product offers load ~50 per page; shops ~20; search ~30 products. Shop inventory is capped at 15 pages (~300 hits) by Cardmarket. Store / Console Try prefill is 1 so the 5-minute quality check …
  - `monitorMode` (boolean, default=false): Monitor mode
    - On a schedule, push and charge only listing IDs not seen in a previous run. First run delivers the full match set (baseline). Pair with an Apify Schedule and a stable monitorStoreName.
  - `monitorStoreName` (string, default=cardmarket-listings-monitor): Monitor store name
    - Named Key-Value store for seen listing IDs across scheduled runs. Use a distinct name per watch (e.g. blastoise-nm vs charizard-shops).
  - `resetMonitorState` (boolean, default=false): Reset monitor state
    - Clear the seen-ID cache before this run (next run becomes a new baseline).
  - `proxyConfiguration` (object, default={"useApifyProxy": true, "apifyProxyGroups": ["UNBLOCKER"], "apifyProxyCountry": "DE"}, prefill={"useApifyProxy": true, "apifyProxyGroups": ["UNBLOCKER"], "apifyProxyCountry": "DE"}): Proxy configuration
    - Recommended on Apify: UNBLOCKER with country DE (Cardmarket Cloudflare). RESIDENTIAL+DE also works when Camoufox can solve the challenge. Local runs can leave proxy off.

### `lowlanddata/cardmarket-deal-finder`

- Titel: Cardmarket Listings Scraper - Live Offers, Stock & Prices
- Preis: je Ereignis – apify-default-dataset-item: None $ (result); apify-actor-start: 0.005 $ (Actor Start)
- Nutzer gesamt / 30 Tage: 14 / 6, zuletzt geändert 2026-10-13T05:42:25.203Z
- Beschreibung: Cardmarket listings scraper and deal finder in one: every live offer of the cards you search (price, condition, language, ship-from country), or only offers 25%+ under the official trend price - condition- and language-aware. Pokémon, Magic, Yu-Gi-Oh!, Lorcana and 11 more. No seller data.
- Eingabefelder (12):
  - `game` (string, enum=["pokemon", "magic", "yugioh", "lorcana", "onepiece", "digimon", "fleshandblood", "starwarsunlimited", "dragonballsuper…, default=pokemon, prefill=pokemon): Game
    - Which trading card game to hunt deals in.
  - `searchQuery` (string, Pflicht, prefill=charizard): Card search
    - <b>Required.</b> One or two distinctive words work best. For single cards: "charizard", "umbreon vmax", "black lotus". For sealed products, search the <b>set name as Cardmarket writes it</b> - it often differs from the …
  - `productType` (string, enum=["cards", "sealed", "both"], default=cards): Products
    - Single cards, or the sealed products Cardmarket lists in the same catalogue: booster boxes (displays), boosters, elite trainer boxes, tins, box sets and more. Sealed offers carry no condition, so the minimum condition b…
  - `minDiscountPct` (integer, default=25): Min discount vs trend (%)
    - An offer counts as a deal when it undercuts the card's trend price by at least this much. Set 0 for listings mode: every offer of the matched products, like a classic Cardmarket scraper (minus seller data).
  - `minCondition` (string, enum=["MT", "NM", "EX", "GD", "LP", "PL", "PO"], default=EX): Minimum condition
    - Ignore offers below this condition - a cheap damaged card is not a deal.
  - `languages` (array, default=["English", "German", "French", "Italian", "Spanish"], prefill=["English", "German", "French", "Italian", "Spanish"]): Card languages
    - Only count offers in these languages. Japanese and Korean prints trade far below the trend price, so mixing them in fakes discounts. Empty = all languages.
  - `priceMinEur` (integer, default=2): Min trend price (EUR)
    - Skip cards whose trend price is below this - filters bulk noise.
  - `priceMaxEur` (integer): Max trend price (EUR)
    - Skip cards whose trend price is above this.
  - `maxProducts` (integer, default=10): Products to check
    - How many candidate products to open and inspect per run.
  - `maxItems` (integer, default=100): Max deals
    - Upper bound on delivered deal rows.
  - `proxyConfiguration` (object, default={"useApifyProxy": true, "apifyProxyGroups": ["UNBLOCKER"]}, prefill={"useApifyProxy": true, "apifyProxyGroups": ["UNBLOCKER"]}): Proxy
    - Cardmarket requires Apify's Site Unblocker proxy (the UNBLOCKER group, preset here).
  - `reportFailures` (boolean, default=true): Report failures to the developer
    - When a run fails, send the developer the actor name and build, an error category, the error message (truncated) and a one-way hash of your input - so a bug can be fixed without anyone asking you to reproduce it. <b>Your…

### `lulzasaur/cardmarket-scraper`

- Titel: Cardmarket Scraper - TCG Card Prices & Trends
- Preis: {"pricingModel": "FREE", "createdAt": "2026-10-19T21:27:02.893Z", "startedAt": "2026-11-02T21:27:02.727Z", "apifyMarginPercentage": 0, "notifiedAboutFutureChan…
- Nutzer gesamt / 30 Tage: 25 / 5, zuletzt geändert 2026-10-19T21:27:02.882Z
- Beschreibung: Scrape Cardmarket, Europe's largest TCG marketplace. Get card name, set/expansion, lowest price, price trend, 30/7/1-day averages, availability, rarity and URL for Magic, Pokemon, Yu-Gi-Oh and more. Search by keyword.
- Eingabefelder (5):
  - `searchQueries` (array, prefill=["Black Lotus"]): Search Queries
    - One or more card names or keywords to search on Cardmarket (e.g. 'Black Lotus', 'Charizard', 'Blue-Eyes White Dragon'). Each query is searched independently.
  - `game` (string, enum=["Magic", "Pokemon", "YuGiOh", "Lorcana", "OnePiece", "FleshAndBlood", "Digimon", "DragonBallSuper", "StarWarsUnlimited…, default=Magic): Game / Category
    - TCG category to search within. Choose Magic, Pokemon, Yu-Gi-Oh, Lorcana, One Piece, Flesh and Blood, Digimon, Dragon Ball Super or Star Wars Unlimited.
  - `maxResults` (integer, default=50, prefill=25): Max Results (per query)
    - Maximum number of card products to scrape per query. Set to 0 for unlimited (all matching results). Default is 50.
  - `scrapeDetails` (boolean, default=false): Scrape Detail Pages
    - If enabled, visit each product page to also capture Price Trend and 30/7/1-day average prices. Slower and uses more compute, but richer data. If disabled, only search-result fields (name, set, lowest price, availability…
  - `proxyConfiguration` (object, default={"useApifyProxy": true, "apifyProxyGroups": ["RESIDENTIAL"]}): Proxy Configuration
    - Proxy settings. Cardmarket is protected by Cloudflare — RESIDENTIAL proxies are strongly recommended and used by default. Do not disable the proxy.

## eBay verkauft

### `automation-lab/ebay-sold-scraper`

  - ❌ `/acts/automation-lab~ebay-sold-scraper` → HTTP 404: {
  "error": {
    "type": "record-not-found",
    "message": "Actor with this name was not found"
  }
}

### `parsebird/ebay-sold-listings-scraper`

- Titel: eBay Sold Listings Scraper
- Preis: je Ereignis – apify-actor-start: 5e-05 $ (Actor Start); listing-scraped: None $ (eBay sold listing)
- Nutzer gesamt / 30 Tage: 67 / 12, zuletzt geändert 2026-08-09T12:55:36.649Z
- Beschreibung: Scrape eBay sold listings with real transaction prices across 8 marketplaces. Filter by keyword, category, price, condition, date range, and sort order. Returns 22+ fields per item including sold price, shipping, seller info, and listing type.
- Eingabefelder (14):
  - `keywords` (array, prefill=["iphone 15 pro"]): Keywords
    - 1–6 search terms. Each keyword runs as a separate search with the same filters applied. Results are tagged with the keyword for easy filtering.
  - `daysToScrape` (integer, default=30, prefill=30): Days to Scrape
    - Number of days back to include sold listings (1–90). Listings older than this are excluded from results.
  - `count` (integer, default=100, prefill=50): Max Results per Keyword
    - Maximum number of sold listings to return per keyword. Lower values produce faster, cheaper runs.
  - `categoryId` (string, enum=["0", "550", "2984", "267", "12576", "625", "15032", "11450", "11116", "1", "58058", "293", "14339", "237", "45100", "9…, default=0, prefill=0): Category
    - eBay main category filter. Use 'All Categories' for the broadest search.
  - `subcategoryId` (string, default=): Subcategory
    - Optional subcategory ID. When set, overrides the Category field (maps to _sacat). Find IDs at https://sold-comps.com/ebay-categories
  - `ebaySite` (string, enum=["ebay.com", "ebay.co.uk", "ebay.de", "ebay.fr", "ebay.it", "ebay.es", "ebay.ca", "ebay.com.au"], default=ebay.com, prefill=ebay.com): eBay Site
    - eBay marketplace to search. Each site has its own listings, currency, and language.
  - `sortOrder` (string, enum=["endedRecently", "timeNewlyListed", "pricePlusPostageLowest", "pricePlusPostageHighest", "distanceNearest"], default=endedRecently, prefill=endedRecently): Sort Order
    - How to sort sold search results.
  - `minPrice` (number): Min Price
    - Minimum sold price filter. Leave empty for no minimum.
  - `maxPrice` (number): Max Price
    - Maximum sold price filter. Leave empty for no maximum.
  - `itemLocation` (string, enum=["default", "domestic", "worldwide"], default=default): Item Location
    - Filter by where the item is located.
  - `itemCondition` (string, enum=["any", "new", "used"], default=any): Condition
    - Filter by item condition.
  - `keyword` (string): Keyword (deprecated — use Keywords)
    - Single search keyword. Deprecated: use the 'keywords' array field instead. Accepted for backward compatibility.
  - `search` (string): Search (deprecated — use Keywords)
    - Deprecated alias for 'keyword'. Use the 'keywords' array instead. Backslash-escaped quotes in the value are unescaped before the search runs.
  - `proxyConfiguration` (object, default={"useApifyProxy": true}, prefill={"useApifyProxy": true}): Proxy Configuration
    - Datacenter proxies work for most runs. Switch to residential if you see blocks or empty results.

### `yumitori/ebay-sold-scraper`

- Titel: eBay Sold Items Scraper: Sold Prices, Comps & Sell-Through
- Preis: {"pricingModel": "FREE", "createdAt": "2026-10-04T06:53:01.226Z", "startedAt": "2026-10-18T06:53:01.020Z", "apifyMarginPercentage": 0, "notifiedAboutFutureChan…
- Nutzer gesamt / 30 Tage: 13 / 3, zuletzt geändert 2026-10-04T06:53:01.212Z
- Beschreibung: ⚡🔥 BLAZING-FAST eBay sold-price scraper — every real sold price for any keyword in seconds. See what items really sell for, not asking prices, and price every flip right. Median & avg · sneakers, cards, electronics, any category · 8 marketplaces · newest-first.
- Eingabefelder (9):
  - `queries` (array, prefill=["jordan 1", "pokemon booster box"]): Keywords
    - What to look up — one search term per line. You get every sold listing for each.
  - `ask` (string): Ask in plain English (optional)
    - Another way in — instead of the keyword field above, just ask a question: “how much do used AirPods Pro 2 sell for in the UK last 30 days”, “sealed pokemon booster box prices this year”, “compare iphone 15 pro on US vs …
  - `marketplace` (string, enum=["US", "GB", "DE", "FR", "IT", "ES", "CA", "AU"], default=US): eBay marketplace
    - Which eBay site to pull sold listings from.
  - `categories` (array, default=[]): Categories (optional)
    - Leave EMPTY (default) and each keyword is auto-scoped to its single most-relevant eBay category — this keeps comps accurate (a "nintendo switch" search returns real Switch consoles, not $5 games). Pick one or more categ…
  - `categoryIdsCustom` (array, prefill=[]): Custom category IDs — paste from the lookup tool
    - 🔎 Find & copy any eBay category IDs at https://ebay-categories.pages.dev (search by product or brand, select multiple, copy), then paste them here — one per line.
  - `maxComps` (integer, default=1000): Max sold listings per keyword
    - How many sold listings to pull per keyword — enough to cover the entire sold history for a term. Results come newest-sold first.
  - `days` (string, enum=["7", "14", "30", "60", "90", "180", "365"], default=90): Only items sold in the last…
    - Filter to items sold within this window. Results always come newest-sold first.
  - `enrichDetails` (boolean, default=false): Enrich with item details (condition · specifics · seller)
    - OFF (default) = fastest, core sold fields only. ON = adds condition, item specifics (size · storage · color) and seller + feedback score to the newest listings, shown in a separate “🔎 With details” output tab. This make…
  - `cardPriceGuide` (boolean, default=true): 🃏 Card Price Guide (auto for graded cards)
    - ON (default) = when a keyword is a graded trading card, the run ALSO returns eBay’s per-grade Price Guide — PSA/BGS/CGC values with sold counts — plus a Card Price Guide report in Storage. Auto-detected and self-gating:…

### `tnodes/ebay-sold-scraper`

- Titel: eBay Sold Listings Scraper
- Preis: je Ereignis – apify-actor-start: 1e-05 $ (Actor Start); apify-default-dataset-item: 0.002 $ (result)
- Nutzer gesamt / 30 Tage: 43 / 4, zuletzt geändert 2026-05-21T06:33:27.458Z
- Beschreibung: Scrape real sold prices, dates, conditions, and shipping from eBay's completed listings filter. Residential-proxy backed (Apify pool) with Chrome 124 TLS fingerprint impersonation — bypasses eBay's anti-bot.
- Eingabefelder (5):
  - `keyword` (string, Pflicht, example=Samsung PM883 1.92TB): Search Keyword
    - Search term (product name, MPN, or model number). eBay's fuzzy search applies — `Samsung PM883 1.92TB` matches PM883-series listings.
  - `condition` (string, enum=["any", "new", "used"], default=any): Condition
    - Restrict to one condition bucket. `any` returns both. eBay's New = factory-sealed + open-box + refurbished; Used = pre-owned + acceptable + for-parts.
  - `daysToScrape` (integer, default=60): Days to Scrape
    - Only return listings sold within the last N days. eBay caps sold-listing visibility at 90 days regardless.
  - `count` (integer, default=50): Max Results
    - Maximum number of listings to return (after filtering).
  - `proxyConfiguration` (object, default={"useApifyProxy": true, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "US"}, prefill={"useApifyProxy": true, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "US"}): Proxy Configuration
    - eBay aggressively blocks datacenter IPs — keep the default (Apify Residential) for best results. You can also use your own proxies if you have a deal with another provider.

### `caffein.dev/ebay-sold-listings`

- Titel: eBay Sold Listings Search
- Preis: je Ereignis – apify-default-dataset-item: None $ (result); apify-actor-start: 5e-05 $ (Actor Start)
- Nutzer gesamt / 30 Tage: 4097 / 872, zuletzt geändert 2026-09-15T23:28:17.435Z
- Beschreibung: Get confirmed eBay sold prices. Search by keyword across 8 marketplaces, filter by date range, and export clean structured data for comps, resale pricing, and market research.
- Eingabefelder (17):
  - `keywords` (array, prefill=["rtx 4080"]): Keywords
    - One or more search keywords. Each keyword runs as a separate search with the same filters applied to all.
  - `keyword` (string): Keyword (deprecated — use Keywords)
    - Single search keyword. Deprecated: use the 'keywords' array field instead.
  - `search` (string): Search (deprecated — use Keywords)
    - Deprecated: alias for the single-keyword `keyword` field. Use the `keywords` array instead. Accepted for backward compatibility with callers that send `search`. Backslash-escaped quotes (\") in the value are unescaped b…
  - `categoryId` (string, default=0): Category
    - eBay category ID — maps directly to the `_sacat` URL parameter. Enter ANY eBay category ID as free text; you are not limited to a preset list. Use "0" (the default) for All Categories. Don't know the ID? We maintain the…
  - `subcategoryId` (string, default=): Subcategory
    - Optional eBay subcategory ID — also maps to `_sacat`. Enter ANY subcategory ID as free text. When set, it overrides the Category field above. Leave blank to search at the category level. Full ID reference: https://sold-…
  - `ebaySite` (string, enum=["ebay.com", "ebay.co.uk", "ebay.de", "ebay.fr", "ebay.it", "ebay.es", "ebay.ca", "ebay.com.au"], default=ebay.com): eBay Site
    - eBay site to scrape from
  - `daysToScrape` (integer, default=30): Days to Scrape
    - Number of days back to scrape sold listings (default: 30)
  - `count` (integer, default=100): Count
    - Number of listings to scrape (default: 100)
  - `sortOrder` (string, enum=["endedRecently", "timeNewlyListed", "pricePlusPostageLowest", "pricePlusPostageHighest", "distanceNearest"], default=endedRecently): Sort order
    - Sort order for the sold search results page.
  - `minPrice` (integer): Min price
    - Minimum sold price filter (search-page filter).
  - `maxPrice` (integer): Max price
    - Maximum sold price filter (search-page filter).
  - `buyingFormat` (string, enum=["all", "auction", "buyItNow", "acceptsOffers"], default=all): Buying format
    - Search-page buying format filter.
  - `itemLocation` (string, enum=["default", "domestic", "worldwide"], default=default): Item location
    - Search-page item location filter.
  - `itemCondition` (string, enum=["any", "new", "used"], default=any): Condition
    - Search-page condition filter.
  - `conditionId` (integer): Condition ID
    - Numeric eBay condition ID — overrides itemCondition when set.
  - `aspectFilter` (object): Aspect filter
    - eBay aspect facet filters, e.g. {"Brand": "Nike"}. Keys and values are double-encoded per eBay's convention.
  - `includeCompletedListings` (boolean, default=true): Include Completed Listings
    - When true (default), includes eBay's Completed Listings filter alongside the Sold filter. This enables accurate detection of 'Best Offer Accepted' listings via the listingType and isBestOfferAccepted fields. When false,…


_Lauf: 2026-10-20 22:03 UTC, Stand 0ded335_
