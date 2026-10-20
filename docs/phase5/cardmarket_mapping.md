# Spike 2: Cardmarket-Verknüpfung über Katalog prüfen


## ❌ Abbruch

```
Traceback (most recent call last):
  File "<stdin>", line 139, in <module>
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "<stdin>", line 75, in main
  File "/srv/.venv/lib/python3.12/site-packages/httpx/_client.py", line 1376, in __init__
    super().__init__(
  File "/srv/.venv/lib/python3.12/site-packages/httpx/_client.py", line 210, in __init__
    self.headers = Headers(headers)
                   ^^^^^^^^^^^^^^^^
  File "/srv/.venv/lib/python3.12/site-packages/httpx/_models.py", line 156, in __init__
    bytes_value = _normalize_header_value(v, encoding)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/srv/.venv/lib/python3.12/site-packages/httpx/_models.py", line 82, in _normalize_header_value
    return value.encode(encoding or "ascii")
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
UnicodeEncodeError: 'ascii' codec can't encode character '\xfc' in position 62: ordinal not in range(128)
```

_Lauf: 2026-10-20 21:27 UTC, Stand cb335ce_
