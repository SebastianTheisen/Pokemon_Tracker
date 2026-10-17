"""Scanner: Karten auf Fotos erkennen (Plan 5.6).

Die Module hier sind reine Bild- und Textverarbeitung ohne Datenbank:

* :mod:`~app.scanner.imaging` – Fotos sicher laden, verkleinern, Karte suchen und entzerren
* :mod:`~app.scanner.ocr` – Texterkennung (RapidOCR, PP-OCRv6 + koreanisches Modell)
* :mod:`~app.scanner.text` – Merkmale aus dem Text: Nummer, Setcode, Name, Sprache
* :mod:`~app.scanner.slab` – Grading-Labels (PSA/BGS/CGC)
* :mod:`~app.scanner.matching` – Bildabgleich (SIFT + RANSAC)
* :mod:`~app.scanner.binder` – Binderseite in einzelne Karten zerlegen (Beta)
* :mod:`~app.scanner.storage` – Merkmal-Cache, eigene Referenzbilder, offene Scans
* :mod:`~app.scanner.catalog_images` – Katalogbilder laden (lazy, mit Cache)
* :mod:`~app.scanner.runtime` – bündelt alles für die App

Die Identifikation gegen den Katalog (Datenbank) liegt in :mod:`app.services.scan`.
"""
