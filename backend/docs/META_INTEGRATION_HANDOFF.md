# UNLOCK direct Meta integration — engineering handoff

Executed locally on October 29, 2026, on `codex/meta-model-api-integration`.
This is a local working integration. **Live Meta inference remains unverified
until the gated tests run with a real key.** The demonstrated redesign used an
explicitly labeled scripted offline provider with the real engineering services.

## A — What was implemented

The existing controller, CAD engine, planner and verifier were retained. A direct
Meta adapter uses the official Python SDK against Chat Completions. Configuration
loads `backend/.env` deterministically; deployment environment variables override
it. Meta is the default live provider. Fireworks/Together remain explicit
alternatives; the mock policy is available only through explicit selection.

The adapter preserves assistant tool calls and correlated results, supports
multiple calls, rejects malformed responses/model substitution and normalizes
errors without reflecting raw provider errors or secrets. SDK retries are off;
the controller owns bounded retries. Async HTTP enforces an absolute timeout and
active cancellation. Cost remains unavailable without a sourced operator tariff;
no account balance or pricing is inferred.

Controller hardening reserves output tokens before **every attempt**, retaining
that reservation for failed or unreported requests. The public limits cannot be
raised: 3 candidates, 12 tools, 6 turns, 16,000 billed output tokens, 120 seconds,
and one schema repair. Plain text without an established outcome gets one
bounded clarification; it never becomes a fabricated tool call. Cancellation and
zero-inference runs have accurate outcome/provenance labels.

A local FastAPI coordinator provides import, immutable revisions, frozen-target
baseline runs, redesign, candidate evidence, append-only review, checked export,
content-addressed downloads, ordered/resumable SSE and cancellation. SQLite
persists records with foreign keys and marks interrupted jobs after restart.
One serial queue coordinates bounded native subprocesses; credentials are removed
from their environments. Actual meshes come from BRep tessellation in workers.

React now connects locally by default. Tree/canvas selection use actual occurrence
IDs; baseline and redesign fetch authoritative results, including negative and
unavailable outcomes. Candidate views render actual T01/T02 constructed meshes,
comparison metrics belong to the selected candidate, and checked playback uses
saved transform differences. Project/target generation guards prevent late
responses from restoring stale results. The layout and landing visual design
are preserved. Illustrative mode remains explicit and visibly labeled.

## B — Meta API configuration

Add your key to **`/Users/shreyaspabbu/Documents/Upload_hackathon/backend/.env`**.
A placeholder-only file has been created locally; the committed template is
[`../.env.example`](../.env.example). Do not copy credentials into `frontend/`.

```dotenv
AI_PROVIDER=meta
MODEL_API_KEY=YOUR_REAL_META_KEY
META_MODEL=muse-spark-1.3
META_BASE_URL=https://api.meta.ai/v1
META_REASONING_EFFORT=medium
RUN_META_LIVE_TESTS=0
```

Restart the backend after changing its configuration. `high` effort is available
through `META_REASONING_EFFORT`; no higher effort is chosen automatically.
Environment files are ignored at every depth; only examples are included in Git.
Ordinary pytest excludes paid tests even when a key exists. Live test commands
also require `RUN_META_LIVE_TESTS=1`. Interactive redesign requests use the
configured provider; clicking Request redesign with a key performs real inference.

The current model is **Muse Spark 1.3**, not Muse Spark Open. The later explicit
request supersedes the PRD's original Fireworks/Open provider choice. Protocol
settings follow Meta's [overview](https://dev.meta.ai/docs/overview),
[tool-calling guide](https://dev.meta.ai/docs/tool-calling) and
[reasoning guide](https://dev.meta.ai/docs/reasoning), checked October 29, 2026.
In particular, Chat Completions uses `tool_choice="auto"`; no forced tool choice,
OpenAI-only response format, sampling, log-probability or agent-framework
parameters are added. Pricing must be sourced from the operator's current account.

## C — Tool calling

All eight allowlisted tools retain real domain implementations:

| Tool | Actual source |
|---|---|
| inspect_assembly | Validated manifest and measured native inventory |
| inspect_constraints | Frozen constraints, regions, keep-outs and template bounds |
| analyze_removal | Deterministic Stage A PlanResult |
| inspect_blocker | Rejection certificates and actual BRep findings |
| list_interventions | Server template domains intersected with the manifest |
| construct_candidate | Trusted T01/T02 constructor in an isolated worker |
| verify_candidate | Fresh reconstruction, independent static checks, planning, replay and reverse insertion |
| compare_candidates | Planner comparison under the same target and frozen policy |

No generic shell, Python, URL, filesystem, acceptance or release tool is exposed.
Arguments reject extra fields, invalid/stale IDs, unsupported templates and
out-of-domain parameters. Imported metadata remains untrusted. HTTP imports use
the same tool-compatible identifier alphabet (`A–Z a–z 0–9 _ . : -`, up to 96
characters) for project/component/constraint IDs; unsupported identifiers fail
before native parsing. The router encodes/decode opaque supported IDs.

## D — Engineering integration and observed demonstration

The model receives compact structured evidence, never raw STEP files. The CAD
constructor changes one bracket occurrence. Independent verification reconstructs
it from the frozen parameters; model-supplied pass flags are never accepted.
Comparison requires passing mandatory checks, supported removal, independent
forward replay and reverse restoration. An infeasible original has undefined
operation counts; no zero baseline or percentage is invented.

The real B02 demonstration, using the explicitly offline policy:

1. Import the genuine synthetic STEP assembly and select occurrence `target`.
2. Baseline search conclusively returns `no_path_supported`; actual BRep evidence
   identifies the bridge obstruction. Remaining obstacles are not mislabeled
   as confirmed blockers.
3. The scripted provider reads actual witness/domain results and requests a T01
   relief. Its first 24 × 8 mm opening is constructed and rejected by replanning.
4. Feedback drives a different 24 × 12 mm opening at local `(0, -20)`.
5. Independent reconstruction and applicable mandatory static checks pass.
   Revised removal is `target Z+ 80 mm`, cost `(0,0,0,1)`; forward replay and
   reverse insertion pass.
6. The comparison establishes infeasible → feasible. The browser displays the
   actual changed solid and authoritative metrics, records acceptance, then
   requests a checked full-assembly STEP export.
7. Export reconstructs/replans, round-trips STEP and packages the full evidence;
   every file hash in the final ZIP manifest is checked by the integration test.

Full original/revised plans, transforms, certificates, verification checks,
proposal handle mappings, tool records and constructed STEP/preview artifacts
are preserved independently of worker temporary directories. CLI output uses a
content-addressed `artifacts/` directory. The HTTP store uses `.data/` by default.
No candidate from a cancelled, active or superseded run can be accepted or
exported. Export rechecks acceptance both before native work and at commit.

## E — Tests and evidence

See [`../evidence/meta/validation.json`](../evidence/meta/validation.json) for exact
observed commands/counts and [`META_INTEGRATION_AUDIT.md`](META_INTEGRATION_AUDIT.md)
for the untouched starting state. The baseline snapshot passed **220 tests**;
the initial 10 restricted-sandbox HTTP failures were reproduced as socket binding
restrictions and passed with loopback networking allowed.

The final frozen suite passed **267 tests, zero failures**, with **2 paid tests
excluded**, in **243.86 seconds** (17 third-party/test warnings). Ruff, formatting,
dependency consistency and the React production build passed. The explicitly
selected live suite reported **2 skipped** because credentials/flag were absent.

The final verification record separates:

- Offline provider/configuration tests through the actual SDK and an in-process
  HTTP transport; multiple tools, conversation history, invalid JSON, bad usage,
  key errors, 401/402/403/404/429/5xx, model substitution, timeout and cancellation.
- Real controller tests, including rejection/revision, limits, deduplication,
  injection/schema violations, missing key and durable geometry evidence.
- HTTP integration over real CAD: import, baseline, actual redesign, independent
  checks, metrics, acceptance, round-trip export, stale targets/constraints,
  idempotency, SSE resume, cancellation, missing Meta key and restart recovery.
- Existing geometry, planner, template and export regressions.
- TypeScript/Vite production build, Ruff and dependency consistency.
- Headless Chrome through the real local HTTP backend: selection → analysis →
  rejection/revised improvement → comparison → acceptance → checked export;
  explicit offline provider, no model credits, zero browser errors.

Paid tests are marked `meta_live` and excluded by default. Selecting them without
both key and flag reports **skipped**, never live success.

## F — Live results

No successful live Meta request is claimed. During implementation inspection,
`MODEL_API_KEY` was absent and `RUN_META_LIVE_TESTS` was disabled. The saved smoke
report records `status: skipped`, no requests and no token or cost measurements.
The model identifier configured for future live runs is `muse-spark-1.3`.

The offline policy's token counts are synthetic and labeled accordingly. Its
engineering results are actual computations. No model superiority over the
existing geometry-ranked deterministic selector has been established.

## G — Git history

The original working tree contained an entirely uncommitted backend. The first
commit explicitly preserves that preexisting implementation; subsequent commits
represent actual tested integration milestones. No history was backdated or
rewritten, no remote push/merge was performed, and the configured author was used.
The earlier root README and local skill files remain outside these commits.

The integration milestones created before this handoff are:

| Commit | Message | Main modules | Validation at that milestone |
|---|---|---|---|
| c18342f | chore: preserve existing CAD planner and AI controller baseline | Existing backend source/contracts/tests/docs | Untouched baseline: 220 passed |
| 7c56bdf | feat(ai): add direct Meta configuration and secure environment loading | config.py, environment examples, dependencies | 11 configuration tests passed; environment ignore rules checked |
| af83190 | feat(ai): implement cancellable Meta SDK transport and native tool calling | meta.py, provider.py | 15 direct-SDK offline tests passed |
| f7e690d | fix(ai): enforce retry budgets and retain authoritative engineering evidence | controller/session/native/toolbox and report schema | Existing controller 11 passed; 9 new focused cases passed |
| 4c2a199 | test(ai): add gated Meta smoke and real-engine live acceptance tests | smoke/CLI/live tests | 27 configuration/SDK tests passed; live selection explicitly skipped |
| 6ecddf8 | fix(ai): preserve evidence handles and validate provider usage | Controller/provider/smoke regression fixes | 31 configuration/SDK tests passed; resolved full-suite citation regression |
| 5dd4e67 | feat(api): connect persistent jobs to real CAD analysis redesign and export | api/, worker.py, API tests | 7 HTTP/engineering cases passed in the final suite |
| 72bd448 | feat(frontend): display real CAD analysis redesign verification and export | HTTP adapter, workspace, actual mesh viewport | TypeScript/Vite passed; real-service browser acceptance passed |
| 993bac4 | test(integration): preserve reproducible CAD API and browser validation evidence | Validation scripts and evidence/meta | Frozen suite: 267 passed; ZIP/artifact hashes verified; browser passed |

The documentation commit containing this report is recorded in the final delivery
response. Git remains the authoritative complete chronological record:


```sh
git log --reverse --format='%h %s' ba920db..codex/meta-model-api-integration
```

## H — Remaining issues and scope

- **Live Meta tool calling and end-to-end behavior need the gated credentialed
  run.** Offline SDK/protocol and engineering success do not establish live success.
- The server is deliberately local: loopback clients, trusted hosts and explicit
  CORS origins. Public hosting, authentication/project ownership, provider data
  terms and production operational qualification remain separate deployment work.
- Linux/container execution was not tested. The existing Dockerfile is a CLI
  engine image; it is not a validated public HTTP deployment.
- Only the known bridge family, T01/T02, rigid axis translations and annotated
  reusable screws are supported. B01/B02/B03 are synthetic, with simplified
  mating/workholding and pending fixture redistribution approval.
- B03's annotated screw retains the cover, not its default service target. This
  handoff does not claim that its tool-access conflict was resolved; B02 is the
  demonstrated improving redesign.
- No strength, fatigue, torque, electrical safety, manufacturing feasibility,
  restored function or engineering release approval is established.
- The retained stdlib alternate-provider transport has its earlier socket timeout
  behavior. The new primary Meta SDK transport has active cancellation and an
  absolute deadline; provider switching is explicit.

## I — Exact run instructions

From a clean checkout, install the pinned Python 3.12 environment:

```sh
cd /Users/shreyaspabbu/Documents/Upload_hackathon/backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
# Only if backend/.env does not exist:
cp -n .env.example .env
```

Start the backend (terminal 1):

```sh
cd /Users/shreyaspabbu/Documents/Upload_hackathon
backend/.venv/bin/python -m unlock_engine.api --port 8000
```

Start React (terminal 2), then open http://localhost:5183/projects:

```sh
cd /Users/shreyaspabbu/Documents/Upload_hackathon/frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5183 --strictPort
```

B01/B02/B03 import once on first startup. Open B02, select `target`, set it as the
repair target, then Analyze → Run baseline analysis → Explore a redesign →
Request redesign. With the key configured, this last action calls Meta. Without
it, baseline remains viewable and redesign returns Model unavailable.

For a complete, explicitly offline demonstration instead, start terminal 1 with:

```sh
AI_PROVIDER=mock backend/.venv/bin/python -m unlock_engine.api --port 8000
```

The browser reports the scripted provider while running real CAD operations.
To inspect the earlier illustrative UI alone, start Vite with
`VITE_UNLOCK_MODE=fixture npm run dev`; it performs no engineering computation.

Low-cost live protocol check (3 requests at most, no CAD):

```sh
cd /Users/shreyaspabbu/Documents/Upload_hackathon/backend
RUN_META_LIVE_TESTS=1 .venv/bin/python -m unlock_engine.ai smoke --output .work/meta-live/smoke.json
```

Only after smoke passes, run the bounded real model/CAD workflow:

```sh
RUN_META_LIVE_TESTS=1 .venv/bin/python -m unlock_engine.ai demo --fixture B02 --output .work/meta-live/B02
```

Or run both explicitly selected paid pytest acceptance cases:

```sh
RUN_META_LIVE_TESTS=1 .venv/bin/python -m pytest -q -m meta_live tests/test_meta_live.py
```

Offline validation and a reproducible CLI engineering demo:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/python -m pip check
.venv/bin/python -m unlock_engine.ai demo --offline --fixture B02 --output .work/meta-offline
```

Browser acceptance (Python Playwright with installed Chrome, no user profile):
start the backend above with `AI_PROVIDER=mock` and start the frontend, then run:

```sh
cd /Users/shreyaspabbu/Documents/Upload_hackathon
backend/.venv/bin/python backend/scripts/browser_qa.py
```

The test uses the actual HTTP service. Screenshots, the DOM evidence and the
request/error report are written under `backend/.work/meta-validation/browser/`.
The development run used the local webapp-testing skill's server lifecycle helper;
that helper is not required by the checked-in test script.

API discovery is available at http://127.0.0.1:8000/docs. Artifacts are immutable
SHA-256 IDs rather than caller-supplied filesystem paths. Keep local data/evidence
when reproducing a run; deleting `.data/` intentionally removes the local history.
