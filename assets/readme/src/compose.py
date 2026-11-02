"""Composite captions over rendered frames and encode a theme-matched GIF.

usage: UNLOCK_FONT_DIR=<fonts> python compose.py [--themes light,dark] [--width 1000]
Numbers in captions are checked against evidence and exported geometry first.
"""

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from timeline import BEATS, CAPTIONS, DISSOLVE_FRAMES, FPS, LAST_FRAME, ramp, state

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILD = HERE / ".build"
FONTS = Path(os.environ["UNLOCK_FONT_DIR"])
HERO = BUILD / "hero"
RAISE_PX = 14

THEMES = dict(
    light=dict(bg="#ffffff", ink="#161a20", ink2="#4b5360", tick="#2a6e57", route="#2253d6"),
    dark=dict(bg="#0d1117", ink="#e6edf3", ink2="#b1bac4", tick="#57c09c", route="#7ea3ff"),
)


def check_captions():
    """Refuse to draw a number the evidence does not support."""
    scene = json.loads((BUILD / "B05.json").read_text())
    report = json.loads((ROOT / "backend/evidence/live-b05/live_run.json").read_text())
    candidate = report["candidates"][0]
    plan = candidate["revised_plan"]
    witness = scene["witnesses"][0]
    assert report["live_model"] is True and report["model"]["model_id"] == "muse-spark-1.3"
    assert report["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
    assert scene["baseline_status"] == "no_path_supported"
    assert round(witness["overlap_mm3"]) == 1397 and witness["travel_mm"] == 12.0
    assert len(scene["components"]) == 9
    assert candidate["proposal"]["template_id"] == "T02"
    assert candidate["proposal"]["parameters"] == {"offset_y_mm": -12.0}
    assert [p["offset_y_mm"] for p in scene["allowed_positions"]] == [-12.0, 12.0, 24.0, 36.0]
    assert scene["design"]["matches_live_run"] is True
    assert len(plan["constraint_checks"]) == 12
    assert all(c["result"] == "pass" for c in plan["constraint_checks"])
    assert plan["replay"] == "passed" and plan["reverse"] == "passed"
    step = plan["steps"][0]
    assert (step["component_id"], step["axis"], step["distance_mm"]) == ("target", "Z+", 80.0)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def tracked(draw, xy, text, fnt, fill, tracking=0.0):
    """Draw text with tracking, keeping PIL's kerning between letters."""
    x, y = xy
    if not tracking:
        draw.text((x, y), text, font=fnt, fill=fill, anchor="ls")
        return
    for i, ch in enumerate(text):
        draw.text((x, y), ch, font=fnt, fill=fill, anchor="ls")
        pair = text[i : i + 2]
        x += fnt.getlength(pair) - fnt.getlength(pair[1:]) + tracking
    return x


def mix(fill, bg, alpha):
    a = tuple(int(fill[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(bg[i : i + 2], 16) for i in (1, 3, 5))
    return tuple(round(x * alpha + y * (1 - alpha)) for x, y in zip(a, b))


def caption_alphas(frame):
    out = []
    for name, start, end in BEATS:
        fade_in = 1.0 if start == 0 else ramp(frame, start, start + 5)
        fade_out = 1.0 if end == LAST_FRAME else 1 - ramp(frame, end - 3, end)
        if start <= frame < end:
            out.append((name, min(fade_in, fade_out)))
    return out


def project(point, s, width, height):
    """Pinhole camera matching render_hero.py: lens 58 mm, sensor 36 mm."""
    az, el = math.radians(s["azimuth"]), math.radians(s["elevation"])
    distance = 528.0 * s["distance"]
    focus = np.array((0.0, -2.0, 27.0))
    position = focus + distance * np.array(
        (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    )
    forward = (focus - position) / np.linalg.norm(focus - position)
    right = np.cross(forward, (0, 0, 1.0))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    v = np.array(point, float) - position
    depth = v @ forward
    scale = (58.0 / 36.0) / depth
    x = (v @ right) * scale - (-0.075)
    y = (v @ up) * scale - 0.035
    return ((x + 0.5) * width, (0.5 - y * width / height) * height)


def compose(theme, width):
    colors = THEMES[theme]
    height = round(width * 676 / 1200)
    scale = width / 1000
    headline = font("InstrumentSans-600.ttf", round(34 * scale))
    mono = font("IBMPlexMono-400.ttf", round(16 * scale))
    out = BUILD / f"hero_{theme}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    table = json.loads((HERO / "frames.json").read_text()) if (HERO / "frames.json").exists() else None
    keys = {}
    first_frame = None
    for frame in range(LAST_FRAME):
        s = state(frame)
        key = json.dumps(s, sort_keys=True)
        render = keys.setdefault(key, frame)
        path = HERO / f"f{render:04d}.png"
        if not path.exists():
            continue
        base = Image.open(path).convert("RGBA").resize((width, height), Image.LANCZOS)
        # The faintest shadow tail costs bytes on every frame and is invisible.
        pixels = np.array(base)
        pixels[pixels[..., 3] < 4, 3] = 0
        base = Image.fromarray(pixels)
        canvas = Image.new("RGBA", (width, height), colors["bg"])
        # Lift the model slightly, so the plate's near corner has a margin.
        canvas.alpha_composite(base, dest=(0, 0), source=(0, RAISE_PX))
        draw = ImageDraw.Draw(canvas)
        margin = round(36 * scale)
        for name, alpha in caption_alphas(frame):
            title, data = CAPTIONS[name]
            draw.text((margin, round(68 * scale)), title, font=headline, anchor="ls", fill=mix(colors["ink"], colors["bg"], alpha))
            draw.text((margin, round(98 * scale)), data, font=mono, anchor="ls", fill=mix(colors["ink2"], colors["bg"], alpha))
            if name == "verify":
                # One tick per recorded check.
                count = min(12, max(0, int((frame - 140) / 1.25)))
                for i in range(12):
                    x = margin + i * round(22 * scale)
                    y = round(124 * scale)
                    box = (x, y, x + round(15 * scale), y + round(4 * scale))
                    draw.rectangle(box, fill=mix(colors["tick"], colors["bg"], alpha if i < count else alpha * 0.16))
        if s["lift"] > 16:
            start = project((0, 15, 26.0), s, width, height)
            end = project((0, 15, 10.0 + s["lift"]), s, width, height)
            start = (start[0], start[1] - RAISE_PX)
            end = (end[0], end[1] - RAISE_PX)
            length = math.dist(start, end)
            dash = 7 * scale
            steps = int(length / (dash * 2))
            for i in range(steps):
                t0, t1 = i * dash * 2 / length, (i * dash * 2 + dash) / length
                a = (start[0] + (end[0] - start[0]) * t0, start[1] + (end[1] - start[1]) * t0)
                b = (start[0] + (end[0] - start[0]) * t1, start[1] + (end[1] - start[1]) * t1)
                draw.line((a, b), fill=colors["route"], width=max(1, round(1.6 * scale)))
        rgb = canvas.convert("RGB")
        if frame == 0:
            first_frame = rgb
        if first_frame is not None and frame >= LAST_FRAME - DISSOLVE_FRAMES:
            t = ramp(frame, LAST_FRAME - DISSOLVE_FRAMES, LAST_FRAME - 1)
            rgb = Image.blend(rgb, first_frame, t)
        rgb.save(out / f"c{frame:04d}.png")
    return out, height


def stabilize(frames, threshold=5, refresh_every=8):
    """Hold pixels that barely changed, so render noise doesn't cost GIF bytes.

    A periodic stricter pass settles what was held, so fades leave no residue.
    """
    previous = None
    for i, path in enumerate(frames):
        current = np.array(Image.open(path).convert("RGB")).astype(np.int16)
        if previous is not None:
            limit = 2 if i % refresh_every == 0 else threshold
            still = np.abs(current - previous).max(axis=2) < limit
            current[still] = previous[still]
            Image.fromarray(current.astype(np.uint8)).save(path)
        previous = current


def pinned_palette(out, listing, background, colors, ramp_steps=24, extra=()):
    """A palette with the exact page colour and a fine ramp for soft shadows.

    Without dithering, the shadows would otherwise fall into a few visible bands.
    """
    palette = out / "palette.png"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-vf", f"palettegen=max_colors={colors - ramp_steps - 1 - len(extra)}:stats_mode=full:reserve_transparent=0", str(palette)],
        check=True,
    )
    entries = np.array(Image.open(palette).convert("RGB")).reshape(-1, 3).astype(int)
    want = np.array([int(background[i : i + 2], 16) for i in (1, 3, 5)])
    ramp = [want * (1 - 0.32 * step / ramp_steps) for step in range(ramp_steps + 1)]
    tones = [[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in extra]
    merged = np.vstack([entries, np.round(ramp).astype(int), np.array(tones, int).reshape(-1, 3)])
    merged = np.unique(merged, axis=0)
    padded = np.vstack([merged, np.repeat(want[None, :], 256 - len(merged), axis=0)])
    Image.fromarray(padded.reshape(16, 16, 3).astype(np.uint8)).save(palette)
    return palette


def encode(out, theme, dest, colors=256, dither="none"):
    frames = sorted(out.glob("c*.png"))
    stabilize(frames)
    listing = out / "list.txt"
    # Identical neighbours collapse into one GIF frame with a longer delay.
    entries = []
    last = None
    for path in frames:
        data = path.read_bytes()
        if data == last:
            entries[-1][1] += 1
        else:
            entries.append([path, 1])
            last = data
    listing.write_text(
        "".join(f"file '{p.name}'\nduration {n / FPS}\n" for p, n in entries)
        + f"file '{entries[-1][0].name}'\n"
    )
    palette = pinned_palette(out, listing, THEMES[theme]["bg"], colors)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-i", str(palette), "-filter_complex", f"[0:v][1:v]paletteuse=dither={dither}:diff_mode=rectangle",
         "-loop", "0", "-fps_mode", "passthrough", str(dest)],
        check=True,
    )
    return len(entries), dest.stat().st_size


def check_projection(width, height):
    """The route overlay must land on the same pixels as Blender's own camera."""
    table = json.loads((HERO / "frames.json").read_text())
    for row in table[::40]:
        s = state(row["frame"])
        for name, point in (("route_start", (0.0, 15.0, 26.0)), ("route_end", (0.0, 15.0, 106.0))):
            x, y = project(point, s, width, height)
            ax, ay = row["anchors"][name]
            assert abs(x - ax * width) < 1.5 and abs(y - ay * height) < 1.5, (name, x, ax * width, y, ay * height)


SEQUENCE = [
    (20, "Original", "Pack seated under a", "fixed strap"),
    (60, "Obstruction", "no_path_supported:", "overlap after a 12 mm lift"),
    (135, "Modification", "T02: the strap's web", "moves −12 mm"),
    (160, "Verification", "Rebuilt, checked,", "replayed, reversed"),
    (203, "Export", "Route Z+ 80 mm, STEP", "reimported, rechecked"),
]


def sequence(theme):
    colors = THEMES[theme]
    panel_w, panel_h = 300, 230
    gap = 12
    width = panel_w * 5 + gap * 4
    label = 92
    canvas = Image.new("RGB", (width, panel_h + label), colors["bg"])
    draw = ImageDraw.Draw(canvas)
    title = font("InstrumentSans-600.ttf", 22)
    body = font("InstrumentSans-400.ttf", 17)
    keys = {}
    for frame in range(LAST_FRAME):
        keys.setdefault(json.dumps(state(frame), sort_keys=True), frame)
    for i, (frame, name, line1, line2) in enumerate(SEQUENCE):
        path = HERO / f"f{keys[json.dumps(state(frame), sort_keys=True)]:04d}.png"
        im = Image.open(path).convert("RGBA")
        w, h = im.size
        # Same framing in every panel: the model, with room for the lift.
        box = (int(w * 0.235), int(h * 0.14), int(w * 0.95), int(h * 0.14) + int(w * 0.715 * panel_h / panel_w))
        crop = im.crop(box).resize((panel_w, panel_h), Image.LANCZOS)
        cell = Image.new("RGBA", (panel_w, panel_h), colors["bg"])
        cell.alpha_composite(crop)
        x = i * (panel_w + gap)
        canvas.paste(cell.convert("RGB"), (x, 0))
        draw.text((x + 6, panel_h + 26), f"{i + 1}  {name}", font=title, fill=colors["ink"], anchor="ls")
        draw.text((x + 6, panel_h + 54), line1, font=body, fill=colors["ink2"], anchor="ls")
        draw.text((x + 6, panel_h + 77), line2, font=body, fill=colors["ink2"], anchor="ls")
    dest = HERE.parent / f"sequence-{theme}.png"
    canvas.quantize(colors=200, dither=Image.Dither.NONE).save(dest, optimize=True)
    print(dest.name, dest.stat().st_size)


def main():
    themes = ["light", "dark"]
    width = 1000
    dest_dir = HERE.parent
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--themes":
            themes = args[i + 1].split(",")
        if a == "--width":
            width = int(args[i + 1])
        if a == "--dest":
            dest_dir = Path(args[i + 1])
    check_captions()
    check_projection(width, round(width * 676 / 1200))
    for theme in themes:
        out, _ = compose(theme, width)
        n, size = encode(out, theme, dest_dir / f"hero-{theme}.gif")
        print(theme, "gif frames", n, "bytes", size)
        last = sorted(out.glob("c*.png"))[-DISSOLVE_FRAMES - 1]
        poster = dest_dir / f"hero-poster-{theme}.png"
        Image.open(last).convert("RGB").quantize(colors=200, dither=Image.Dither.NONE).save(poster, optimize=True)
        print(poster.name, poster.stat().st_size)
        sequence(theme)


if __name__ == "__main__":
    main()
