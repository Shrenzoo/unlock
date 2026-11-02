"""Composite the six-fixture gallery and the T01 clip, and encode theme-matched GIFs.

usage: UNLOCK_FONT_DIR=<fonts> python compose_cells.py
Outcome labels are checked against the recorded gallery release before drawing.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cell_timeline import CELL_FPS, CELL_FRAMES, cell_state
from compose import pinned_palette, stabilize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILD = HERE / ".build"
FONTS = Path(os.environ["UNLOCK_FONT_DIR"])
OUT = HERE.parent

THEMES = dict(
    light=dict(
        bg="#ffffff", ink="#161a20", ink2="#4b5360", ink3="#667080", rule="#e1e6ee",
        verified="#2a6e57", signal="#b8461c", neutral="#2253d6",
    ),
    dark=dict(
        bg="#0d1117", ink="#e6edf3", ink2="#b1bac4", ink3="#8b949e", rule="#21262d",
        verified="#57c09c", signal="#f0916a", neutral="#7ea3ff",
    ),
)

CELLS = [
    ("B02", "Trapped service part", "Verified improvement", "verified", "T01 relief"),
    ("B04", "Pump under a crossbar", "Verified improvement", "verified", "T01 relief, second size"),
    ("B05", "Battery under a strap", "Verified improvement", "verified", "T02 move, nothing cut"),
    ("B06", "Sensor under a light bracket", "Verified improvement", "verified", "T01, within a cut budget"),
    ("B07", "Hatch screw behind a shield", "Incomplete analysis", "signal", "Driver blocked. No claim"),
    ("B08", "Filter, already serviceable", "No supported candidate", "neutral", "Route exists. No edit"),
]
RECORDED = dict(
    B02="VERIFIED_IMPROVEMENT_FOUND",
    B04="VERIFIED_IMPROVEMENT_FOUND",
    B05="VERIFIED_IMPROVEMENT_FOUND",
    B06="VERIFIED_IMPROVEMENT_FOUND",
    B07="INCOMPLETE_ANALYSIS",
    B08="NO_SUPPORTED_CANDIDATE",
)


def check_outcomes():
    release = json.loads(
        (ROOT / "backend/evidence/gallery-release-lighter/validation.json").read_text()
    )
    jobs = release["private_engineering"]["jobs"]
    for code, outcome in RECORDED.items():
        assert jobs[code]["outcome"] == outcome, code


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def render_for(code, tag, frame):
    state_key = {}
    for f in range(frame + 1):
        s = json.dumps(cell_state(code, f), sort_keys=True)
        state_key.setdefault(s, f)
    first = state_key[json.dumps(cell_state(code, frame), sort_keys=True)]
    return BUILD / f"{tag}_{code}" / f"f{first:04d}.png"


def encode(directory, theme, dest, fps=CELL_FPS, colors=256):
    frames = sorted(directory.glob("c*.png"))
    stabilize(frames)
    entries = []
    last = None
    for path in frames:
        data = path.read_bytes()
        if data == last:
            entries[-1][1] += 1
        else:
            entries.append([path, 1])
            last = data
    entries[-1][1] += int(fps * 1.6)  # Rest on the result before looping.
    listing = directory / "list.txt"
    listing.write_text(
        "".join(f"file '{p.name}'\nduration {n / fps}\n" for p, n in entries)
        + f"file '{entries[-1][0].name}'\n"
    )
    tones = [v for k, v in THEMES[theme].items() if k not in ("bg", "rule")]
    palette = pinned_palette(directory, listing, THEMES[theme]["bg"], colors, extra=tones)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-i", str(palette), "-filter_complex", "[0:v][1:v]paletteuse=dither=none:diff_mode=rectangle",
         "-loop", "0", "-fps_mode", "passthrough", str(dest)],
        check=True,
    )
    return len(entries), dest.stat().st_size


def shape_only(image):
    """Drop the shadow's faintest tail, which would outline the frame on the page."""
    pixels = np.array(image)
    pixels[pixels[..., 3] < 10, 3] = 0
    return Image.fromarray(pixels)


def poster(canvas, directory, dest):
    """The final frame on the GIF's own palette, so colours match the animation."""
    palette = Image.open(directory / "palette.png").convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    canvas.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE).save(dest, optimize=True)


def gallery(theme):
    c = THEMES[theme]
    cell_w, cell_h = 330, 206
    label_h = 64
    gap = 5
    width = cell_w * 3 + gap * 2
    height = (cell_h + label_h) * 2 + 14
    bold = font("InstrumentSans-600.ttf", 15)
    small = font("InstrumentSans-400.ttf", 12)
    mono = font("IBMPlexMono-500.ttf", 13)
    out = BUILD / f"gallery_{theme}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    for frame in range(CELL_FRAMES):
        canvas = Image.new("RGBA", (width, height), c["bg"])
        draw = ImageDraw.Draw(canvas)
        for i, (code, name, outcome, tone, detail) in enumerate(CELLS):
            x = (i % 3) * (cell_w + gap)
            y = (i // 3) * (cell_h + label_h + 14)
            im = Image.open(render_for(code, "cell", frame)).convert("RGBA").resize((cell_w, cell_h), Image.LANCZOS)
            canvas.alpha_composite(shape_only(im), (x, y))
            baseline = y + cell_h + 18
            draw.text((x + 8, baseline), code, font=mono, fill=c["ink3"], anchor="ls")
            draw.text((x + 40, baseline), name, font=small, fill=c["ink2"], anchor="ls")
            draw.text((x + 8, baseline + 20), outcome, font=bold, fill=c[tone], anchor="ls")
            draw.text((x + 8, baseline + 37), detail, font=small, fill=c["ink3"], anchor="ls")
        canvas.convert("RGB").save(out / f"c{frame:04d}.png")
    print(theme, "gallery", encode(out, theme, OUT / f"gallery-{theme}.gif"))
    poster(canvas, out, OUT / f"gallery-poster-{theme}.png")


def relief(theme):
    c = THEMES[theme]
    width, height = 780, 485
    out = BUILD / f"relief_{theme}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    mono = font("IBMPlexMono-400.ttf", 14)
    head = font("InstrumentSans-600.ttf", 22)
    # Numbers come from the live run's record, asserted against the export.
    scene = json.loads((BUILD / "B02.json").read_text())
    assert scene["design"]["removed_mm3"] == 2560.0 and scene["design"]["matches_live_run"]
    assert scene["design"]["parameters"]["width_mm"] == 40.0
    assert scene["design"]["parameters"]["depth_mm"] == 16.0
    captions = [
        (0, 14, "The original bracket", "B02, no supported route"),
        (14, 34, "T01 relief, 40 × 16 mm", "2,560 mm³ removed, 0 mm³ outside the editable web"),
        (34, CELL_FRAMES, "The part lifts through it", "target TRANSLATE Z+ 80 mm, reverse passed"),
    ]
    for frame in range(CELL_FRAMES):
        canvas = Image.new("RGBA", (width, height), c["bg"])
        im = Image.open(render_for("B02", "relief", frame)).convert("RGBA").resize((width, height), Image.LANCZOS)
        canvas.alpha_composite(shape_only(im))
        draw = ImageDraw.Draw(canvas)
        for start, end, title, data in captions:
            if start <= frame < end:
                draw.text((22, 42), title, font=head, fill=c["ink"], anchor="ls")
                draw.text((22, 66), data, font=mono, fill=c["ink2"], anchor="ls")
        canvas.convert("RGB").save(out / f"c{frame:04d}.png")
    print(theme, "relief", encode(out, theme, OUT / f"relief-{theme}.gif"))
    poster(canvas, out, OUT / f"relief-poster-{theme}.png")


def main():
    check_outcomes()
    for theme in THEMES:
        gallery(theme)
        relief(theme)


if __name__ == "__main__":
    main()
