"""
Generates fb_cleaner.ico -- the app / desktop-shortcut icon.

Everything is drawn once at 4x scale and downsampled with LANCZOS, so the small
16px and 32px entries come out smooth instead of the jagged per-size arcs the
previous version produced.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE_DIR = Path(__file__).resolve().parent
OUT_FILE = BASE_DIR / "fb_cleaner.ico"
PNG_PREVIEW = BASE_DIR / "fb_cleaner_icon.png"

MASTER = 1024                       # drawing canvas; final sizes are downsampled
SIZES = [256, 128, 64, 48, 32, 24, 16]

DEEP_BLUE = (14, 86, 205)
FB_BLUE = (24, 119, 242)
CYAN = (0, 214, 254)
WHITE = (255, 255, 255)


def _rounded_mask(size: int, radius_ratio: float = 0.235) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return mask


def _diagonal_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    """Vertical-ish gradient built row by row, then sheared slightly for depth."""
    grad = Image.new("RGB", (1, size))
    px = grad.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((size, size), Image.BILINEAR)


def _load_font(px: int) -> ImageFont.FreeTypeFont | None:
    for name in ("segoeuib.ttf", "seguibl.ttf", "arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    return None


def _draw_f(draw: ImageDraw.ImageDraw, size: int):
    """Vector 'f' -- used when no bold system font can be loaded."""
    s = size
    stem_w = int(s * 0.105)
    stem_x = int(s * 0.505)
    top_y = int(s * 0.275)
    bottom_y = int(s * 0.775)

    draw.rounded_rectangle(
        [stem_x - stem_w // 2, int(s * 0.375), stem_x + stem_w // 2, bottom_y],
        radius=stem_w // 3, fill=WHITE,
    )
    draw.rounded_rectangle(
        [int(s * 0.375), int(s * 0.455), int(s * 0.625), int(s * 0.455) + stem_w],
        radius=stem_w // 3, fill=WHITE,
    )
    draw.arc(
        [stem_x - int(s * 0.115), top_y, stem_x + int(s * 0.135), top_y + int(s * 0.22)],
        start=180, end=360, fill=WHITE, width=stem_w,
    )


def build_master() -> Image.Image:
    s = MASTER
    icon = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # --- background tile: blue -> cyan gradient, rounded-square clipped -------
    bg = _diagonal_gradient(s, DEEP_BLUE, FB_BLUE).convert("RGBA")
    sheen = _diagonal_gradient(s, CYAN, FB_BLUE).convert("RGBA")
    sheen.putalpha(90)
    bg = Image.alpha_composite(bg, sheen)
    icon.paste(bg, (0, 0), _rounded_mask(s))

    # --- soft top-left highlight --------------------------------------------
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-int(s * 0.25), -int(s * 0.42), int(s * 0.85), int(s * 0.48)], fill=(255, 255, 255, 46))
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.06))
    icon = Image.alpha_composite(icon, Image.composite(
        glow, Image.new("RGBA", (s, s), (0, 0, 0, 0)), _rounded_mask(s)))

    draw = ImageDraw.Draw(icon)

    # --- cyan "sweep" arc: the cleaning half of the identity ------------------
    ring_pad = int(s * 0.135)
    ring_box = [ring_pad, ring_pad, s - ring_pad, s - ring_pad]
    draw.arc(ring_box, start=128, end=372, fill=CYAN + (235,), width=int(s * 0.035))

    # arrowhead closing the sweep, so it reads as "clean / refresh"
    ang = math.radians(128)
    cx, cy = s / 2, s / 2
    r = (s - 2 * ring_pad) / 2
    tipx, tipy = cx + r * math.cos(ang), cy + r * math.sin(ang)
    head = int(s * 0.055)
    draw.polygon(
        [(tipx - head, tipy - head * 0.25), (tipx + head * 0.55, tipy - head * 1.15),
         (tipx + head * 0.75, tipy + head * 0.75)],
        fill=CYAN + (235,),
    )

    # --- the Facebook 'f' ----------------------------------------------------
    font = _load_font(int(s * 0.62))
    if font is not None:
        box = draw.textbbox((0, 0), "f", font=font)
        w, h = box[2] - box[0], box[3] - box[1]
        draw.text((s / 2 - w / 2 - box[0], s / 2 - h / 2 - box[1] - int(s * 0.015)),
                  "f", font=font, fill=WHITE)
    else:
        _draw_f(draw, s)

    return icon


def main():
    master = build_master()
    frames = [master.resize((n, n), Image.LANCZOS) for n in SIZES]
    frames[0].save(OUT_FILE, format="ICO", sizes=[(n, n) for n in SIZES])
    master.resize((512, 512), Image.LANCZOS).save(PNG_PREVIEW, format="PNG")
    print(f"[OK] wrote {OUT_FILE} ({', '.join(f'{n}x{n}' for n in SIZES)})")
    print(f"[OK] wrote {PNG_PREVIEW} (512x512 preview)")


if __name__ == "__main__":
    main()
