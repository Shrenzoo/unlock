# How the README's visuals are made

[← Back to the README](../../../README.md)

Nothing on the README page is modelled or drawn by hand from imagination. The 3D comes from the engine, the diagrams read their numbers from committed evidence, and each script stops if its source data disagrees with the record.

## The pipeline

| Step | Script | Runs in | Output |
|:--|:--|:--|:--|
| 1. Export geometry | `export_scene.py` | The backend's Python | `.build/<code>.json`, `scene_provenance.json` |
| 2. Render frames | `render_hero.py`, `render_cells.py` | Blender 5 (Cycles) | Transparent PNG frames in `.build/` |
| 3. Composite and encode | `compose.py`, `compose_cells.py` | Python with Pillow | `hero-*`, `relief-*`, `gallery-*`, `sequence-*` |
| 4. Diagrams | `diagrams.py` | Python with HarfBuzz and fontTools | `brand-*`, `trust-boundary-*`, `verification-ledger-*`, `architecture-*` |

`.build/` is not committed: it is large and regenerates exactly. [`scene_provenance.json`](scene_provenance.json) is committed, and records each fixture's witness, plan and design hash.

## What each step guarantees

**Geometry is the engine's.** `export_scene.py` generates each fixture with `fixtures.generate_fixture`, imports it with `service.import_revision`, and tessellates the BReps. Vertices stay per face, so smooth shading never crosses a CAD edge, and the lines you see are the real BRep edges.

**Redesigns are the recorded ones.** Brackets are rebuilt by `service.construct_candidate`. For B02 and B05 the script exits unless the rebuilt geometry hash equals the live run's verified design (`7aebefb8…`, `c9b46d5a…`). B04, B06 and the gallery's B02 cell use the designs recorded under the offline policy, as the public API reports them. The T01 clip shows the live run's 40 × 16 and the gallery shows its 24 × 12: they are different records of the same fixture.

**The interference is the witness.** The orange solid is a boolean intersection of the target, moved by the planner's recorded `travel_mm`, with the bracket. On B02 this reproduces the 640 mm³ in the run's notes. On B05 it gives 1,397 mm³.

**Motion between states is the constructor's.** The strap's web moves through solids the constructor built at each frame. Only the last frame, −12 mm, is the verified design. The in-between positions illustrate the move and are not candidates that anything verified.

**Numbers are checked before they are drawn.** `compose.py` asserts its captions against the live report and exported scene before it draws a frame. `diagrams.py` reads the ledger from the two live reports, and raises on an unexpected result.

## What the animations simplify

- Timing is presentation, not a measurement. Colours and captions are annotations, and the hero's twelve ticks stand for twelve recorded results.
- The offline clips show each fixture's recorded outcome, not a replay of its events. B07's driver is drawn from the manifest's declared dimensions and stops at the fixed shield's top face, where the recorded `TOOL_ACCESS_BLOCKED` occurs.
- A static preview render is not evidence. Only the reports are.

## Rebuilding

From the repository root. The backend's virtual environment provides step 1, and `UNLOCK_FONT_DIR` points at Instrument Sans and IBM Plex Mono static TTFs (OFL, from Google Fonts) named as in `svgkit.py`.

```sh
PYTHONPATH=backend/src backend/.venv/bin/python assets/readme/src/export_scene.py
cd assets/readme/src
Blender -b -P render_hero.py
Blender -b -P render_cells.py -- --code B02 --size 440x275 --samples 16 --gallery-design
for code in B04 B05 B06 B07 B08; do Blender -b -P render_cells.py -- --code $code --size 440x275 --samples 16; done
Blender -b -P render_cells.py -- --code B02 --size 780x485 --samples 24 --tag relief --close
UNLOCK_FONT_DIR=<fonts> python compose.py
UNLOCK_FONT_DIR=<fonts> python compose_cells.py
UNLOCK_FONT_DIR=<fonts> python diagrams.py
```

The hero takes about an hour on an Apple M5 under load. `compose.py` and `compose_cells.py` need Pillow, NumPy and ffmpeg. `diagrams.py` needs `uharfbuzz` and `fonttools`.
