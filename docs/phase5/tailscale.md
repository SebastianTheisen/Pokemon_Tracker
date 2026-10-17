# Phase 5 – Tailscale (eigenes Gerät „kartenkiste“ im Container)

- Datum: 2026-10-17 17:34 UTC
- Tailscale im Container: `1.104.1`
- Adresse: `https://kartenkiste.<tailnet>.ts.net`
- Health über HTTPS im Tailnet: `{"status":"ok","version":"0.1.0","database":"ok"}`

## Weiterleitung des Containers

```
https://kartenkiste.<tailnet>.ts.net (tailnet only)
|-- / proxy http://api:8000
```

## Tailscale direkt auf dem VPS (andere Apps, unverändert)

```
https://gtcha.<tailnet>.ts.net (tailnet only)
|-- /     proxy http://127.0.0.1:8080
|-- /beta proxy http://127.0.0.1:8081

https://kartenkiste.<tailnet>.ts.net (tailnet only)
|-- / proxy http://127.0.0.1:8000
```
