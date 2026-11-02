# Validation report

[← Back to the README](../README.md) · [Claim ledger](claims.md) · [README audit](readme-audit.md)

What was executed for the 2026-11-01 README redesign, on an Apple M5 running macOS, and what was not. The change is documentation and visuals only: `git diff origin/main --name-only -- backend frontend` lists no files.

## Setup path, in a fresh clone

`git clone` of `main` at `6604c31` into an empty directory, with a new virtual environment and the README's exact commands.

| Command | Result |
|:--|:--|
| `python3.12 -m venv .venv` | Python 3.12.16 |
| `pip install -r requirements.lock`, then `--no-deps --no-build-isolation -e .` | Succeeded with a warm pip cache. `.venv` is 1.1 GB. A cold download was not timed |
| `python -m unlock_engine.ai demo --offline --fixture B05` | `VERIFIED_IMPROVEMENT_FOUND`, T02 −12 mm, 41.2 s |
| `python -m unlock_engine.ai demo --offline --fixture B02` | `VERIFIED_IMPROVEMENT_FOUND`: 24×8 rejected `NO_REPAIR_PATH`, then 24×12 verified, 41.8 s |
| `unlock-engine plan-demo --output .work/planning` | Exit 0 |
| `pytest -q tests/test_ai_toolbox.py tests/test_ai_controller.py tests/test_templates_verification.py` | 65 passed in 220.95 s |
| `npm ci`, then `npm run dev -- --host 127.0.0.1 --port 5183 --strictPort` | Served, on Node 26.10.0 |
| `AI_PROVIDER=mock python -m unlock_engine.api --port 8000` | `/health`: mode `local`, provider `mock`, credentials `missing` |

**Full workspace, driven in the browser, B02.** Set `target` as the repair target, ran the baseline (`no_path_supported`, two confirmed witnesses), requested a redesign (24×8 failed, 24×12 passed, `VERIFIED IMPROVEMENT FOUND`), compared (27 passes, 0 failures, 0 unknown), accepted, and created the checked package. Result: "Export full assembly; STEP round trip passed", package SHA-256 `b0489b637bde…`. All of this ran against scratch data.

**An unplanned result.** The same offline B02 demo, run earlier while a GPU render held the load average above 16, ended `INCOMPLETE_ANALYSIS` at 120.5 s with `GEOMETRY_FAILED: native operation timed out`. It reported that it could not finish and claimed nothing. The README lists this as a limitation.

## Evidence and code checks

- Each `jq`, `shasum` and `grep` command in the README's reproducibility section was run from the repository root and printed the stated result.
- Each `#L` line reference to code was checked for the expected symbol.
- `pytest --collect-only` at `6604c31`: 389 collected, 32 deselected, 357 selected.
- `export_scene.py` regenerated all six fixtures. Rebuilt B02 and B05 brackets matched the live reports' geometry hashes `7aebefb8…` and `c9b46d5a…`, and the B02 witness reproduced the recorded 640 mm³.
- `compose.py` asserted the hero's captions against `live-b05/live_run.json`. `compose_cells.py` asserted gallery labels against `gallery-release-lighter/validation.json`. `diagrams.py` read the ledger from both live reports. All passed.
- The route overlay's camera projection was compared with Blender's own at sampled frames, within 1.5 px.

## The deployed service, read-only

- `GET /health`: `read_only`, provider `mock`, credentials `missing`, six recorded runs.
- `GET /v1/projects` and each recorded run: six outcomes and every design in the README's table match, including B02's 24×8 then 24×12, and B07's three candidates.
- `GET /v1/candidates/candidate_630dfe62…`: the 26 listed checks behind the workspace's 25 passes (one, `tool_access`, is not applicable).
- Anonymous `POST` to an import route: 403.
- Headless Chrome opening B05's workspace and comparison: 0 non-GET requests.
- `https://unlock-labs.pages.dev`: 200.

## GitHub rendering

Real Chrome against `github.com/Shrenzoo/unlock/tree/docs/readme-redesign`, not a local preview. Pages were scrolled through and read in screenshots.

| Case | Images loaded | Assets chosen | Page overflow | Anchors resolving |
|:--|--:|:--|:--|--:|
| Desktop 1280, light | 9 of 9 | Light | None | 44 of 44 |
| Desktop 1280, dark | 9 of 9 | Dark | None | 44 of 44 |
| Phone 390, light | 9 of 9 | Light | None | 44 of 44 |
| Phone 390, dark | 9 of 9 | Dark | None | 44 of 44 |
| Desktop, reduced motion, light | 9 of 9 | Light posters, no GIFs | None | 44 of 44 |
| Desktop, reduced motion, dark | 9 of 9 | Dark posters, no GIFs | None | 44 of 44 |

The GIFs animate on the page and their backgrounds match GitHub's default light and dark canvas exactly. The Mermaid diagram renders natively, and all tables and code blocks render. On a phone, wide tables scroll inside their own frames and the page itself does not scroll sideways.

## Documents and assets

`python3 docs/check_docs.py --external` passes:

- Relative links, heading anchors and `#L` references resolve across the README and `docs/`.
- All 26 external links return 200, including the live demo's six project pages.
- Every `<img>` has alt text, and every asset in `assets/readme/` is referenced.
- No tracked document matches the credential patterns. A wider scan of the branch's diff for emails, key prefixes and tokens found none.

**Asset weight.** 19 old SVGs were removed and 23 new assets added, 8 MB in total across both themes. A reader downloads only one theme: about 4 MB, of which the hero is 2.2 to 2.7 MB. The first hero encode was 8.4 MB.

| Asset | Light | Dark |
|:--|--:|--:|
| Hero GIF, 1000 × 563, 12.2 s | 2.7 MB | 2.1 MB |
| Gallery GIF, 1000 × 554, 6.9 s | 0.55 MB | 0.45 MB |
| T01 GIF, 780 × 485, 6.9 s | 0.44 MB | 0.33 MB |

## What was not run

These were skipped deliberately, as the task required.

- **The full CAD test suite.** No engine or test code changed. The last recorded full run remains 342 passed, 27 deselected (2026-10-31), so the 15 tests added since then in the default selection have no recorded full run behind this README. The 65 tests above did run.
- **Paid API calls.** No Meta inference was made. Every live result quoted is from earlier recorded runs.
- **Deployment.** Nothing was deployed, and no billing, secret or authentication setting changed. Read-only requests to the public site will have woken its scale-to-zero API briefly.
- **The judge code.** It was neither read nor entered, and no judge attempt was used.

## What could not be confirmed

- **The organizer's event page** was not reachable at the URL tried. Track and theme names come from the PRD's record of that page, a public event guide, and the maintainer. Please confirm them against your submission.
- **Other clients.** Safari, Firefox, GitHub's mobile apps and the "dark dimmed" theme were not inspected. On "dark dimmed", the GIFs' dark background will show as a slightly different rectangle.
- **A cold install's time.** The fresh-clone install used a warm pip cache.
- **The demo film.** It has no public URL yet, so the README has no film link. A comment in the README marks where it goes.
