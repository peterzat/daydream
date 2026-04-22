"""Generate the v0 watercolor placeholder PNG.

Run once; the output is committed at web/assets/placeholder-meadow.png.
Regenerate when the WHIMSY palette or composition changes. Pillow is a
build-only dep (not runtime, not in pyproject); install ad-hoc:

    .venv/bin/pip install pillow
    .venv/bin/python tools/gen_placeholder.py

Aesthetic anchor: cozy, soft, painterly. Spiritfarer / A Short Hike.
NOT pixel art."""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "web" / "assets" / "placeholder-meadow.png"


def gen(width: int = 1024, height: int = 384, seed: int = 7) -> Image.Image:
    random.seed(seed)
    base = Image.new("RGB", (width, height), (246, 240, 220))
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / (height - 1)
        r = int(247 * (1 - t) + 162 * t)
        g = int(232 * (1 - t) + 174 * t)
        b = int(200 * (1 - t) + 134 * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    img = base.convert("RGBA")

    # Sun / moon glow upper-right, soft and warm.
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [int(width * 0.62), int(height * 0.05), int(width * 0.96), int(height * 0.42)],
        fill=(255, 240, 195, 80),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=42))
    img = Image.alpha_composite(img, glow)

    # Watercolor paint dabs across the meadow band (lower half).
    for _ in range(48):
        x = random.randint(-40, width + 40)
        y = random.randint(int(height * 0.45), height + 30)
        rx = random.randint(40, 150)
        ry = random.randint(14, 42)
        col = (
            random.randint(95, 170),
            random.randint(140, 192),
            random.randint(108, 152),
            random.randint(22, 58),
        )
        dab = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(dab).ellipse([x - rx, y - ry, x + rx, y + ry], fill=col)
        dab = dab.filter(ImageFilter.GaussianBlur(radius=14))
        img = Image.alpha_composite(img, dab)

    # Fireflies: small warm dots, slight bloom.
    fly = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fdr = ImageDraw.Draw(fly)
    for _ in range(60):
        x = random.randint(0, width)
        y = random.randint(int(height * 0.15), int(height * 0.85))
        r = random.randint(2, 5)
        fdr.ellipse(
            [x - r, y - r, x + r, y + r],
            fill=(255, 235, 170, random.randint(120, 200)),
        )
    fly = fly.filter(ImageFilter.GaussianBlur(radius=2))
    img = Image.alpha_composite(img, fly)

    # Final wash: tiny blur for a paper-y feel, then back to RGB.
    img = img.filter(ImageFilter.GaussianBlur(radius=1.4)).convert("RGB")
    return img


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img = gen()
    img.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
