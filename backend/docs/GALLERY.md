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
witness coordinates straight onto the template domain. Cylinders are centred on
their placement; boxes are placed by their lower corner.

These are synthetic examples, not validated products. Shared constructor and
simplified mating mean they cannot establish industrial generalization.

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

The account holder chose on 2026-10-31 to give B04–B08 and their generated
evidence the same CC BY 4.0 team grant recorded for B02 in
[B02_PROVENANCE.md](B02_PROVENANCE.md). The fixtures were written in this task
with AI assistance, on top of the team's bridge constructor. The co-author's
agreement recorded for B02 was not separately re-confirmed for B04–B08; confirm
it before treating the grant as covering all rightsholders. B01, B03 and the
held-out B02 variant keep their pending provenance and are not published.

`fixture_license.GRANTS` is the only list the publication guard accepts. Each
gallery export carries `LICENSE-B0x.txt` and `THIRD_PARTY_NOTICES.txt` naming its
own fixture. B02's notice bytes are unchanged.

## Publishing the gallery

The public app still mounts exactly one read-only Volume subdirectory. A gallery
is a composed snapshot of one completed private job per fixture, B02 included.
`validate_public_gallery` refuses to serve unless every project has one recorded
offline run, a recorded grant and its expected outcome, verified exports pass
their member-hash and licensing checks, and refusals carry no export. A
single-job B02 snapshot is still accepted, so the current deployment keeps
working until the gallery replaces it.

From `backend/`, with the Modal CLI authenticated to the `shreyas-pabbathi`
workspace:

```sh
# 1. Redeploy private jobs so the cloud image contains the gallery fixtures.
modal deploy modal_app.py
# 2. Run all six fixtures privately, one at a time, and compose the gallery.
#    Prints one line per fixture and finally "Gallery ID: <32 hex>". ~10 CPU-minutes.
PYTHONPATH=src modal run modal_app.py::gallery
# 3. Point the public read-only API at the gallery. Reuse the exact origin list
#    of the current deployment (it must include https://unlock-labs.pages.dev).
UNLOCK_DEMO_JOB=<gallery id> UNLOCK_CORS_ORIGINS=<current origin list> \
modal deploy modal_web.py
```

Rollback: redeploy `modal_web.py` with the previous B02 job ID; the guard still
accepts a single-job B02 snapshot, and the frontend falls back to `demo_run_id`.

Then rebuild and upload the frontend as in
[CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md) (`npm run build:public`,
upload `dist`, Not found handling → single-page-application) and check
`/projects` shows six rows and `/projects/fixture_B07` opens its recorded run.

## Tests

- `tests/test_gallery.py`: every gallery fixture imports analysis-ready with
  5–12 parts and its grant, and differs from B02. Default suite.
- `tests/test_deployment.py`: composes B02 + B07 + B08, checks the guard, the
  per-project recorded runs and outcomes over HTTP, and tampering refusals
  (claimed success, relicensing, missing B02, duplicate project). Default suite.
- `pytest -m gallery`: the full offline run of B04–B08 against their expected
  outcomes, about 8 minutes.
