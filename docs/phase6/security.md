# Sicherheits-Check (2026-10-24 09:09 UTC)

## Offene Ports von außen (alles außer localhost)
```
0.0.0.0:1404
0.0.0.0:37000
0.0.0.0:42370
0.0.0.0:45657
0.0.0.0:4567
0.0.0.0:45778
0.0.0.0:4579
0.0.0.0:4779
0.0.0.0:5200
0.0.0.0:8678
100.119.203.80:443
100.119.203.80:63670
[::]:1404
```

## Firewall (ufw)
```
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), deny (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
Anywhere                   DENY IN     95.222.118.0/24           
Anywhere                   DENY IN     95.222.119.0/24           
34001                      ALLOW IN    Anywhere                  
443                        ALLOW IN    Anywhere                  
4779                       ALLOW IN    Anywhere                  
5200                       ALLOW IN    Anywhere                  
4579                       ALLOW IN    Anywhere                  
45778                      ALLOW IN    Anywhere                  
37000                      ALLOW IN    Anywhere                  
4567                       ALLOW IN    Anywhere                  
8678                       ALLOW IN    Anywhere                  
42370                      ALLOW IN    Anywhere                  
1404                       ALLOW IN    Anywhere                  
45657                      ALLOW IN    Anywhere                  
51820/udp                  ALLOW IN    Anywhere                  
22/tcp (OpenSSH)           ALLOW IN    Anywhere                  
34001 (v6)                 ALLOW IN    Anywhere (v6)             
443 (v6)                   ALLOW IN    Anywhere (v6)             
4779 (v6)                  ALLOW IN    Anywhere (v6)             
5200 (v6)                  ALLOW IN    Anywhere (v6)             
4579 (v6)                  ALLOW IN    Anywhere (v6)             
45778 (v6)                 ALLOW IN    Anywhere (v6)             
37000 (v6)                 ALLOW IN    Anywhere (v6)             
```

## Veröffentlichte Container-Ports
```
api: 127.0.0.1:8000->8000/tcp
backup: 5432/tcp
db: 5432/tcp
monitor: 8000/tcp
tailscale: 
worker: 8000/tcp
```

## Benutzer in den Containern (soll nicht root sein)
```
api: tracker
worker: tracker
monitor: tracker
```

## Rechte der .env (soll 600 sein)
```
600 root
```

## Sicherheits-Header der App
```
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: no-referrer
permissions-policy: camera=(self), microphone=(), geolocation=()
strict-transport-security: max-age=31536000
```

## Ohne Anmeldung (soll 401 sein)
```
/api/v1/collection/items → 401
/api/v1/admin/users → 401
/api/v1/cards/search?q=pikachu → 401
```

## Tailscale
```
https://kartenkiste.<tailnet>.ts.net (tailnet only)
|-- / proxy http://api:8000

Geräte im Tailnet sichtbar: 3
```
