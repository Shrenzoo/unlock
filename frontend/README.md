# UNLOCK frontend

React 19 + TypeScript + Vite, with Three.js through React Three Fiber and Drei. GSAP drives the hero reveal and the scroll story; Lenis smooths landing-page scrolling. Everything else is CSS.

```bash
npm install
npm run dev        # http://localhost:5183
npm run build      # type-check + production build
```

Set `VITE_UNLOCK_API=https://your-coordinator` to switch from the bundled fixture to the FastAPI adapter.

## Routes

| Path | What it is |
| --- | --- |
| `/` | Landing: hero assembly, five-step scroll story, workspace preview, scope |
| `/projects` | Project list, package checks, supported-assembly contract |
| `/projects/prj_b02` | Engineering workspace: Inspect, Analyze, Redesign, Compare, Export |

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

## Integration points waiting for the backend

- `api/httpApi.ts` implements every endpoint in PRD §20 plus one proposed endpoint, `POST /v1/runs/{id}/redesign`, that splits the redesign job from the baseline job. Agree on it with the backend owner.
- `ModuleAssembly` renders procedural presentation geometry. Real imports will deliver a GLB with occurrence IDs; swap the part builders for a node lookup by ID and keep the `AssemblyView` contract.
- Playback interpolates linearly between `Step.start_mm` and `end_mm`. Real plans should send per-step transforms in the same units.
- `ui/Evidence.tsx` is the single place that decides how a result is drawn. Green appears only when `provenance.kind` is `live` or `computed_earlier`.

## What is illustrative

Every number, check and stage event comes from `fixtures/b02.ts`. Nothing was computed by a planner, geometry kernel or model. Import, review decisions and export throw `ServiceNotConnected`, and the UI says so.
