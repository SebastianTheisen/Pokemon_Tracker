# Spike Apify, Stufe F: Testläufe

- Verfügbare Proxy-Gruppen im Tarif: ['BUYPROXIES94952', 'GOOGLE_SERP', 'RESIDENTIAL', 'UNBLOCKER']

## PSA-Zertifikat 73270136 · fanndev (Note, Population, Verkäufe)

- Anbieter: `fanndev/psa-card-cert-lookup-scraper`
- Eingabe: `{"certNumber": "73270136", "maxItems": 1}`
- Status: SUCCEEDED  · Dauer 11 s
- Kosten: 0.004323057326792015 $ (Ereignisse: {"apify-default-dataset-item": 0, "apify-actor-start": 1})
- Ergebnisse: 1
- Felder: ["_error", "_errorDetail", "_input", "_scrapedAt", "_source", "recordType"]
- Sprachen: {'None': 1} · Zustände: {'None': 1}
  - 
- Erster Eintrag vollständig: `{"_input": "73270136", "_source": "S1-cert-page", "_scrapedAt": "2026-10-21T16:14:07Z", "recordType": "ERROR", "_error": "blocked_or_transient", "_errorDetail": "ChallengedUpstream(\"every TLS profile in ('firefox133', 'firefox135', 'chrome124', 'safari17_0') was challenged for https://www.psacard.com/cert/73270136 (last status 403). Cloudflare's rule may have changed.\")"}`

## PSA-Zertifikat 73270136 · lulzasaur (Population)

- Anbieter: `lulzasaur/psa-pop-scraper`
- Eingabe: `{"certNumber": "73270136"}`
- Status: SUCCEEDED Partial results: 0 record(s) saved; 1 lookup(s) failed; 0 not attempted before the time limit. · Dauer 26 s
- Kosten: 0 $ (Ereignisse: {"apify-actor-start": 4, "apify-default-dataset-item": 0})
- Ergebnisse: 0

## Echte Kosten je Lauf (30 s nach dem letzten Lauf)

- PSA-Zertifikat 73270136 · fanndev (Note, Population, Verkäufe): **0.006418947323529257 $** {"ACTOR_COMPUTE_UNITS": 0.00017, "DATASET_WRITES": 1e-05, "KEY_VALUE_STORE_READS": 1e-05, "KEY_VALUE_STORE_WRITES": 5e-05, "DATA_TRANSFER_INTERNAL_GBYTES": 1e-05, "DATA_TRANSFER_EXTERNAL_GBYTES": 0.0, "PROXY_RESIDENTIAL_TRANSFER_GBYTES": 0.00197}
- PSA-Zertifikat 73270136 · lulzasaur (Population): **0.0002 $** {}

**Verbrauch diesen Monat danach: 0.7386333630619735 $ von 8 $**

_Lauf: 2026-10-21 16:15 UTC, Stand 86cbff0_
