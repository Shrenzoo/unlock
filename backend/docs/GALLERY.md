# Fixture gallery: B04–B08

Recorded 2026-10-31. The public demonstration previously showed one assembly,
B02. The gallery adds five original synthetic assemblies with different layouts
and, more importantly, different *answers*: three verified redesigns by three
different means, one case the engine will not certify, and one product that was
already serviceable. Every result below was computed by the same pipeline as
B02 (STEP generation and import, deterministic baseline search, bounded redesign,
independent reconstruction and verification, acceptance, STEP export round trip)
and every outcome is checked against an expectation written before the run.

## The public projects

<!-- measured -->

`fixture_catalog.py` holds each name, description and expected outcome. It
imports no CAD library, so the read-only gateway's publication guard can check
recorded runs against it. Geometry lives in `fixtures.GALLERY`.

## How the layouts differ, and what they share

All five reuse the trusted `bridge_bracket_v1` constructor (the only family with
server-owned edits), so the same verifier, templates and finite domains apply.
What changes per fixture: bracket span, web depth and height, the bound templates
(B05 binds only T02), the cut budget (B06 allows 1,200 mm³), the target's size
and position, the chassis, the surrounding parts and whether screws retain the
target through a declared screwdriver (B07, B08). B08 has no bracket at all.

As in B02, parts float with at least 2 mm clearance (simplified workholding).
Resting parts directly on the base produced tangent contacts the engine refuses
without a declared contact, which is correct behaviour, so the layouts avoid it.
The bracket stays at the world origin because the offline policy maps BRep
witness coordinates straight onto the template domain. Every part is placed by
the lower corner of its bounding box.

These are synthetic examples, not validated products. Shared constructor and
simplified mating mean they cannot establish industrial generalization.

## Detailed geometry (2026-11-01)

The first gallery used plain blocks and cylinders, so the five products looked
alike. `fixture_parts.py` now builds each part as one closed, detailed solid:

| Fixture | Product | Parts beyond target, bracket and screws |
|:--|:--|:--|
| B04 | Pump skid | Slotted chassis with recessed bay; foot-mounted motor with terminal box; horizontal coolant tank on saddles; two bulkhead ports with hex nuts and barbs; controller board |
| B05 | Battery bay | Second module; two saddle racks; monitor board; power connector; bolted fuse carrier; wiring duct |
| B06 | Sensor housing | Rounded housing plate; pedestal mount; cable gland; top-hat rail; signal board; whip antenna; two-cell holder |
| B07 | Relay panel | Shield can over the hatch screw; service bay under the hatch; relay; terminal block; screw standoff |
| B08 | Air purifier | Filter tray; axial fan; vented side walls; control board; power inlet; screw standoffs |

The targets carry detail too (pump head and handle, terminal posts and vents,
lens bezel, counterbored hatch, pleated filter media). The viewer also tints
electronics a darker neutral and fasteners a lighter one, so detail reads without
borrowing the colours that carry evidence. Three rules kept every pre-registered
outcome intact:

- **Targets keep their registered boxes exactly.** The planner certifies motion
  with bounding boxes, so a target's detail lives inside the box its outcome was
  registered with. `tests/test_gallery.py` pins all five.
- **No fixed part's box crosses a moving path.** A box overlapping the upward
  sweep of a target, a screw or the driver turns a certified answer into
  "unknown". Supports stop below the parts they hold (cradles, tray, pedestal,
  standoffs, service bay), and the test checks every fixture.
- **Detail must fit the verifier's time budget.** The redesign loop has 120 s and
  each verifier phase 30 s. Import, verification and preview evaluate exact BRep
  distance for every pair of parts, and that is slow between many parallel flat
  faces (fins, louvers, combs) or parallel cylinders. So repeated detail uses
  few round features, the motor, screws and tank axes differ, and the B07 shield
  is a plain can. The first detailed draft was too heavy: B04 and B05 ran out of
  time and ended `INCOMPLETE_ANALYSIS`, and the runner refused to record them.

Two outcomes are time-sensitive by construction, so their fixtures stay lighter.
B04 must verify its second relief inside the 120 s budget. B07 must finish its
second verification with more than 10 s left, or the toolbox withholds a retry,
the scripted policy stops, and the run records `NO_VERIFIED_IMPROVEMENT` instead
of `INCOMPLETE_ANALYSIS`. A 12-part B07 did exactly that once, at 116 s, during a
full test run on a busy machine; the 10-part B07 finished that verification at
78 s under a load average of 15 to 20 on 10 cores.

Final geometry, and `pytest -m gallery` times on this Mac while other applications
kept the load average between 9 and 28 (the engine is single-threaded; Modal
previously ran these jobs within about 10% of an idle local run):

| Fixture | Parts | Faces | Preview triangles | Job | Outcome |
|:--|--:|--:|--:|--:|:--|
| B04 | 10 | 277 | 30,160 | 152 s | Verified improvement (second relief) |
| B05 | 12 | 400 | 31,268 | 150 s | Verified improvement (strap moved) |
| B06 | 11 | 286 | 31,142 | 116 s | Verified improvement |
| B07 | 10 | 215 | 20,914 | 99 s | Incomplete analysis (turn budget) |
| B08 | 12 | 396 | 37,046 | 57 s | No supported candidate (3-step route) |

The first gallery had 39 to 64 faces per fixture and about 2,000 to 3,600 preview
triangles. B02 is the team's own licensed geometry and is unchanged.

## Corrections made on the way, recorded rather than hidden

- **B05 first run:** offset +12 mm failed with `GEOMETRY_FAILED: native
  operation timed out`, then +24 mm verified on the last allowed candidate. The
  timeout coincided with a parallel `npm ci` and TypeScript build on the same
  machine. The pipeline correctly refused to count it. Because a result that
  depends on machine load is fragile on Modal's single CPU, the pack was moved so
  the first offset tried (−12 mm) verifies with a 4 mm gap.
- **B07 expectation:** first registered as `NO_VERIFIED_IMPROVEMENT`. The run
  ended `INCOMPLETE_ANALYSIS`: the verifier rejected two bracket edits with
  `screw1 Z+ TOOL_ACCESS_BLOCKED`, and the controller's fixed 6-turn budget
  stopped before the third constructed candidate could be checked. The geometry
  prediction was right; the budget prediction was wrong. The expectation was
  revised to the honest recorded outcome, and the catalog says so.
- **B08 first layout:** screws 6 mm from the cartridge made the screwdriver
  handle's conservative box overlap the cartridge's. Exact BRep poses found no
  collision, so the move was reported `unknown` and the baseline stayed
  `incomplete`. Screws moved to x = ±32 mm, giving the handle box 4 mm of
  clearance; the route is now certified.

In each case the job runner refused to complete because the recorded outcome
differed from the expectation. Nothing was relabelled.

## Rights

Recorded 2026-10-31. This is the account holder's authorization record, in the
same form as [B02_PROVENANCE.md](B02_PROVENANCE.md); it is not an independent
legal title search.

The account holder chose on 2026-10-31 to release B04–B08 and their generated
demonstration evidence under the team's CC BY 4.0 grant, and then reported that
**written authorization from the relevant contributors** had been obtained for
that public release. The written authorization is held privately by the UNLOCK
team. Its correspondence and signatures are deliberately not stored in this
repository, its evidence or any export; this record states only that it exists.

The fixtures were written in this task with AI assistance, on top of the team's
bridge constructor; no third-party CAD or geometry was imported. Attribution
follows B02: "the UNLOCK team (Shreyas Pabbathi and his brother)", source
`https://github.com/Shrenzoo/unlock`, with the generating call and seed. B01,
B03 and the held-out B02 variant keep their pending provenance and are not
published.

Where the licensing information appears:

- **Every published revision** carries the grant in its manifest `provenance`
  (author, `CC-BY-4.0`, source), served by `/v1/revisions` and in the
  downloadable `manifest.json`.
- **Verified exports** (B02, B04, B05, B06) contain `attribution.txt`,
  `LICENSE-B0x.txt` and `THIRD_PARTY_NOTICES.txt` in their hashed inventory, and
  `limitations.txt` names the license file instead of "rights pending".
- **B07 and B08** have no export, since no revised geometry was verified. Their
  original STEP, manifest and preview are published with the manifest grant.

`fixture_license.GRANTS` is the only list the publication guard accepts. The
guard compares each export's notice bytes with `license_files` and refuses a
gallery export whose `limitations.txt` does not state its license. B02's notice
bytes are unchanged. The single-job B02 snapshot deployed before the gallery
still says "rights remain pending" in `limitations.txt`; the regenerated B02 in
the gallery corrects that.

## Publishing the gallery

The public app still mounts exactly one read-only Volume subdirectory. A gallery
is a composed snapshot of one completed private job per fixture, B02 included.
`validate_public_gallery` refuses to serve unless every project has one recorded
offline run, a recorded grant and its expected outcome, verified exports pass
their member-hash and licensing checks, and refusals carry no export. A
single-job B02 snapshot is still accepted, which kept the earlier deployment
working until the gallery replaced it and keeps it available for rollback.

Order matters. The new frontend works against the current single-B02 API (it
falls back to `demo_run_id`, and the Result column shows "—"), so release it
first; switching the API afterwards then has no broken window.

1. Frontend, from `frontend/`: build with the production API origin, then
   upload only the `dist/` contents to the Pages project `unlock-labs`
   (Production). Pages serves the SPA by default because the build has no
   `404.html`; keep `_headers` and `THIRD_PARTY_NOTICES.txt`, and do not add the
   legacy `_redirects` rule.

   ```sh
   VITE_UNLOCK_API=https://shreyas-pabbathi--unlock-demo-web.us-east.modal.run npm run build:public
   ```

2. Modal, from `backend/`, in the separate tooling environment
   (`pip install -r requirements-modal.txt`), authenticated to the
   `shreyas-pabbathi` workspace:

   ```sh
   # Keep the deployed private worker current with the gallery fixtures.
   modal deploy modal_app.py
   # Run all six fixtures privately, one at a time, compose and validate the
   # gallery. Prints one line per fixture, then "Gallery ID: <32 hex>".
   PYTHONPATH=src modal run modal_app.py::gallery
   # Point the public read-only API at the gallery. Reuse the exact origin list
   # of the current deployment (it must include https://unlock-labs.pages.dev).
   UNLOCK_DEMO_JOB=<gallery id> UNLOCK_CORS_ORIGINS=<current origin list> \
     modal deploy modal_web.py
   ```

3. Check `/projects` shows six rows and `/projects/fixture_B07` opens its
   recorded run, then run the production browser test (`UNLOCK_PRODUCTION_WEB`
   and `UNLOCK_PRODUCTION_API` set, `pytest -m browser tests/browser/test_production.py`).

Rollback: redeploy `modal_web.py` with the previous B02 job ID,
`UNLOCK_DEMO_JOB=9ad44594b93d4d0b860e8efda623b2d6`. The guard still accepts that
original single-job snapshot, and the new frontend falls back to `demo_run_id`.

## Release record (2026-11-01)

Released 2026-11-01 from `main` at `15324be` (PR #18), following the steps above.
Raw reports are in [evidence/gallery-release](../evidence/gallery-release/).

**Before.** Cloudflare was still serving an older build (production deployment
`2b20b62e`) without the Result column, and the API served the single B02 job.
The Modal dashboard showed Starter, a $30 usage limit, a $0 spend limit, $29.99
credits and $0 charges before any cloud work, and the same afterwards.

**Frontend.** `npm run build:public` with the production API origin, uploaded as
a zip of `dist/` (21 files) through the dashboard to `unlock-labs`, Production:
deployment `e73c7891`. The served Dashboard chunk is byte-identical to the local
build; `/`, `/projects` and deep links return the app, and the `_headers`
security headers are present.

**Private jobs.** `modal deploy modal_app.py` (no secret, live inference off),
then `modal run modal_app.py::gallery` in ephemeral app
`ap-HgIADuVeVvxOfvKFtR8Mxm`:

| Fixture | Job | Outcome | Time | Export SHA-256 |
|:--|:--|:--|--:|:--|
| B02 | `f30b648b…` | Verified improvement | 67 s | `61e1b25d…` |
| B04 | `0f615938…` | Verified improvement | 99 s | `adacbaa1…` |
| B05 | `22f4428f…` | Verified improvement | 57 s | `b5f41a4c…` |
| B06 | `7ead9ac8…` | Verified improvement | 59 s | `28954fcf…` |
| B07 | `16aca150…` | Incomplete analysis | 54 s | none |
| B08 | `20526da7…` | No supported candidate | 20 s | none |

Every outcome matched its pre-registered expectation; full IDs and hashes are in
`validation.json`. `compose_gallery` validated gallery
`a0de2889d0634a48a1eb8ac879341e9e` before committing it to the Volume.

**Independent check.** The gallery was downloaded from the Volume and validated
locally: the guard accepted all six outcomes; 100/100 reads; 71/71 artifacts
hash-exact; 28/28 write attempts refused; unknown project and artifact,
traversal, foreign origin and foreign host rejected; the four exports carry exact
notice, attribution and rights-line files. A scan of 162 public payloads found no
known credential value. Its only email matches are dependency authors already in
`THIRD_PARTY_NOTICES.txt`, and its only "signature" match is three.js code.

**Public API.** `modal deploy modal_web.py` with that gallery and the unchanged
origin list `https://unlock-labs.pages.dev,https://unlock-demo.unlock-labs.workers.dev`.
`/health` reports read-only, mock provider, no credentials and one recorded run
per project; a foreign origin and an anonymous POST both get 403.

**Acceptance.** `tests/browser/test_production.py` against the live URLs:
3 passed. A separate read-only pass opened all six projects: each table row and
workspace shows the API's recorded outcome and run, the part tree matches the
API, and only GET requests were made, on desktop and mobile. Each workspace
was also checked in a real Chrome window and renders its BRep model.

**Cost.** Modal's metered summary (preliminary and unrounded) attributes
$0.00788871 to the ephemeral gallery run; deployed apps rose by $0.00077994
over the release. The amount billed was $0.00. No Modal containers were left
running.

## Tests

- `tests/test_gallery.py`: every gallery fixture imports analysis-ready with
  5–12 parts and its grant, and differs from B02. Each target keeps its
  registered box, no fixed part's box crosses a moving or driver path, and each
  fixture carries at least 200 faces. Default suite.
- `tests/test_deployment.py`: composes B02 + B07 + B08, checks the guard, the
  per-project recorded runs and outcomes over HTTP, and tampering refusals
  (claimed success, relicensing, missing B02, duplicate project). It also proves
  B02 export wording without the CC BY 4.0 rights sentence is refused inside a
  gallery yet still valid as the original standalone B02 snapshot. Default suite.
- `pytest -m gallery`: the full offline run of B04–B08 against their expected
  outcomes, about 8 minutes.
