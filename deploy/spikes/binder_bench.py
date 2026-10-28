"""Messung der Binder-Zerlegung: synthetische, realistische Seiten aus den Testkarten.

Karten in Hüllen auf dunkler Seite, Tisch drumherum, Schräglage, Glanzstreifen. Gezählt wird je
Zelle, ob der Bildabgleich die Karte an der richtigen Stelle findet (fehlende Zellen = falsch).

    cd backend && uv run python ../deploy/spikes/binder_bench.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.scanner.binder import binder_cells  # noqa: E402
from app.scanner.imaging import card_crop, decode_image  # noqa: E402
from app.scanner.matching import extract_features, match_score  # noqa: E402

TESTSET = str(Path(__file__).resolve().parents[2] / "scanner_testset") + "/"
NAMES = ["03.jpg", "02.jpg", "05.jpg", "06.jpg", "07.jpg"]
CARD_W, CARD_H = 420, 588
rng = np.random.default_rng(7)

crops = {}
for name in NAMES:
    img = decode_image(open(TESTSET + name, "rb").read())
    crop = card_crop(img)
    crops[name] = cv2.resize(crop if crop is not None else img, (CARD_W, CARD_H))
refs = {name: extract_features(c, max_features=2000) for name, c in crops.items()}


def page(cols: int, rows: int, order: list[str], *, gap: int = 26, sleeve: bool = True) -> np.ndarray:
    w = cols * CARD_W + (cols + 1) * gap
    h = rows * CARD_H + (rows + 1) * gap
    p = np.full((h, w, 3), (40, 40, 40), np.uint8)  # dunkle Binderseite
    for i, name in enumerate(order):
        r, c = divmod(i, cols)
        y, x = gap + r * (CARD_H + gap), gap + c * (CARD_W + gap)
        card = crops[name].copy()
        if sleeve:  # Hülle: leicht milchig + heller Rand
            card = cv2.addWeighted(card, 0.9, np.full_like(card, 230), 0.1, 0)
            cv2.rectangle(p, (x - 8, y - 8), (x + CARD_W + 8, y + CARD_H + 8), (90, 90, 90), 2)
        p[y : y + CARD_H, x : x + CARD_W] = card
    return p


def scene(p: np.ndarray, *, margin: float, tilt: float, glare: bool, glare2: bool = False) -> np.ndarray:
    h, w = p.shape[:2]
    mh, mw = int(h * margin), int(w * margin)
    bg = np.full((h + 2 * mh, w + 2 * mw, 3), (120, 150, 175), np.uint8)  # Holztisch-artig
    noise = rng.integers(-15, 15, bg.shape, dtype=np.int16)
    bg = np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    d = tilt * w
    dst = np.float32([[mw + d, mh], [mw + w - d * 0.3, mh + d * 0.5], [mw + w, mh + h], [mw, mh + h - d * 0.4]])
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(p, m, (bg.shape[1], bg.shape[0]))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (bg.shape[1], bg.shape[0]))
    out = bg.copy()
    out[mask > 0] = warped[mask > 0]
    if glare:
        overlay = out.copy()
        cv2.line(overlay, (0, int(out.shape[0] * 0.3)), (out.shape[1], int(out.shape[0] * 0.55)), (255, 255, 255), 60)
        out = cv2.addWeighted(out, 0.75, overlay, 0.25, 0)
    if glare2:
        overlay = out.copy()
        cv2.ellipse(overlay, (int(out.shape[1] * 0.65), int(out.shape[0] * 0.35)), (260, 120), 30, 0, 360, (255, 255, 255), -1)
        cv2.line(overlay, (int(out.shape[1] * 0.1), 0), (int(out.shape[1] * 0.45), out.shape[0]), (255, 255, 255), 45)
        out = cv2.addWeighted(out, 0.7, overlay, 0.3, 0)
    # wie die App: längste Seite höchstens 2400
    s = 2400 / max(out.shape[:2])
    return cv2.resize(out, None, fx=s, fy=s) if s < 1 else out


def evaluate(image: np.ndarray, order: list[str], layout: str = "auto") -> tuple[int, int, str]:
    cells, method = binder_cells(image, layout)  # type: ignore[arg-type]
    correct = 0
    cols = 3 if len(order) == 9 else 4
    for cell in cells:
        if cell.row >= len(order) // cols or cell.column >= cols:
            continue
        q = extract_features(cell.image)
        scores = {n: match_score(q, f) for n, f in refs.items()}
        best = max(scores, key=scores.get)
        if scores[best] >= 20 and best == order[cell.row * cols + cell.column]:
            correct += 1
    return correct, len(order), method


order9 = [NAMES[i % 5] for i in range(9)]
order12 = [NAMES[(i * 2) % 5] for i in range(12)]
cases = {
    "9er randlos": scene(page(3, 3, order9), margin=0.0, tilt=0.0, glare=False),
    "9er mit Tisch 12%": scene(page(3, 3, order9), margin=0.12, tilt=0.0, glare=False),
    "9er Tisch + schräg": scene(page(3, 3, order9), margin=0.10, tilt=0.04, glare=False),
    "9er Tisch + schräg + Glanz": scene(page(3, 3, order9), margin=0.10, tilt=0.04, glare=True),
    "12er quer + Tisch": scene(page(4, 3, order12), margin=0.08, tilt=0.02, glare=False),
    "9er randlos + Glanz": scene(page(3, 3, order9), margin=0.0, tilt=0.0, glare=True),
    "9er Tisch + 2x Glanz": scene(page(3, 3, order9), margin=0.10, tilt=0.03, glare=True, glare2=True),
    "12er quer + Glanz": scene(page(4, 3, order12), margin=0.08, tilt=0.02, glare=True),
    "9er Tisch 20% + schräg": scene(page(3, 3, order9), margin=0.20, tilt=0.05, glare=False),
}
total = good = 0
for label, img in cases.items():
    order = order12 if "12er" in label else order9
    c, n, method = evaluate(img, order)
    total += n
    good += c
    print(f"{label:28s} {c}/{n} richtig  (Verfahren: {method})", flush=True)
print(f"GESAMT {good}/{total} = {good / total:.0%}")
