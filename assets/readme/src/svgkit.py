"""A small SVG canvas that draws text as outlines, so GitHub shows the brand's type.

GitHub serves README images without web fonts. Glyphs are shaped with HarfBuzz
and stored once in <defs>, so a repeated letter costs one <use> element.
"""

import os
from html import escape
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

FONT_DIR = Path(os.environ["UNLOCK_FONT_DIR"])

FONTS = dict(
    sans="InstrumentSans-400.ttf",
    sans500="InstrumentSans-500.ttf",
    sans600="InstrumentSans-600.ttf",
    sans700="InstrumentSans-700.ttf",
    mono="IBMPlexMono-400.ttf",
    mono500="IBMPlexMono-500.ttf",
    mono600="IBMPlexMono-600.ttf",
)

# Tokens from frontend/src/styles/tokens.css, tuned per GitHub theme for contrast.
THEMES = dict(
    light=dict(
        ink="#161a20",
        ink2="#4b5360",
        ink3="#667080",
        rule="#cdd3dc",
        panel="#f4f6fa",
        panel2="#e9edf3",
        cobalt="#2253d6",
        cobalt_wash="#dde5fb",
        signal="#b8461c",
        signal_wash="#f8e1d6",
        verified="#2a6e57",
        verified_wash="#dcebe4",
        canvas="#ffffff",
    ),
    dark=dict(
        ink="#e6edf3",
        ink2="#b1bac4",
        ink3="#8b949e",
        rule="#30363d",
        panel="#161b22",
        panel2="#21262d",
        cobalt="#7ea3ff",
        cobalt_wash="#16233f",
        signal="#f0916a",
        signal_wash="#3a1f14",
        verified="#57c09c",
        verified_wash="#12302a",
        canvas="#0d1117",
    ),
)


class _Face:
    def __init__(self, key):
        path = FONT_DIR / FONTS[key]
        self.key = key
        self.tt = TTFont(path)
        self.glyphset = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.upem = self.tt["head"].unitsPerEm
        blob = hb.Blob.from_file_path(str(path))
        self.font = hb.Font(hb.Face(blob))

    def shape(self, text):
        if not text:
            return []
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.font, buf, {"kern": True, "liga": False})
        return [
            (self.order[info.codepoint], pos.x_advance, pos.x_offset, pos.y_offset)
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions)
        ]


_faces = {}


def face(key):
    if key not in _faces:
        _faces[key] = _Face(key)
    return _faces[key]


def text_width(text, font, size, tracking=0.0):
    f = face(font)
    scale = size / f.upem
    glyphs = f.shape(text)
    return sum(g[1] * scale + tracking * size for g in glyphs) - tracking * size


def wrap(text, font, size, width):
    """Greedy line breaks by measured width."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if text_width(trial, font, size) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class Canvas:
    def __init__(self, width, height, theme, title, desc):
        self.width = width
        self.height = height
        self.t = THEMES[theme]
        self.title = title
        self.desc = desc
        self.defs = {}
        self.body = []

    def _glyph(self, f, name):
        key = f"{f.key}-{name}"
        if key not in self.defs:
            pen = SVGPathPen(f.glyphset, ntos=lambda v: f"{v:.0f}")
            f.glyphset[name].draw(pen)
            self.defs[key] = (f"g{len(self.defs)}", pen.getCommands())
        return self.defs[key][0]

    def text(self, x, y, text, font="sans", size=16, color="ink", anchor="start", tracking=0.0):
        f = face(font)
        scale = size / f.upem
        glyphs = f.shape(text)
        total = sum(g[1] * scale + tracking * size for g in glyphs) - tracking * size
        if anchor == "middle":
            x -= total / 2
        elif anchor == "end":
            x -= total
        fill = self.t.get(color, color)
        uses = []
        pen_x = 0.0
        for name, advance, dx, dy in glyphs:
            ref = self._glyph(f, name)
            uses.append(
                f'<use href="#{ref}" x="{(pen_x + dx * scale) / scale:.0f}" y="{-dy:.0f}"/>'
            )
            pen_x += advance * scale + tracking * size
        self.body.append(
            f'<g fill="{fill}" transform="translate({x:.2f} {y:.2f}) scale({scale:.5f} {-scale:.5f})">'
            + "".join(uses)
            + "</g>"
        )
        return total

    def rect(self, x, y, w, h, fill="none", stroke=None, sw=1, r=0, dash=None):
        attrs = f'x="{x}" y="{y}" width="{w}" height="{h}" fill="{self.t.get(fill, fill)}"'
        if r:
            attrs += f' rx="{r}"'
        if stroke:
            attrs += f' stroke="{self.t.get(stroke, stroke)}" stroke-width="{sw}"'
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        self.body.append(f"<rect {attrs}/>")

    def line(self, x1, y1, x2, y2, stroke="rule", sw=1, dash=None):
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.body.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{self.t.get(stroke, stroke)}" stroke-width="{sw}"{extra}/>'
        )

    def path(self, d, fill="none", stroke=None, sw=1, cap=None, join=None, dash=None):
        attrs = f'd="{d}" fill="{self.t.get(fill, fill)}"'
        if stroke:
            attrs += f' stroke="{self.t.get(stroke, stroke)}" stroke-width="{sw}"'
        if cap:
            attrs += f' stroke-linecap="{cap}"'
        if join:
            attrs += f' stroke-linejoin="{join}"'
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        self.body.append(f"<path {attrs}/>")

    def circle(self, cx, cy, r, fill="none", stroke=None, sw=1):
        attrs = f'cx="{cx}" cy="{cy}" r="{r}" fill="{self.t.get(fill, fill)}"'
        if stroke:
            attrs += f' stroke="{self.t.get(stroke, stroke)}" stroke-width="{sw}"'
        self.body.append(f"<circle {attrs}/>")

    def arrow(self, x1, y1, x2, y2, stroke="ink3", sw=1.5, head=7, dash=None):
        import math

        angle = math.atan2(y2 - y1, x2 - x1)
        self.line(x1, y1, x2 - head * 0.7 * math.cos(angle), y2 - head * 0.7 * math.sin(angle), stroke, sw, dash)
        a = angle + math.radians(155)
        b = angle - math.radians(155)
        self.path(
            f"M{x2:.2f} {y2:.2f}L{x2 + head * math.cos(a):.2f} {y2 + head * math.sin(a):.2f}"
            f"L{x2 + head * math.cos(b):.2f} {y2 + head * math.sin(b):.2f}Z",
            fill=stroke,
        )

    def check(self, x, y, color="verified", size=12):
        s = size / 14
        self.path(
            f"M{x + 3 * s:.2f} {y + 7.2 * s:.2f}l{2.6 * s:.2f} {2.6 * s:.2f}L{x + 11 * s:.2f} {y + 4.4 * s:.2f}",
            stroke=color,
            sw=1.8,
            cap="round",
            join="round",
        )

    def cross(self, x, y, color="ink3", size=12):
        s = size / 14
        self.path(
            f"M{x + 3.5 * s:.2f} {y + 3.5 * s:.2f}l{7 * s:.2f} {7 * s:.2f}M{x + 10.5 * s:.2f} {y + 3.5 * s:.2f}l{-7 * s:.2f} {7 * s:.2f}",
            stroke=color,
            sw=1.6,
            cap="round",
        )

    def mark(self, x, y, size, accent="#3268f5", color="ink"):
        """The UNLOCK mark, from frontend/public/favicon.svg (24-unit grid)."""
        s = size / 24
        self.path(
            f"M{x + 2 * s:.2f} {y + 22 * s:.2f}V{y + 11 * s:.2f}h{7 * s:.2f}v{3 * s:.2f}H{x + 5 * s:.2f}v{8 * s:.2f}z"
            f"M{x + 22 * s:.2f} {y + 22 * s:.2f}V{y + 11 * s:.2f}h{-7 * s:.2f}v{3 * s:.2f}h{4 * s:.2f}v{8 * s:.2f}z",
            fill=color,
        )
        self.rect(round(x + 9.5 * s, 2), round(y + 2 * s, 2), round(5 * s, 2), round(5 * s, 2), fill=accent)

    def svg(self):
        defs = "".join(f'<path id="{i}" d="{d}"/>' for i, d in self.defs.values())
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" role="img" aria-labelledby="t d">'
            f'<title id="t">{escape(self.title)}</title><desc id="d">{escape(self.desc)}</desc>'
            f"<defs>{defs}</defs>" + "".join(self.body) + "</svg>\n"
        )
