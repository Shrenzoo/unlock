# Browser acceptance — real services, B02 and upload

Executed October 30, 2026 on `feature/browser-e2e-acceptance`, commit `507a74e`.
**Result: 14 of 14 browser tests passed** (3 min 54 s) against the real FastAPI
coordinator, its native CAD workers and a production frontend bundle. The browser
was installed Chrome 156, headless, with hardware WebGL (ANGLE Metal on an Apple
M5, not software rendering).

The other checks were clean too:
- the full offline backend suite: 327 tests passed;
- Ruff check and format, and `pip check`;
- TypeScript and the Vite production build.

The decision policy throughout is the **labelled offline scripted policy**
(`AI_PROVIDER=mock`):
- **What is real:** every CAD construction, verification, plan, comparison and
  export.
- **What isn't:** no model inference happens, and no paid request is possible,
  because every backend starts with `MODEL_API_KEY` blanked.

B02 is a **synthetic fixture**.

## How to run

```sh
cd frontend && npm ci          # once
cd ../backend
.venv/bin/python scripts/browser_qa.py      # = python -m pytest -m browser tests/browser
```

- **Servers:** the suite starts its own coordinator on ports 8100–8102 (8199 is
  left closed for the missing-backend case). It builds a production bundle per API
  origin and serves each with `vite preview` on ports 5193–5196.
- **Default runs:** ordinary `pytest` deselects these tests (marker `browser`).
- **Evidence:** each run writes to `backend/.work/browser-acceptance/<UTC stamp>/`.
  A curated copy of the final run is in
  [`../evidence/browser-acceptance/`](../evidence/browser-acceptance/): `report.json`
  plus screenshots, stored as quality-85 JPEG and otherwise unaltered.

## What the tests prove

**`test_b02_first_time_user_journey`** walks the whole B02 flow and checks each
step against the backend:
- **Landing and projects:**
  - the landing CTA opens the real B02 project;
  - project rows equal `/v1/projects`, with no duplicates and truthful readiness.
- **Assembly and target:**
  - tree IDs equal the revision inventory;
  - the viewport loads the backend BRep tessellation (metres,
    `scale_already_applied`, never rescaled);
  - orbit, zoom and Reset change and restore the render, and selection
    highlights;
  - the baseline request carries `target_id` and the constraint hash.
- **Analysis and redesign:**
  - the confirmed obstruction IDs shown are the backend's;
  - the redesign outcome, candidate states and decision-policy label match the
    run record;
  - rejected candidates cannot reach review.
- **Comparison and playback:**
  - the comparison renders both models;
  - its check counts equal the verification record;
  - route playback moves along the verified Z+ step and stops at its bounds.
- **Acceptance and export:**
  - acceptance posts the candidate's input hash and is recorded;
  - export is created by the backend and downloaded by the browser.

The other tests:

| Test | Proves |
|---|---|
| `test_genuine_step_and_manifest_upload…` | A STEP and manifest made with the repo's fixture tool, under a new project ID, upload through the file input, import, and open with matching tree, label and preview. The input hash equals an independent import of the same bytes. |
| `test_invalid_packages_are_rejected…` (4 cases) | An STL and a STEP without manifest are refused client-side, with no request sent. An unparseable STEP and an invalid manifest are refused by the server. No project is created in any case. |
| `test_missing_backend…` | A bundle pointed at a closed port shows "Cannot reach the UNLOCK engineering service", the unreachable state and no example data, on Projects and in a workspace. |
| `test_unavailable_model…` | `AI_PROVIDER=meta` without credentials is labelled "credentials missing" before the run, and ends `MODEL_UNAVAILABLE` with no candidates and no verified claim. |
| `test_cancelled_redesign…` | Cancel stops the backend job (`cancelled`); nothing is accepted or exportable. |
| `test_offline_interval_mid_job…` | The browser goes offline for 4 s mid-redesign, and a request made meanwhile fails. The backend outcome still arrives, with exactly one redesign request. |
| `test_reload_restores…` | A reload restores the persisted run without any POST. Export stays disabled, and the API refuses it until acceptance. A run from another revision is never applied. |
| `test_pages_fit_and_name_their_controls` (3 sizes) | At 1600 × 1000, 1366 × 768 and 390 × 844: no horizontal overflow; the desktop workspace is exactly one viewport tall; every visible control has an accessible name; keyboard focus is visible; the CAD scene renders. |

Console, page and network errors must all be empty for the run. The one named
exception is the download link's navigation, which Chrome reports as
`ERR_ABORTED` once it becomes a download; its bytes are verified separately.

## Export package validation (final run)

| Check | Result |
|---|---|
| Downloaded bytes | SHA-256 `52cce6dded18e746…`, which equals the content-addressed artifact ID and the API's bytes |
| Contents | Exactly the 14 files listed in `bundle.json`, plus `bundle.json`; every SHA-256 matches |
| Status | `full_assembly`, STEP round trip `passed` |
| Identity | One candidate ID across `bundle.json`, `verification.json`, `template_parameters.json` and `paths.json`; the original revision and constraint hash equal the workspace's |
| Route | `paths.json` steps equal the verified plan: target Z+ 80 mm, feasible, replacement verified |
| Provenance | `ai_run.json` records `live_model=false` and `offline_fake_provider` |
| Hygiene | No API key, `MODEL_API_KEY`, `/Users/` paths or bearer tokens in any file |
| Independent STEP reimport | `original.step` and `revised.step` reimported through the production worker: 8 occurrences each, all ready. The bridge volume change, 1,152.0 mm³, equals the recorded removed volume, and every other part is unchanged. |

## Defects found and fixed

| Commit | Defect |
|---|---|
| `c3b49c1` | Under `AI_PROVIDER=mock` the redesign panel said "Configured live model: Muse Spark 1.3". The projects page said "Connected" with no backend, and filed the outage under "Package not accepted". |
| `86a3b40` | Export used a delayed `window.open` that popup blockers swallow; it's now a plain download link. The package list named 9 of 15 files. |
| `bcce1d9` | All landing calls to action linked to `/projects/prj_b02`, which doesn't exist in the default HTTP mode. |
| `4286b4c` | A visually hidden caption escaped the panel scroller and grew the page to about 2,300 px. Provenance timestamps were clipped, and panels kept the previous step's scroll position. |
| `40813e3` | A reload lost all completed work; runs are now restored from `?run=`. |
| `80943e5` | Dragging to orbit the camera selected the part under the pointer. |
| `5350127`, `507a74e` | The side-by-side comparison clipped the assembly at 1366 px, and a phone callout ran off-screen. |

## Measured timings (final run, offline scripted policy)

| Step | Time |
|---|---:|
| Landing load (DOMContentLoaded) | 0.13 s |
| Projects list | 0.80 s |
| Open B02 to rendered BRep | 1.55 s |
| Baseline request accepted | 0.05 s |
| Baseline to visible result | 7.98 s |
| Redesign to visible verified outcome | 18.41 s |
| Comparison render (two canvases) | 1.50 s |
| Checked export to download link | 9.86 s |
| Genuine upload to rendered workspace | 3.87 s |
| Coordinator ready with 3 bundled fixtures | 10.8 s |

The redesign's own run record breaks its time down as follows:
- **Total:** 18.08 s.
- **Stage A:** import 3.5 s and baseline 4.1 s.
- **Native geometry:** 18.1 s, overlapping the stages above.
- **Decision policy:** 6 ms. It's an offline script, so no model latency exists in
  this run and none is invented.

The journey made 23 API calls, with no retries.

## Limitations

- **Decision policy:** the browser suite uses the offline scripted policy. Live
  Muse behaviour is covered by `LIVE_B02_REDESIGN.md`, not by this suite.
- **Severed event stream:** Chromium keeps an open loopback event stream alive
  under offline emulation, so a severed stream isn't exercised in the browser. SSE
  resume is covered in `test_api`.
- **Phone layout:** phone widths show a stacked workspace that works for reading.
  Full CAD editing is intended for screens of 1280 px and wider, and the UI says
  so.
- **Assemblies covered:** one synthetic fixture (B02) end to end, plus one genuine
  upload of a synthetic B01 package. No industrial assembly is implied.
- **Frontend unit tests:** there is no frontend unit-test framework. Frontend
  behaviour is covered by these browser tests, TypeScript and the production
  build.
