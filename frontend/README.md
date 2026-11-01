# UNLOCK frontend

React 19 + TypeScript + Vite, with Three.js through React Three Fiber and Drei. GSAP drives the hero reveal and the scroll story; Lenis smooths landing-page scrolling. Everything else is CSS.

Public read-only B02 demonstration: <https://unlock-labs.pages.dev>. The previous
Workers URL redirects here, including workspace paths and query parameters.
Its Modal API serves recorded CAD results from an offline scripted decision policy.
Anonymous uploads and engineering mutations are disabled. Judges can enter a
private code on Projects to upload supported CAD packages for bounded fresh
offline analysis. Live AI inference remains disabled. See the
[judge access report](../backend/docs/JUDGE_ACCESS.md) for session ownership, quotas
and actual cloud/browser verification, and the
[launch report](../backend/docs/CLOUDFLARE_DEPLOYMENT.md) for licensing, usage,
production browser evidence and deployment settings.
The [initial UI presentation update](docs/UI_POLISH.md) records the noise field
and matching favicon. The current [spacious reference design](docs/REFERENCE_DESIGN.md)
records larger sections, continuously visible idle motion and CAD framing.
The [atmospheric lighting correction](docs/ATMOSPHERIC_LIGHTING.md) replaced
ribbons with irregular cloud lighting while verifying that every measured layout
position and the existing CAD interactions are preserved. The later
[story zoom correction](docs/STORY_ZOOM.md) makes the model grow throughout scrolling.
The background now reproduces the reference design's light strokes: its interface was
erased into two plates (`design/build_field_plates.py`, from `design/field-reference.webp`)
that a small WebGL shader (`src/landing/lightField.ts`) lays behind the unchanged section
layout, with slow drift and measured film grain. Without WebGL, CSS shows the same plates.
The [model layout refinement](docs/MODEL_LAYOUT.md) enlarges both landing assemblies
and places the larger condensed hero headline at the lower left, preserving that field.
The [scroll performance and Pages release](docs/SCROLL_PERFORMANCE.md) records the
optimized animation work, production checks and current hosting configuration.

```bash
npm install
npm run dev        # http://localhost:5183
npm run build      # type-check + production build
```

By default the app talks to the local FastAPI coordinator at `http://127.0.0.1:8000`;
set `VITE_UNLOCK_API` to use another origin (it is baked in at build time). The
bundled illustrative fixture runs only with `VITE_UNLOCK_MODE=fixture`, and every
record it shows is labelled illustrative.

## Routes

| Path | What it is |
| --- | --- |
| `/` | Landing: illustrative hero assembly, five-step scroll story, scope |
| `/projects` | Projects from the coordinator, engine connection state, package import |
| `/projects/fixture_B02` | Engineering workspace on the computed B02 fixture (`prj_b02` in fixture mode) |
| `/projects/<id>?run=<run id>` | The same workspace restored to a persisted run after a reload |

## Layout

```
src/
  domain/types.ts        contracts mirrored from PRD §20 (manifest, plan, proposal, verification, events, errors)
  api/                   UnlockApi interface, fixture adapter, HTTP/SSE adapter
  fixtures/b02.ts        hand-authored illustrative data, provenance.kind = 'illustrative'
  three/                 procedural B02 assembly (constructor v1 dimensions), studio light, label projector
  landing/               hero, scroll story timeline, sections
  app/dashboard/         project entry and package validation
  app/workspace/         state model, tree, viewport + compare, evidence panels
  ui/                    logo, evidence tags (result and provenance rules)
```

## Connected to the backend (default)

- `api/httpApi.ts` implements the coordinator's `/v1` endpoints, including
  `POST /v1/runs/{id}/redesign`, plus `GET /health` for the configured decision
  policy (offline scripted, live model, or credentials missing).
- `app/workspace/LiveViewport.tsx` renders the backend's BRep tessellation
  (`preview.json`, already in metres; units are checked and never scaled twice).
  Playback interpolates the verified plan's `start_mm`/`end_mm` per step.
- Export is created by the backend (reconstruction, replanning, STEP reimport)
  and then offered as a plain download link to the content-addressed ZIP.
- `ui/Evidence.tsx` decides how results are drawn; the decision-policy label in
  the Redesign panel never calls the offline scripted policy inference.

## What is illustrative

The landing page's hero and story (`three/ModuleAssembly`, `fixtures/b02.ts`) are
presentation geometry and say so. In fixture mode every number, check and event
comes from `fixtures/b02.ts`; import, review decisions and export throw
`ServiceNotConnected`, and the UI says so.

## Cloudflare static deployment

Build from this directory with the actual backend origin:

```bash
VITE_UNLOCK_API=https://shreyas-pabbathi--unlock-demo-web.us-east.modal.run \
VITE_UNLOCK_JUDGE_API=https://shreyas-pabbathi--unlock-judges-web.us-east.modal.run npm run build:public
```

Upload only the contents of `dist/` to the existing **Pages** project
`unlock-labs`, selecting Production. Pages supplies SPA fallback when the build
has no top-level `404.html`. Keep `_headers`, `favicon.svg` and dependency notices
in the upload. No Functions, runtime secrets or paid services are needed.

The judge API is separately deployed with its code hash in a server-side Secret.
Never put the code, session token or any Modal/API token in a VITE variable.
The public API's exact CORS origins include `https://unlock-labs.pages.dev`; its selected
B02 job remains unchanged. Public builds reject localhost, missing or
credential-bearing API URLs and illustrative fixture mode.

`wrangler.jsonc` describes the former Workers Static Assets deployment, which
now only redirects to Pages. Do not upload the app there for future releases.
For that legacy redirect, the separately uploaded `_redirects` contains
`/* https://unlock-labs.pages.dev/:splat 301`. Never include that rule in the
Pages build itself.

## Browser acceptance

`backend/tests/browser` drives this app against a real coordinator in installed
Chrome (`python -m pytest -m browser tests/browser` from `backend/`, after
`npm ci` here). See `backend/docs/BROWSER_ACCEPTANCE.md`.
