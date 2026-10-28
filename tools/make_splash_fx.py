"""Map the Project Moon Pi badge for the animated start-up splash (web/splashfx.js).

Ported from the M.O.S.S. dash (bobcat-dash, same author, MIT). It finds the red swoosh (the path the lens flare
runs along, ending at its tip), the stars (to twinkle), the lander's engine flames (to flicker) and the white
rings and lettering (for the metal sheen), and writes, next to the picture:

  <name>.fx.json   the flare path, the stars and the flame centres, in the picture's own pixels
  <name>.fx-sheen.png, <name>.fx-flame.png   masks (white where it applies): the sheen areas, the flames

Run it after changing the logo (needs numpy, scipy, Pillow); the web page only reads the files it writes.
With --check it also saves <name>.fx-check.png showing what it found.

  python3 tools/make_splash_fx.py src/train_tracker/web/img/moon-pi-logo.png --check
"""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def badge(white):
    """Centre and outer radius of the badge, from the extent of its white outer ring."""
    ys, xs = np.nonzero(white)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    return cx, cy, (xs.max() - xs.min() + ys.max() - ys.min()) / 4


def analyse(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    H, W, _ = a.shape
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mn, mx = a.min(2), a.max(2)
    white = (mn > 185) & (mx - mn < 45)
    red = (r > 160) & (g < 90) & (b < 90)

    # the outer ring (cut into arcs where the swoosh crosses it) is the outline of the big white shapes:
    # it gives the badge's centre and size
    lab, n = ndi.label(white)
    sizes = ndi.sum(white, lab, range(1, n + 1))
    ring = np.isin(lab, 1 + np.nonzero(sizes > 0.002 * W * H)[0])
    cx, cy, R = badge(ring)
    yy, xx = np.mgrid[:H, :W]
    rad = np.hypot(xx - cx, yy - cy) / R

    # inner white ring: the strongest band of white between 0.5 R and 0.85 R
    prof = [(white & (rad >= k) & (rad < k + 0.01)).sum() / max(1, ((rad >= k) & (rad < k + 0.01)).sum())
            for k in np.arange(0.5, 0.85, 0.01)]
    inner = 0.5 + 0.01 * int(np.argmax(prof))

    # red: the long shapes are the swoosh, the compact ones the MOON lettering
    lab, n = ndi.label(red)
    swoosh = np.zeros_like(red)
    letters = np.zeros_like(red)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        part = lab == i
        if part.sum() < 0.002 * R * R:
            continue
        width = (sl[1].stop - sl[1].start) / R
        (swoosh if width > 0.45 else letters)[part] = True

    # the flare's path: the main (biggest) swoosh strand's centre line, from its far left end to the tip
    lab, n = ndi.label(swoosh)
    main = lab == (np.argmax(ndi.sum(swoosh, lab, range(1, n + 1))) + 1)
    ys, xs = np.nonzero(main)
    path = []
    for x in range(xs.min(), xs.max() + 1, max(1, int(R / 40))):
        col = ys[xs == x]
        if len(col):
            path.append([int(x), float(np.median(col))])
    tip = (int(xs.max()), int(ys[xs == xs.max()].min()))
    path.append([tip[0], float(tip[1])])

    # stars: small bright spots in the blue ring and the sky, away from the white rings and the lettering
    bright = (mn > 200)
    lab, n = ndi.label(bright)
    stars = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        part = lab[sl] == i
        area = int(part.sum())
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        y, x = ndi.center_of_mass(part)
        x, y = x + sl[1].start, y + sl[0].start
        rr = np.hypot(x - cx, y - cy) / R
        if not (1 <= area <= 0.004 * R * R) or max(h, w) > 0.09 * R or max(h, w) > 3.5 * min(h, w):
            continue
        in_blue = inner + 0.03 < rr < 0.95
        if not in_blue:
            continue
        if y < cy - 0.62 * R and abs(x - cx) < 0.45 * R:            # the 'project' lettering
            continue
        stars.append([round(x, 1), round(y, 1), round(float(np.sqrt(area)), 2)])

    # flames: the bright blue-white plumes under the lander (centre of the badge, just above the lunar surface)
    zone = (np.abs(xx - cx) < 0.33 * R) & (yy > cy + 0.22 * R) & (yy < cy + 0.48 * R) & (rad < inner)
    flame = zone & (b > 190) & (b >= r + 5) & (g > 140)
    # the jets: peaks in how much flame each column has, at least 0.1 R apart
    cols = ndi.uniform_filter1d(flame.sum(0).astype(float), max(3, int(R / 30)))
    jets = []
    for x in np.argsort(cols)[::-1]:
        if cols[x] < 0.35 * cols.max() or len(jets) == 5:
            break
        if all(abs(x - j[0]) > 0.1 * R for j in jets):
            ys = np.nonzero(flame[:, x])[0]
            jets.append([int(x), round(float(ys.mean()), 1), round(float(cols[x]), 1)])
    jets.sort()

    # sheen: the white rings and white lettering (not the clouds or the moon inside), and the red lettering
    sheen = (white & (rad >= inner - 0.02) & (rad < 1.03)) | letters
    for x, y, s in stars:                                          # leave the stars to twinkle on their own
        sheen[int(max(0, y - 2 * s)):int(y + 2 * s), int(max(0, x - 2 * s)):int(x + 2 * s)] = False
    sheen = ndi.binary_dilation(sheen, iterations=1)

    def box(m):                                                    # [x, y, w, h] around a mask, 2 px spare
        ys, xs = np.nonzero(m)
        x0, y0 = max(0, xs.min() - 2), max(0, ys.min() - 2)
        return [int(x0), int(y0), int(min(W, xs.max() + 3) - x0), int(min(H, ys.max() + 3) - y0)]

    return {"size": [W, H], "centre": [round(cx, 1), round(cy, 1)], "radius": round(R, 1), "inner": round(inner, 3),
            "path": path, "tip": list(tip), "stars": stars, "jets": jets,
            "sheen_box": box(sheen), "flame_box": box(flame)}, sheen, flame


def main(paths, check=False):
    for path in paths:
        fx, sheen, flame = analyse(path)
        base = os.path.splitext(path)[0]
        with open(base + ".fx.json", "w") as f:
            json.dump(fx, f, separators=(",", ":"))
        Image.fromarray((sheen * 255).astype(np.uint8)).save(base + ".fx-sheen.png", optimize=True)
        soft = ndi.gaussian_filter(flame.astype(float), 1.0).clip(0, 1) * 255
        Image.fromarray(soft.astype(np.uint8)).save(base + ".fx-flame.png", optimize=True)
        print(f"{path}: badge r {fx['radius']}, {len(fx['path'])} path points, tip {fx['tip']}, "
              f"{len(fx['stars'])} stars, {len(fx['jets'])} flames")
        if check:
            from PIL import ImageDraw                              # noqa: E402
            im = Image.open(path).convert("RGB")
            ov = np.asarray(im).copy()
            ov[sheen] = (ov[sheen] * 0.3 + np.array([255, 200, 0]) * 0.7).astype(np.uint8)
            ov[flame] = (0, 255, 0)
            im = Image.fromarray(ov)
            d = ImageDraw.Draw(im)
            d.line([tuple(p) for p in fx["path"]], fill=(0, 255, 255), width=3)
            for x, y, s in fx["stars"]:
                d.ellipse((x - 6, y - 6, x + 6, y + 6), outline=(255, 0, 255), width=2)
            for x, y, _ in fx["jets"]:
                d.ellipse((x - 8, y - 8, x + 8, y + 8), outline=(0, 255, 0), width=2)
            tx, ty = fx["tip"]
            d.ellipse((tx - 10, ty - 10, tx + 10, ty + 10), outline=(255, 255, 255), width=3)
            im.save(base + ".fx-check.png")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args, check="--check" in sys.argv)
