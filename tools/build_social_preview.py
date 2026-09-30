"""Build pics/SAIMAIL_SOCIAL_PREVIEW.png at 1280x640 under 1MB.

Recompose (do not stretch) from the SAIMAIL2 mark and a SAIMAIL wordmark
using the Golden Default palette already present in the product sources.
No badges, no tiny technical text, no capability claims.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(ROOT, "pics", "SAIMAIL_LOGO.png")
OUT = os.path.join(ROOT, "pics", "SAIMAIL_SOCIAL_PREVIEW.png")

BG = (26, 24, 16)  # #1A1810 --background
SURFACE = (51, 46, 34)  # #332E22 --surface
ORANGE = (255, 180, 0)  # source artwork border orange
LINK = (240, 208, 96)  # #F0D060 --borderHighlight / --link
TEXT = (212, 200, 154)  # #D4C89A --textPrimary
BORDER_DARK = (16, 14, 8)  # #100E08 --borderDark

W, H = 1280, 640


def _font(size: int):
    candidates = (
        r"C:\Windows\Fonts\verdana.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def build() -> tuple[int, int, int]:
    logo = Image.open(LOGO).convert("RGBA")
    canvas = Image.new("RGBA", (W, H), BG + (255,))
    draw = ImageDraw.Draw(canvas)

    # Outer orange frame, matching the source mark/banner language.
    frame = 20
    draw.rectangle([0, 0, W - 1, H - 1], outline=ORANGE + (255,), width=frame)

    # Inner panel.
    inset = 44
    draw.rectangle(
        [inset, inset, W - inset - 1, H - inset - 1],
        fill=SURFACE + (255,),
        outline=LINK + (255,),
        width=3,
    )

    # Canonical mark, nearest-neighbour scaled (no AI regen, no blur).
    mark = 340
    logo_r = logo.resize((mark, mark), Image.Resampling.NEAREST)
    lx = 88
    ly = (H - mark) // 2
    canvas.alpha_composite(logo_r, (lx, ly))

    # Wordmark.
    font = _font(118)
    text = "SAIMAIL"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = lx + mark + 56
    ty = (H - th) // 2 - bbox[1] - 18

    # Hard outline for legibility when reduced; no soft shadow blur.
    for dx, dy in (
        (-3, 0),
        (3, 0),
        (0, -3),
        (0, 3),
        (-2, -2),
        (2, 2),
        (-2, 2),
        (2, -2),
    ):
        draw.text((tx + dx, ty + dy), text, font=font, fill=BORDER_DARK + (255,))
    draw.text((tx, ty), text, font=font, fill=LINK + (255,))

    # Short status line -- not tiny technical text, no badges, no claims.
    font2 = _font(34)
    sub = "LOCAL ONLY"
    bbox2 = draw.textbbox((0, 0), sub, font=font2)
    sw = bbox2[2] - bbox2[0]
    sx = tx + (tw - sw) // 2
    sy = ty + th + 26
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        draw.text((sx + dx, sy + dy), sub, font=font2, fill=BORDER_DARK + (255,))
    draw.text((sx, sy), sub, font=font2, fill=TEXT + (255,))

    canvas.convert("RGB").save(OUT, "PNG", optimize=True)
    size = os.path.getsize(OUT)
    im = Image.open(OUT)
    return im.size[0], im.size[1], size


if __name__ == "__main__":
    w, h, n = build()
    print(f"{w}x{h} bytes={n} under_1mb={n < 1_000_000}")
    assert (w, h) == (1280, 640), (w, h)
    assert n < 1_000_000, n
