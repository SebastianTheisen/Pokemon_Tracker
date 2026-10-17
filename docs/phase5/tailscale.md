# Phase 5 – Tailscale auf dem VPS

- Datum: 2026-10-17 16:15 UTC
- Tailscale: `1.102.4`
- Adresse: `https://kartenkiste.<tailnet>.ts.net` (vollständiger Name bewusst nicht im Repo)
- Health über HTTPS im Tailnet: `{"status":"ok","version":"0.1.0","database":"ok"}`
- API von außen über die öffentliche IP, Port 8000 (Erwartung: keine Verbindung = 000): `000`

```
https://gtcha.tail6f0d61.ts.net (tailnet only)
|-- /     proxy http://127.0.0.1:8080
|-- /beta proxy http://127.0.0.1:8081

https://kartenkiste.<tailnet>.ts.net (tailnet only)
|-- / proxy http://127.0.0.1:8000

```
