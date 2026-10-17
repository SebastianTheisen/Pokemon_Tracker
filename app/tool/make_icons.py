"""Erzeugt das App-Icon „Kartenkiste“ (eigenes Motiv, keine fremde Marke) in allen Größen.

Aufruf (aus app/):  ../backend/.venv/bin/python tool/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

NAVY = (11, 20, 38)
BLUE = (76, 125, 255)
VIOLET = (139, 92, 246)
APP = Path(__file__).resolve().parents[1]


def gradient(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            pixels[x, y] = tuple(round(BLUE[i] + (VIOLET[i] - BLUE[i]) * t) for i in range(3))
    return image


def icon(size: int, *, maskable: bool = False, rounded: bool = True) -> Image.Image:
    """Zwei versetzte Karten über einer Kiste. ``maskable``: Motiv kleiner (sichere Zone)."""
    scale = 4  # Supersampling für glatte Kanten
    big = size * scale
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    background = gradient(big).convert("RGBA")
    mask = Image.new("L", (big, big), 0)
    radius = 0 if (maskable or not rounded) else big // 5
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=radius, fill=255)
    canvas.paste(background, (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    inset = 0.22 if maskable else 0.14
    area = big * (1 - 2 * inset)
    left, top = big * inset, big * inset
    card_w, card_h = area * 0.42, area * 0.42 * 88 / 63
    line = max(2, round(big * 0.018))
    for offset in (-0.13, 0.09):  # hintere und vordere Karte
        cx = left + area * (0.5 + offset)
        x0, y0 = cx - card_w / 2, top + area * 0.04 + (0.05 if offset > 0 else 0) * area
        draw.rounded_rectangle(
            (x0, y0, x0 + card_w, y0 + card_h),
            radius=card_w * 0.1,
            fill=(255, 255, 255, 240) if offset > 0 else (255, 255, 255, 170),
            outline=NAVY + (255,),
            width=line,
        )
    # Kiste
    box_top = top + area * 0.58
    draw.rounded_rectangle(
        (left + area * 0.08, box_top, left + area * 0.92, top + area * 0.98),
        radius=area * 0.06,
        fill=NAVY + (255,),
    )
    draw.rounded_rectangle(
        (left + area * 0.38, box_top + area * 0.12, left + area * 0.62, box_top + area * 0.2),
        radius=area * 0.03,
        fill=BLUE + (255,),
    )
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    web = APP / "web"
    icon(16).save(web / "favicon.png")
    for size in (192, 512):
        icon(size).save(web / "icons" / f"Icon-{size}.png")
        icon(size, maskable=True).save(web / "icons" / f"Icon-maskable-{size}.png")
    icon(180, rounded=False).convert("RGB").save(web / "icons" / "apple-touch-icon.png")
    densities = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for name, size in densities.items():
        icon(size).save(APP / "android" / "app" / "src" / "main" / "res" / f"mipmap-{name}" / "ic_launcher.png")
    print("Icons erzeugt.")


if __name__ == "__main__":
    main()
