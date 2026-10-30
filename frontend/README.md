# UNLOCK frontend

React 19 + TypeScript + Vite, with Three.js through React Three Fiber and Drei. GSAP drives the hero reveal and the scroll story; Lenis smooths landing-page scrolling. Everything else is CSS.

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

## Browser acceptance

`backend/tests/browser` drives this app against a real coordinator in installed
Chrome (`python -m pytest -m browser tests/browser` from `backend/`, after
`npm ci` here). See `backend/docs/BROWSER_ACCEPTANCE.md`.
