"""Generate the static image assets (icons, grain, paper texture, social image).

    python scripts/generate_assets.py

Re-run after changing colours. Output goes to static/icons and static/images.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "static" / "icons"
IMAGES = ROOT / "static" / "images"
BG = (8, 8, 8)
ACCENT = (217, 79, 112)
GOLD = (201, 169, 110)
TEXT = (245, 241, 234)

# The heart used everywhere (same path as the SVG icon, 24x24 viewbox).
HEART_SVG = (
    "M12 20.5s-7.5-4.6-9.3-9.2C1.5 8.1 3.6 4.5 7.1 4.5c2 0 3.6 1.1 4.9 2.9 "
    "1.3-1.8 2.9-2.9 4.9-2.9 3.5 0 5.6 3.6 4.4 6.8-1.8 4.6-9.3 9.2-9.3 9.2z"
)


def heart_polygon(cx: float, cy: float, size: float, steps: int = 400) -> list[tuple[float, float]]:
    """Classic parametric heart, scaled to `size` (width) and centred on (cx, cy)."""
    import math

    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((x, y))
    scale = size / 34.0
    return [(cx + x * scale, cy + (y + 1.5) * scale) for x, y in pts]


def icon(size: int, padding: float, rounded: bool) -> Image.Image:
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), BG + (255,))
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((s * 0.15, s * 0.15, s * 0.85, s * 0.85), fill=ACCENT + (70,))
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.12))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    heart_w = s * (1 - 2 * padding)
    d.polygon(heart_polygon(s / 2, s / 2, heart_w), fill=ACCENT + (255,))
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    if rounded:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.22), fill=255)
        img.putalpha(mask)
    return img


def grain(size: int = 180) -> Image.Image:
    rnd = random.Random(7)
    img = Image.new("L", (size, size))
    img.putdata([rnd.randint(0, 255) for _ in range(size * size)])
    return Image.merge("RGBA", (img, img, img, Image.new("L", (size, size), 255)))


def paper(size: int = 300) -> Image.Image:
    rnd = random.Random(11)
    base = Image.new("RGB", (size, size), (243, 236, 223))
    noise = Image.new("L", (size, size))
    noise.putdata([rnd.randint(110, 150) for _ in range(size * size)])
    noise = noise.filter(ImageFilter.GaussianBlur(0.7))
    fibres = ImageDraw.Draw(noise)
    for _ in range(90):
        x, y = rnd.randint(0, size), rnd.randint(0, size)
        fibres.line((x, y, x + rnd.randint(-14, 14), y + rnd.randint(-3, 3)), fill=rnd.randint(100, 118), width=1)
    tinted = Image.merge("RGB", (noise, noise, noise))
    return Image.blend(base, tinted, 0.07)


def og_image() -> Image.Image:
    w, h = 1200, 630
    img = Image.new("RGBA", (w, h), BG + (255,))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-200, -250, 600, 450), fill=ACCENT + (60,))
    gd.ellipse((700, 250, 1400, 900), fill=GOLD + (45,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
    d = ImageDraw.Draw(img)
    d.polygon(heart_polygon(w / 2, 200, 70), fill=ACCENT + (255,))
    font = None
    for name in ("georgia.ttf", "Georgia.ttf", "DejaVuSerif.ttf", "times.ttf"):
        try:
            font = ImageFont.truetype(name, 110)
            small = ImageFont.truetype(name, 34)
            break
        except OSError:
            continue
    if font is None:
        font = small = ImageFont.load_default()
    title = "OUR LOVE"
    tw = d.textlength(title, font=font)
    d.text(((w - tw) / 2, 290), title, font=font, fill=TEXT)
    sub = "Every moment has a story."
    sw = d.textlength(sub, font=small)
    d.text(((w - sw) / 2, 440), sub, font=small, fill=(154, 149, 144))
    return img.convert("RGB")


def logo_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<rect width="24" height="24" rx="5" fill="#080808"/>'
        f'<path d="{HEART_SVG}" fill="#D94F70" transform="translate(2.4 2.2) scale(0.8)"/></svg>\n'
    )


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    icon(192, 0.2, False).save(ICONS / "icon-192.png", optimize=True)
    icon(512, 0.2, False).save(ICONS / "icon-512.png", optimize=True)
    icon(512, 0.3, False).save(ICONS / "maskable-512.png", optimize=True)  # safe zone for masks
    icon(180, 0.2, False).convert("RGB").save(ICONS / "apple-touch-icon.png", optimize=True)
    (ICONS / "logo.svg").write_text(logo_svg(), encoding="utf-8")
    grain().save(IMAGES / "grain.png", optimize=True)
    paper().save(IMAGES / "paper.png", optimize=True)
    og_image().save(IMAGES / "og.png", optimize=True)
    print("Assets written to", ICONS, "and", IMAGES)


if __name__ == "__main__":
    main()
