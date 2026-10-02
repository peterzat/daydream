#!/usr/bin/env python3
"""Make the link-preview card and the site icons from a door painting.

A link shared in iMessage, Slack and the like unfurls from the door page's
Open Graph tags (web/door.html, filled by daydream/server.py:_page): the card
is og:image, shown large above the page's title. Platforms want about
1200x630 (1.91:1); the card is written as a JPEG (the --card path). The
door paintings are wider than that, so the card sets the painting as a plate
on the page's paper, the way the door does, with the hand-lettered wordmark
beneath. The icons: icon-180.png (a phone's home screen) is a square crop of
the same painting; icon-32.png (the tab, the small mark beside a Slack
unfurl) is the drawn mark.

    .venv/bin/python tools/make_link_card.py web/assets/door-village.png \\
        --card web/assets/card-village.jpg --icons web/assets

Colours are DESIGN.md tokens; the font is the self-hosted Caveat. Look at
what it writes before committing: the geometry is checked here, the eye is not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parent.parent
FONT = REPO / "web/assets/fonts/caveat-latin-var.woff2"
W, H = 1200, 630
BG = (246, 243, 236)       # --bg
INK = (58, 74, 68)         # --ink
SAGE = (74, 106, 90)       # --sage-deep
MARGIN = 44
RADIUS = 18
WORDMARK = "daydream"


def _rounded(im: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def card(door: Image.Image) -> Image.Image:
    page = Image.new("RGB", (W, H), BG)
    plate_w = W - 2 * MARGIN
    plate_h = round(door.height * plate_w / door.width)
    band = H - MARGIN - plate_h
    if band < 150:
        raise SystemExit(f"the painting is too tall for a card ({door.size}); crop it first")
    plate = _rounded(door.convert("RGB").resize((plate_w, plate_h), Image.LANCZOS), RADIUS)
    # A soft shadow under the plate, like the door's --page-shadow.
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (MARGIN + 6, MARGIN + 16, MARGIN + plate_w - 6, MARGIN + plate_h + 10), RADIUS,
        fill=(74, 106, 90, 70))
    page.paste(shadow.filter(ImageFilter.GaussianBlur(14)), (0, 0),
               shadow.filter(ImageFilter.GaussianBlur(14)))
    page.paste(plate, (MARGIN, MARGIN), plate)

    font = ImageFont.truetype(str(FONT), 112)
    try:
        font.set_variation_by_axes([600])
    except OSError:
        pass  # a static build of the font: its one weight
    draw = ImageDraw.Draw(page)
    left, top, right, bottom = draw.textbbox((0, 0), WORDMARK, font=font)
    x = (W - (right - left)) // 2 - left
    y = MARGIN + plate_h + (band - (bottom - top)) // 2 - top
    draw.text((x, y), WORDMARK, font=font, fill=INK)
    left, top, right, bottom = draw.textbbox((x, y), WORDMARK, font=font)
    if left < MARGIN or right > W - MARGIN or top < MARGIN + plate_h or bottom > H - 8:
        raise SystemExit(f"the wordmark does not fit its band: {(left, top, right, bottom)}")
    return page


def mark(size: int) -> Image.Image:
    """The tab's icon: a painting is a smudge at 32 px, so the wordmark's
    first letter, paper on sage, drawn large and scaled down."""
    big = size * 8
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), big // 5, fill=SAGE)
    font = ImageFont.truetype(str(FONT), int(big * 0.95))
    try:
        font.set_variation_by_axes([700])
    except OSError:
        pass
    left, top, right, bottom = draw.textbbox((0, 0), "d", font=font)
    draw.text(((big - (right - left)) // 2 - left, (big - (bottom - top)) // 2 - top), "d",
              font=font, fill=BG)
    return im.resize((size, size), Image.LANCZOS)


def icons(door: Image.Image) -> dict[str, Image.Image]:
    """The home-screen icon is a square from the painting's left end (on the
    village's door: the near cottages, where its detail is largest); the tab's
    is the mark."""
    side = door.height
    square = door.convert("RGB").crop((0, 0, side, side))
    return {"icon-180.png": square.resize((180, 180), Image.LANCZOS), "icon-32.png": mark(32)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("door", type=Path, help="the door painting (web/assets/door-*.png)")
    p.add_argument("--card", type=Path, required=True, help="where the 1200x630 card goes")
    p.add_argument("--icons", type=Path, help="a folder for icon-180.png and icon-32.png")
    args = p.parse_args(argv)
    door = Image.open(args.door)
    # A watercolour is a photograph to a codec: JPEG is a tenth of the PNG,
    # and the phone that unfurls the link downloads it.
    card(door).save(args.card, optimize=True, quality=88)
    print(f"card: {args.card} ({W}x{H})")
    if args.icons:
        for name, im in icons(door).items():
            im.save(args.icons / name, optimize=True)
            print(f"icon: {args.icons / name} ({im.width}x{im.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
