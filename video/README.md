# Demo video graphics

Motion graphics for the UNLOCK demo video, built with [Remotion](https://www.remotion.dev/).
Each scene is its own 1920×1080, 30 fps composition, so it can be cut together
with screen recordings and footage in any editor. `AllScenes` plays them back to
back for timing review.

Everything shown is real data. `scripts/export_data.py` takes it from the engine
and the committed evidence, never by hand:

- **B05 meshes:** the engine's own tessellation of the battery bay, plus the strap
  re-constructed at −12 mm. The script refuses to export unless that strap's
  geometry hash equals the live run's verified design.
- **Contact point:** the BRep witness of the confirmed obstruction, recomputed by
  the planner: (0, 8.0, 32.0) mm after 12 mm of lift.
- **The live run:** turns, tool calls, Muse's notes and rationale, stage times
  and checks, from `backend/evidence/live-b05/live_run.json`.
- **The gallery:** names, descriptions and pre-registered outcomes from
  `fixture_catalog.py`.

## Scenes

| Composition | Length | Shows |
|:--|--:|:--|
| `Title` | 5 s | The mark assembles; the cobalt part rises out through the relief |
| `Tools` | 6 s | The eight tools Muse can call, the seven it used live, and what it cannot reach |
| `LiveRun` | 30 s | The live Muse Spark 1.3 run on B05, replayed ≈3× faster with the real clock on screen |
| `Checks` | 8 s | The revised plan's 12 checks, re-planning, replay and reverse insertion |
| `Answers` | 9 s | Six assemblies and six recorded outcomes, refusals included |
| `EndCard` | 6 s | "Every battery wears out. Design for the day it does." |

## Use

```sh
npm install
npm run studio                                    # preview and scrub
npx remotion render LiveRun out/LiveRun.mp4 --codec=h264 --crf=16
```

Regenerate the data after the fixtures or the evidence change, from the
repository root:

```sh
PYTHONPATH=backend/src backend/.venv/bin/python video/scripts/export_data.py
```

## Keep it honest

- `LiveRun`, `Tools` and `Checks` show the **live** run of 2026-11-01. The public
  site's B05 page shows the same design from the offline scripted policy, so
  don't present a site recording as the live run.
- The replay is faster than real time. The clock on screen is real; keep the
  "replayed ≈3× faster" note visible.
- Remotion is free for individuals and teams of up to three; check its
  [licence](https://www.remotion.dev/license) if the team is larger.
