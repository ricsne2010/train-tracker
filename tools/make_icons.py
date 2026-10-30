#!/usr/bin/env python3
"""Draw the installer's app icons: a locomotive coming down the tracks at night, headlights on, with the
Project Moon Pi patch in the corner. Start gets a green ▶ badge, Stop a red ■; Uninstall has no badge.

Writes installer/icons/{start,stop,app}.icns (macOS), .ico (Windows) and -256.png (previews). Needs Pillow.

  python3 tools/make_icons.py
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "installer" / "icons"
PATCH = ROOT / "src" / "train_tracker" / "web" / "img" / "moon-pi-logo.png"
K = 4                          # drawn 4x, then shrunk, for smooth edges
N = 1024 * K
ORANGE, ORANGE_DARK = (255, 106, 19), (206, 78, 6)


def P(*v):
    return [round(x * K) for x in v]


def rounded_patch():
    """The Moon Pi patch cropped to its round edge (the file is the patch on a black square)."""
    src = Image.open(PATCH).convert("RGB")
    box = src.convert("L").point(lambda v: 255 if v > 40 else 0).getbbox()
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    r = max(box[2] - box[0], box[3] - box[1]) / 2
    im = src.crop((round(cx - r), round(cy - r), round(cx + r), round(cy + r))).convert("RGBA")
    mask = Image.new("L", (im.width * 4, im.height * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, mask.width - 1, mask.height - 1), fill=255)
    im.putalpha(mask.resize(im.size, Image.LANCZOS))
    return im


def scene():
    """The rounded-square icon without a badge."""
    sky = Image.new("RGBA", (N, N))
    d = ImageDraw.Draw(sky)
    top, bottom = (28, 52, 104), (6, 12, 28)
    for y in range(N):
        t = y / N
        d.line([(0, y), (N, y)], fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    rnd = random.Random(4)
    for _ in range(40):                                        # stars
        x, y, r = rnd.uniform(300, 980), rnd.uniform(70, 330), rnd.uniform(2, 5)
        d.ellipse(P(x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randint(120, 230)))
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle(P(64, 64, 960, 960), radius=200 * K, fill=255)
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    im.paste(sky, (0, 0), mask)
    d = ImageDraw.Draw(im)

    cx, foot = 460, 690                                        # the train's centre line and where it meets the rails
    # ballast and ties widening towards the viewer
    d.polygon([tuple(P(cx - 175, foot)), tuple(P(cx + 175, foot)), tuple(P(cx + 520, 1000)), tuple(P(cx - 520, 1000))],
              fill=(66, 58, 50))
    for i in range(7):
        t = (i + 0.6) / 7
        y = foot + (1000 - foot) * t ** 1.3
        half = 150 + 330 * t ** 1.3
        h = 7 + 16 * t
        d.rectangle(P(cx - half, y - h / 2, cx + half, y + h / 2), fill=(118, 90, 64))
    for s in (-1, 1):                                          # rails
        d.line([tuple(P(cx + s * 100, foot)), tuple(P(cx + s * 300, 1000))], fill=(206, 212, 220), width=11 * K)

    # headlight glow on the track ahead
    glow = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon([tuple(P(cx - 140, foot - 40)), tuple(P(cx + 140, foot - 40)),
                                  tuple(P(cx + 380, 1000)), tuple(P(cx - 380, 1000))], fill=(255, 236, 170, 70))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40 * K)))
    d = ImageDraw.Draw(im)

    # the locomotive, head on
    l, r, roof = cx - 190, cx + 190, 300
    d.polygon([tuple(P(*p)) for p in [(l + 50, roof), (r - 50, roof), (r, roof + 80), (r, foot - 30),
                                       (l, foot - 30), (l, roof + 80)]], fill=ORANGE)
    d.rounded_rectangle(P(l, foot - 150, r, foot - 30), radius=8 * K, fill=ORANGE_DARK)        # lower nose
    d.polygon([tuple(P(*p)) for p in [(l + 64, roof + 30), (r - 64, roof + 30), (r - 26, roof + 96),
                                       (r - 26, roof + 190), (l + 26, roof + 190), (l + 26, roof + 96)]],
              fill=(14, 22, 40))                                                              # windshield
    d.line([tuple(P(cx, roof + 32)), tuple(P(cx, roof + 190))], fill=ORANGE, width=12 * K)     # centre post
    d.polygon([tuple(P(*p)) for p in [(l + 78, roof + 44), (l + 140, roof + 44), (l + 74, roof + 172),
                                       (l + 40, roof + 172), (l + 40, roof + 104)]], fill=(64, 90, 130))   # glare
    d.rectangle(P(l, foot - 186, r, foot - 162), fill=(245, 245, 245))                         # stripe
    d.rectangle(P(l + 20, foot - 30, r - 20, foot), fill=(36, 36, 42))                         # pilot
    lights = [(l + 70, foot - 90, 30), (r - 70, foot - 90, 30), (cx, roof + 14, 18)]
    for x, y, rad in lights:
        g = Image.new("RGBA", (N, N), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse(P(x - rad * 2.6, y - rad * 2.6, x + rad * 2.6, y + rad * 2.6), fill=(255, 240, 180, 170))
        im.alpha_composite(g.filter(ImageFilter.GaussianBlur(26 * K)))
    d = ImageDraw.Draw(im)
    for x, y, rad in lights:
        d.ellipse(P(x - rad, y - rad, x + rad, y + rad), fill=(255, 252, 232))

    patch = rounded_patch().resize((180 * K, 180 * K), Image.LANCZOS)
    im.alpha_composite(patch, (100 * K, 100 * K))
    # keep everything inside the rounded square
    im.putalpha(Image.composite(im.getchannel("A"), Image.new("L", (N, N), 0), mask))
    return im


def badge(im, kind):
    im = im.copy()
    d = ImageDraw.Draw(im)
    cx, cy, r = 790, 790, 150
    d.ellipse(P(cx - r - 16, cy - r - 16, cx + r + 16, cy + r + 16), fill=(255, 255, 255))
    d.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill=(34, 197, 94) if kind == "start" else (220, 38, 38))
    if kind == "start":
        d.polygon([tuple(P(cx - 48, cy - 80)), tuple(P(cx - 48, cy + 80)), tuple(P(cx + 86, cy))], fill="white")
    else:
        d.rounded_rectangle(P(cx - 64, cy - 64, cx + 64, cy + 64), radius=12 * K, fill="white")
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = scene()
    for name, im in (("start", badge(base, "start")), ("stop", badge(base, "stop")), ("app", base)):
        im = im.resize((1024, 1024), Image.LANCZOS)
        im.save(OUT / f"{name}.icns")
        im.save(OUT / f"{name}.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        im.resize((256, 256), Image.LANCZOS).save(OUT / f"{name}-256.png")
        print(f"wrote installer/icons/{name}.icns, .ico, -256.png")


if __name__ == "__main__":
    main()
