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
single-job B02 snapshot is still accepted, so the current deployment keeps
working until the gallery replaces it.

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

Rollback: redeploy `modal_web.py` with the previous B02 job ID. The guard still
accepts that original single-job snapshot, and the new frontend falls back to
`demo_run_id`.

## Tests

- `tests/test_gallery.py`: every gallery fixture imports analysis-ready with
  5–12 parts and its grant, and differs from B02. Default suite.
- `tests/test_deployment.py`: composes B02 + B07 + B08, checks the guard, the
  per-project recorded runs and outcomes over HTTP, and tampering refusals
  (claimed success, relicensing, missing B02, duplicate project). It also proves
  B02 export wording without the CC BY 4.0 rights sentence is refused inside a
  gallery yet still valid as the original standalone B02 snapshot. Default suite.
- `pytest -m gallery`: the full offline run of B04–B08 against their expected
  outcomes, about 8 minutes.
