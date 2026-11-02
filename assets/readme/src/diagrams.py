"""Generate the README's vector diagrams, with numbers read from committed evidence.

usage (from the repository root, with a venv holding uharfbuzz and fonttools):
  UNLOCK_FONT_DIR=<fonts> python assets/readme/src/diagrams.py
"""

import json
from pathlib import Path

from svgkit import Canvas, text_width, wrap

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = HERE.parents[2]
EVIDENCE = ROOT / "backend" / "evidence"


def live(code):
    report = json.loads((EVIDENCE / f"live-{code}" / "live_run.json").read_text())
    verified = next(iter(report["engineering_evidence"]["verified"].values()))
    return report, verified


def brand(theme):
    c = Canvas(
        1200,
        252,
        theme,
        "UNLOCK. Design for the day it breaks.",
        "The UNLOCK mark and wordmark above the tagline, Design for the day it breaks.",
    )
    word = "UNLOCK"
    size = 25
    tracking = 0.2
    wide = text_width(word, "sans600", size, tracking)
    mark = 40
    gap = 14
    x = 600 - (mark + gap + wide) / 2
    c.mark(x, 22, mark, color="ink")
    c.text(x + mark + gap, 53, word, "sans600", size, "ink", tracking=tracking)
    c.text(600, 164, "Design for the day it breaks.", "sans600", 88, "ink", "middle", tracking=-0.038)
    c.text(
        600,
        222,
        "AI-assisted redesign for mechanical repairability.",
        "sans",
        27,
        "ink2",
        "middle",
        tracking=-0.008,
    )
    return c


def panel_items(c, x, y, width, items, color):
    for i, item in enumerate(items):
        row = y + i * 40
        c.circle(x + 5, row - 6, 3, fill=color)
        c.text(x + 20, row, item, "sans", 16.5, "ink")


def trust_boundary(theme):
    c = Canvas(
        1200,
        640,
        theme,
        "The trust boundary between Muse Spark 1.3 and the deterministic engine",
        "On the left, the model reads evidence and proposes values from finite lists. In the middle, a "
        "dispatcher enforces an allowlist, strict schema, frozen identity, run-issued evidence, the "
        "finite domain and budgets. On the right, the engine constructs, rebuilds, checks, replans and "
        "compares. Typed feedback returns to the model. The model's own statements are stored with "
        "authority: none.",
    )
    top = 28
    height = 438
    # Model
    c.rect(0.5, top, 356, height, fill="cobalt_wash", r=10)
    c.text(28, top + 42, "PROBABILISTIC", "mono500", 13, "cobalt", tracking=0.09)
    c.text(28, top + 80, "Muse Spark 1.3", "sans600", 30, "ink", tracking=-0.02)
    c.text(28, top + 110, "Proposes.", "sans", 19, "ink2")
    panel_items(
        c,
        28,
        top + 168,
        300,
        [
            "Reads compact, structured evidence",
            "Never sees a STEP file or a mesh",
            "Calls only eight allowlisted tools",
            "Picks values from finite server lists",
            "Cites evidence this run issued",
            "Writes no code and no geometry",
        ],
        "cobalt",
    )
    # Gate
    gate_x = 420
    c.rect(gate_x + 0.5, top, 360, height, fill="panel", stroke="rule", r=10)
    c.text(gate_x + 180, top + 42, "THE ONLY DOOR", "mono500", 13, "ink3", "middle", tracking=0.09)
    c.text(gate_x + 180, top + 80, "Dispatcher", "sans600", 30, "ink", "middle", tracking=-0.02)
    c.text(gate_x + 180, top + 110, "Validates every call.", "sans", 19, "ink2", "middle")
    gates = [
        ("Tool allowlist", "TOOL_NOT_ALLOWED"),
        ("Strict JSON schema", "SCHEMA_ERROR"),
        ("Frozen revision and target", "STALE_EVIDENCE"),
        ("Run-issued evidence cited", "INVALID_PROPOSAL"),
        ("Inside the finite domain", "INVALID_PROPOSAL"),
        ("Inside the run budgets", "BUDGET_EXHAUSTED"),
    ]
    for i, (label, code) in enumerate(gates):
        row = top + 134 + i * 47
        c.rect(gate_x + 20, row, 320, 39, fill="canvas", stroke="rule", r=6)
        c.text(gate_x + 34, row + 17, label, "sans500", 14.5, "ink")
        c.text(gate_x + 34, row + 32, code, "mono", 10.5, "ink3", tracking=0.02)
    # Engine
    engine_x = 844
    c.rect(engine_x + 0.5, top, 355, height, fill="verified_wash", r=10)
    c.text(engine_x + 28, top + 42, "DETERMINISTIC", "mono500", 13, "verified", tracking=0.09)
    c.text(engine_x + 28, top + 80, "CAD engine", "sans600", 30, "ink", tracking=-0.02)
    c.text(engine_x + 28, top + 110, "Decides.", "sans", 19, "ink2")
    panel_items(
        c,
        engine_x + 28,
        top + 168,
        300,
        [
            "Trusted constructor builds the solid",
            "Fresh worker rebuilds it to compare",
            "Mandatory checks on real BReps",
            "Planner searches the revised design",
            "Forward replay, reverse insertion",
            "Comparison under one frozen policy",
        ],
        "verified",
    )
    # Arrows through the gate
    c.arrow(358, top + 196, gate_x - 3, top + 196, "cobalt", 2, 9)
    c.text(389, top + 182, "proposal", "mono", 10.5, "cobalt", "middle")
    c.arrow(gate_x + 362, top + 196, engine_x - 3, top + 196, "verified", 2, 9)
    c.text(812, top + 182, "valid", "mono", 10.5, "verified", "middle")
    c.arrow(gate_x - 3, top + 318, 360, top + 318, "ink3", 1.5, 8)
    c.text(389, top + 342, "typed", "mono", 10.5, "ink3", "middle")
    c.text(389, top + 356, "feedback", "mono", 10.5, "ink3", "middle")
    c.arrow(engine_x - 3, top + 318, gate_x + 364, top + 318, "ink3", 1.5, 8)
    c.text(812, top + 342, "measured", "mono", 10.5, "ink3", "middle")
    c.text(812, top + 356, "values", "mono", 10.5, "ink3", "middle")
    # Authority strip
    y = top + height + 26
    c.rect(0.5, y, 1199, 118, fill="panel", stroke="rule", r=10)
    c.text(28, y + 37, "The model's closing message, as stored by the engine in every run report", "sans500", 16, "ink2")
    c.text(
        28,
        y + 76,
        '"authority": "none: model statement, not engineering evidence"',
        "mono500",
        21,
        "signal",
    )
    c.text(28, y + 102, "backend/src/unlock_engine/ai/controller.py:399", "mono", 12, "ink3")
    return c


CHECK_ROWS = [
    ("integrity", "Hashes of revision, geometry, policy and constraints match"),
    ("solid_validity", "Every part is one valid, closed, positive-volume solid"),
    ("trusted_reconstruction", "Fresh rebuild matches by two-way BRep difference"),
    ("actual_change", "Material really changed, measured"),
    ("editable_region", "Removed material lies inside the declared region"),
    ("protected_interfaces", "Feet, posts and hole voids unchanged"),
    ("hole_geometry", "Cylindrical hole surfaces agree"),
    ("fixed_components", "Every other part compared independently"),
    ("placements", "STEP world placements unchanged"),
    ("design_envelope", "All solids inside the declared envelope"),
    ("keep_outs", "Every solid clear of every keep-out"),
    ("assembled_intersections", "All pairs checked; only validated planar contacts"),
]


def ledger(theme):
    b02, b02v = live("b02")
    b05, b05v = live("b05")
    checks = [
        {c["constraint_id"]: c for c in v["static_report"]["checks"]} for v in (b02v, b05v)
    ]
    plans = [dict(map(tuple, v["plan"]["constraint_checks"])) for v in (b02v, b05v)]
    row_h = 35
    head = 112
    extras = 3
    table = head + 12 + (len(CHECK_ROWS) + extras) * row_h
    c = Canvas(
        1200,
        table + 146,
        theme,
        "Verification ledger of the two live redesign runs",
        "Static checks, target path, forward replay and reverse insertion all passed on live runs B02 "
        "and B05. Editable region applies only to the T01 cut on B02. Strength, fatigue, electrical "
        "safety, manufacturing feasibility and restored function are not assessed.",
    )
    name_x, why_x, a_x, b_x = 0, 240, 866, 1046
    c.text(a_x, 30, "B02  T01 cut", "sans600", 17, "ink")
    c.text(a_x, 52, "40 × 16 mm relief", "mono", 12.5, "ink3")
    c.text(a_x, 70, b02["run_id"], "mono", 10.5, "ink3")
    c.text(b_x, 30, "B05  T02 move", "sans600", 17, "ink")
    c.text(b_x, 52, "strap −12 mm", "mono", 12.5, "ink3")
    c.text(b_x, 70, b05["run_id"], "mono", 10.5, "ink3")
    c.text(name_x, 70, "Live Muse Spark 1.3 runs", "sans600", 17, "ink")
    c.line(0, 90, 1200, 90, "ink", 1.5)

    def mark(x, y, result, note=None):
        if result == "pass":
            c.check(x, y - 12, "verified", 15)
            if note:
                c.text(x + 22, y, note, "mono500", 13, "verified")
        elif result == "none":
            c.text(x + 2, y, note or "not applicable", "sans", 12.5, "ink3")
        else:
            raise SystemExit(f"ledger: unexpected check result {result}")

    def measure(value):
        return f"{round(value):,} mm³"

    y = head + 4
    for i, (name, why) in enumerate(CHECK_ROWS):
        row = y + i * row_h
        c.text(name_x, row, name, "mono500", 15, "ink")
        c.text(why_x, row, why, "sans", 16, "ink2")
        for idx, x in enumerate((a_x, b_x)):
            found = checks[idx].get(name)
            if found is None:
                if name != "editable_region" or idx != 1:
                    raise SystemExit(f"ledger: {name} missing")
                mark(x, row, "none", "T01 only")
                continue
            note = None
            if name == "actual_change":
                note = measure(found["measured_value"])
            if name == "editable_region":
                note = f"{found['measured_value']:.0f} mm³ outside"
            mark(x, row, found["result"], note)
        c.line(0, row + 12, 1200, row + 12, "rule", 0.75)
    route = y + len(CHECK_ROWS) * row_h
    for i, (name, why, getter) in enumerate(
        (
            ("target_path", "Route check on the revised plan", lambda idx, v: plans[idx]["target_path"]),
            ("forward replay", "Every saved transition recomputed from the frozen revision", lambda idx, v: {"passed": "pass"}[v["plan"]["replay"]["status"]]),
            ("reverse insertion", "Inverse moves rechecked; initial connections restored", lambda idx, v: {"passed": "pass"}[v["plan"]["reverse"]["status"]]),
        )
    ):
        row = route + i * row_h
        c.text(name_x, row, name, "mono500", 15, "ink")
        c.text(why_x, row, why, "sans", 16, "ink2")
        for idx, (x, v) in enumerate(((a_x, b02v), (b_x, b05v))):
            mark(x, row, getter(idx, v))
        c.line(0, row + 12, 1200, row + 12, "rule", 0.75)
    footer = route + extras * row_h + 6
    c.rect(0.5, footer, 1199, 118, fill="signal_wash", r=10)
    c.text(28, footer + 34, "NOT ASSESSED", "mono500", 13, "signal", tracking=0.09)
    limits = "Structural strength and fatigue,  electrical safety,  manufacturing feasibility,  restored product function"
    c.text(28, footer + 64, limits, "sans500", 17.5, "ink", tracking=-0.005)
    c.text(
        28,
        footer + 94,
        "A verified improvement is a design-review result, not engineering or manufacturing release approval.",
        "sans",
        15.5,
        "ink2",
    )
    expected = set(b02["limitations"][:4])
    if expected != {"Structural strength and fatigue", "Electrical safety", "Manufacturing feasibility", "Restored product function"}:
        raise SystemExit("ledger: limitations in evidence changed")
    return c


def box(c, x, y, w, h, title, lines=(), fill="canvas", stroke="rule", accent=None, title_size=16):
    c.rect(x + 0.5, y + 0.5, w, h, fill=fill, stroke=stroke, r=8)
    c.text(x + 14, y + 27, title, "sans600", title_size, accent or "ink", tracking=-0.005)
    for i, line in enumerate(lines):
        if text_width(line, "sans", 14.5) > w - 22:
            raise SystemExit(f"architecture: line too wide for its box: {line}")
        c.text(x + 14, y + 49 + i * 19, line, "sans", 14.5, "ink2")


def architecture(theme):
    c = Canvas(
        1200,
        838,
        theme,
        "UNLOCK architecture, deployed and local",
        "Deployed: a React and Three.js site on Cloudflare Pages reads recorded runs from a read-only "
        "Modal API, and a separate judge gateway runs private offline jobs. Local: the same frontend "
        "talks to a FastAPI coordinator, whose bounded agent controller calls the Meta Model API or a "
        "labelled offline policy. Both reach one engine, built on CadQuery and OpenCASCADE, with "
        "isolated native workers.",
    )

    def lane(y, h, label, sub):
        c.rect(0.5, y + 0.5, 1199, h, fill="panel", stroke="rule", r=12)
        c.text(24, y + 32, label, "mono500", 13, "ink2", tracking=0.09)
        c.text(24 + text_width(label, "mono500", 13, 0.09) + 14, y + 32, sub, "sans", 14, "ink3")

    # Deployed lane
    lane(0, 298, "DEPLOYED", "public demonstration. No Meta inference runs here.")
    box(c, 24, 54, 256, 106, "Cloudflare Pages", ["unlock-labs.pages.dev", "React, TypeScript, Three.js.", "The browser calls two APIs."], accent="cobalt")
    box(c, 344, 54, 256, 106, "Modal: unlock-demo", ["Read-only FastAPI, recorded", "runs, mock provider. Anonymous", "POST returns 403."], accent="cobalt")
    box(c, 344, 176, 256, 106, "Modal: unlock-judges", ["Private code, owned results,", "10 MiB uploads, six attempts", "in total."], accent="signal")
    box(c, 664, 176, 256, 106, "Modal: unlock-engineering", ["Private CPU worker, live=False.", "Fresh offline analysis and", "gallery composition."])
    box(c, 960, 54, 216, 228, "Modal Volume", ["Immutable job snapshots", "Composed gallery", "Judge ledger", "Artifacts by SHA-256", "", "Public API mounts one", "subdirectory, read-only."])
    c.arrow(282, 106, 342, 106, "ink3")
    c.arrow(282, 145, 342, 205, "ink3")
    c.arrow(602, 229, 662, 229, "ink3")
    c.arrow(922, 229, 958, 229, "ink3")
    c.arrow(600, 88, 958, 88, "ink3", 1.5, 7, dash="4 4")
    c.text(780, 78, "reads", "mono", 11, "ink3", "middle")

    # Local lane
    lane(316, 196, "LOCAL", "the full interactive workflow, on your machine.")
    box(c, 24, 370, 216, 124, "React workspace", ["localhost:5183", "Renders what reports say;", "never derives a status."], accent="cobalt")
    box(c, 288, 370, 262, 124, "FastAPI coordinator", ["Loopback, one serial job queue,", "SQLite, resumable events,", "immutable revisions."])
    box(c, 598, 370, 288, 124, "Bounded agent controller", ["8 tools, 3 candidates, 12 calls,", "6 turns, 16,000 tokens, 120 s.", "Outcome derived from evidence."], accent="verified")
    box(c, 934, 370, 242, 124, "Meta Model API", ["muse-spark-1.3, tool calling.", "Or AI_PROVIDER=mock, a", "labelled offline policy."], accent="cobalt")
    c.arrow(242, 432, 286, 432, "ink3")
    c.arrow(552, 432, 596, 432, "ink3")
    c.arrow(888, 420, 932, 420, "cobalt", 1.5)
    c.arrow(932, 444, 888, 444, "cobalt", 1.5)

    # Engine lane
    c.rect(0.5, 530.5, 1199, 306, fill="verified_wash", r=12)
    c.text(24, 562, "ENGINE", "mono500", 13, "verified", tracking=0.09)
    c.text(24 + text_width("ENGINE", "mono500", 13, 0.09) + 14, 562, "one codebase behind both paths: backend/src/unlock_engine", "sans", 14, "ink2")
    steps = [
        ("Package gate", ["STEP + manifest", "AP214/AP242, mm", "Bounded first"]),
        ("Import", ["Rigid solids", "Measured inventory", "Immutable revision"]),
        ("Planner", ["Six-axis search", "Analytic sweeps", "BRep witnesses"]),
        ("Templates", ["T01 relief", "T02 offset", "Finite domains"]),
        ("Verifier", ["Fresh rebuild", "Mandatory checks", "Replay, reverse"]),
        ("Export", ["Real reimport", "Recheck, bundle", "SHA-256 artifacts"]),
    ]
    w = 180
    for i, (title, lines) in enumerate(steps):
        x = 24 + i * (w + 9.6)
        box(c, round(x, 1), 582, w, 112, title, lines, title_size=15.5)
        if i < len(steps) - 1:
            c.arrow(round(x + w + 0.5, 1), 638, round(x + w + 9.2, 1), 638, "verified", 1.2, 5)
    c.rect(24.5, 712.5, 1152, 104, fill="canvas", stroke="rule", r=8)
    c.text(40, 742, "Isolated native workers", "sans600", 15.5, "ink")
    c.text(40, 766, "Each CAD operation runs in its own subprocess, with wall-clock limits and credentials stripped.", "sans", 14, "ink2")
    c.text(40, 790, "CadQuery 2.6.1 on OpenCASCADE 7.8 (OCP). Exact BReps in millimetres; meshes are preview only.", "sans", 14, "ink2")
    c.arrow(419, 495, 419, 529, "ink3")
    c.arrow(742, 495, 742, 529, "ink3")
    c.arrow(910, 283, 910, 529, "ink3", 1.5, 7, dash="4 4")
    return c


def main():
    outputs = dict(
        brand=brand,
        **{"trust-boundary": trust_boundary, "verification-ledger": ledger, "architecture": architecture},
    )
    for name, build in outputs.items():
        for theme in ("light", "dark"):
            path = OUT / f"{name}-{theme}.svg"
            path.write_text(build(theme).svg())
            print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
