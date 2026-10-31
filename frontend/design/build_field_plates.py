"""Erase the UI from the reference mockup and write grain-free background plates.

    python3 design/build_field_plates.py design/field-reference.webp src/landing

Needs numpy, scipy and Pillow. Writes field-hero.webp (rows above the hero/story seam)
and field-story.webp (rows below it), which lightField.ts paints behind the landing page.
Interface elements are masked by hand-measured rectangles and polygons, filled by
Poisson blending in Oklab, and the baked-in grain is blurred away (CSS adds it back).
"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage, sparse
from scipy.sparse.linalg import splu

SRC, OUT = sys.argv[1], sys.argv[2]
SPLIT = 532
img = np.asarray(Image.open(SRC).convert('RGB'), dtype=np.float64) / 255.0
H, W, _ = img.shape

mask = Image.new('L', (W, H), 0)          # 255 = erase
d = ImageDraw.Draw(mask)
rects = [
    # hero
    (36, 14, 142, 44), (898, 14, 1168, 44), (1674, 14, 1742, 44),
    (42, 156, 348, 338), (42, 348, 314, 402), (44, 415, 370, 461),
    (842, 84, 946, 122), (736, 326, 910, 364), (1281, 326, 1430, 364),
    (1481, 339, 1739, 492),
    # story
    (36, 544, 142, 572), (898, 544, 1168, 572), (1674, 544, 1742, 572),
    (38, 622, 72, 645), (38, 650, 335, 728), (38, 731, 430, 812), (38, 822, 362, 845),
    (1608, 654, 1745, 822),
]
for r in rects:
    d.rectangle(r, fill=255)
# exploded module, its screws and callout leaders
objects = Image.new('L', (W, H), 0)
od = ImageDraw.Draw(objects)
od.polygon([(893, 132), (932, 132), (937, 176), (1093, 122), (1093, 64), (1127, 64), (1130, 117),
           (1424, 126), (1462, 126), (1470, 192), (1463, 205), (1462, 300), (1466, 436),
           (1466, 531), (896, 531), (896, 430), (898, 292), (890, 200)], fill=255)
for line in [[(948, 86), (948, 126), (1014, 163)], [(915, 333), (915, 378), (1112, 385)], [(1278, 331), (1278, 367), (1234, 393)]]:
    d.line(line, fill=255, width=9)
for x, y in ((1010, 159), (1108, 384), (1236, 391)):
    d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=255)
# product in the story
od.polygon([(878, 644), (1040, 603), (1338, 650), (1340, 887), (876, 887)], fill=255)
mask = mask.filter(ImageFilter.MaxFilter(7))
objects = objects.filter(ImageFilter.MaxFilter(11))
text_hole = np.asarray(mask) > 127
obj_hole = np.asarray(objects) > 127
# fixed sample columns either side of each object (outside its bounding box)
COLUMNS = {'hero': (872, 1479), 'story': (866, 1347)}  # rows above / below the split

def fill(region_img, region_hole):
    """Push-pull: average known pixels down a pyramid, then pull smooth values back into holes."""
    w = (~region_hole).astype(np.float64)
    c = region_img * w[..., None]
    levels = []
    while min(w.shape) > 2:
        levels.append((c, w))
        c = ndimage.gaussian_filter(c, (1, 1, 0))[::2, ::2] * 4
        w = ndimage.gaussian_filter(w, 1)[::2, ::2] * 4
    col = c / np.maximum(w, 1e-6)[..., None]
    for c_f, w_f in reversed(levels):
        zy, zx = c_f.shape[0] / col.shape[0], c_f.shape[1] / col.shape[1]
        up = ndimage.zoom(col, (zy, zx, 1), order=1)[:c_f.shape[0], :c_f.shape[1]]
        a = np.clip(w_f, 0, 1)[..., None]
        col = c_f / np.maximum(w_f, 1e-6)[..., None] * a + up * (1 - a)
    out = region_img.copy()
    out[region_hole] = col[region_hole]
    return out

def columnguess(region_img, xl, xr, band=6, sag=0.0):
    """A guide image: the vertical profiles of two columns, blended across x.
    sag bends the blend downward in the middle, so a band crossing the gap follows an arc."""
    h, w, _ = region_img.shape
    left = ndimage.gaussian_filter1d(region_img[:, xl - band:xl].mean(1), 3, axis=0)
    right = ndimage.gaussian_filter1d(region_img[:, xr:xr + band].mean(1), 3, axis=0)
    t = np.clip((np.arange(w) - xl) / (xr - xl), 0, 1)
    ys = np.arange(h)[:, None] - sag * 4 * t * (1 - t)[None, :]
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    f = np.clip(ys - y0, 0, 1)[..., None]
    sample = lambda prof: prof[y0] * (1 - f) + prof[y1] * f
    return sample(left) * (1 - t[None, :, None]) + sample(right) * t[None, :, None]

def poisson(region_img, hole, guide, reach=None):
    """Guide + harmonic correction, so the fill meets the known pixels exactly at every edge.
    With reach, the correction fades with distance from the edge so it cannot tint the interior."""
    h, w, _ = region_img.shape
    ys, xs = np.nonzero(hole)
    idx = -np.ones((h, w), dtype=np.int64)
    idx[ys, xs] = np.arange(len(ys))
    resid = region_img - guide
    rows, cols, vals = [], [], []
    diag = np.zeros(len(ys))
    rhs = np.zeros((len(ys), 3))
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = ys + dy, xs + dx
        inb = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
        diag += inb
        nyc, nxc = np.clip(ny, 0, h - 1), np.clip(nx, 0, w - 1)
        nid = idx[nyc, nxc]
        inner = inb & (nid >= 0)
        rows.append(np.nonzero(inner)[0]); cols.append(nid[inner]); vals.append(-np.ones(inner.sum()))
        outer = inb & (nid < 0)
        rhs[outer] += resid[nyc[outer], nxc[outer]]
    A = sparse.csc_matrix((np.concatenate(vals + [diag]),
                           (np.concatenate(rows + [np.arange(len(ys))]), np.concatenate(cols + [np.arange(len(ys))]))),
                          shape=(len(ys), len(ys)))
    lu = splu(A)
    fade = np.exp(-ndimage.distance_transform_edt(hole)[ys, xs] / reach) if reach else 1.0
    out = region_img.copy()
    for c in range(3):
        out[ys, xs, c] = guide[ys, xs, c] + lu.solve(np.ascontiguousarray(rhs[:, c])) * fade
    return out

M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]])

def to_oklab(rgb):
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return np.cbrt(lin @ M1.T) @ M2.T

def from_oklab(lab):
    lin = (lab @ np.linalg.inv(M2).T) ** 3 @ np.linalg.inv(M1).T
    lin = np.clip(lin, 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)

def heal(image, text, obj):
    # blend in Oklab so corrections toward navy stay blue instead of turning beige
    lab = to_oklab(image)
    clean = poisson(lab, text | obj, fill(lab, text | obj))
    rows = np.arange(image.shape[0])[:, None, None]
    guide = np.where(rows < SPLIT, columnguess(clean, *COLUMNS['hero']), columnguess(clean, *COLUMNS['story'], sag=30))
    healed = from_oklab(poisson(clean, obj, guide, reach=40))
    both = text | obj
    a = np.clip(ndimage.gaussian_filter(both.astype(np.float64), 2) * 1.6, 0, 1)[..., None]
    return np.clip(healed * (1 - a) + ndimage.gaussian_filter(healed, (3, 3, 0)) * a, 0, 1)

# remove baked-in grain and webp blocking; fresh grain is added at display resolution
whole = ndimage.gaussian_filter(heal(img, text_hole, obj_hole), (1.5, 1.5, 0))
plates = {'hero': whole[:SPLIT], 'story': whole[SPLIT:]}
for name, part in plates.items():
    Image.fromarray(np.clip(part * 255 + 0.5, 0, 255).astype(np.uint8)).save(f'{OUT}/field-{name}.webp', 'WEBP', quality=95, method=6)
print('wrote', ', '.join(f'{OUT}/field-{n}.webp {p.shape[1]}x{p.shape[0]}' for n, p in plates.items()))
