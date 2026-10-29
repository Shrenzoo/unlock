> Historical October 28 implementation record. The current runtime uses direct Meta Model API / Muse Spark 1.3. See [META_INTEGRATION_HANDOFF.md](META_INTEGRATION_HANDOFF.md) for current configuration, HTTP/frontend integration and validation status.

# Muse Spark Open redesign controller — implementation handoff

Implemented and executed locally on October 28, 2026, on branch
`codex/disassembly-planner` (uncommitted, alongside the earlier geometry and
planner work, which is preserved). **No live Muse Spark Open request has been
made**: `FIREWORKS_API_KEY` is not configured on this machine. Runs marked
*offline* used a scripted fake provider; every construction, verification, plan
and comparison in those runs is real engine output.

## A. Implementation summary

A bounded, tool-using redesign loop over the existing engine:

1. **Stage A (deterministic).** Validated package → isolated import (inventory,
   readiness) → isolated baseline `PlanResult` for the frozen target. Model-free
   exits: incomplete/invalid baseline, a target that already has the minimal
   route `(0,0,0,1)`, or no constructor binding.
2. **Model loop.** Muse receives a compact context (IDs, target bounds, baseline
   status and only the *geometric* rejections) and may call eight allowlisted
   tools. Each call is parsed strictly, identity-checked and executed by a typed
   handler that wraps an existing engine function.
3. **Engineering.** Construction and verification each run in a **fresh isolated
   worker**. Verification independently reconstructs the candidate from its
   trusted parameters, refuses if the reconstructed identity differs from the
   constructed record, runs `verify_candidate(static_only=True)` (every mandatory
   check, fail-closed), then the existing planner: search, forward replay,
   reverse insertion and mandatory route checks.
4. **Final derivation.** The controller re-runs the planner's own `compare_plans`
   for every checked candidate. The outcome comes from that evidence only; the
   model's closing message is recorded with `authority: none`.

Candidate stages stay separate: `PROPOSED → CONSTRUCTED → CHECKED →
VERIFIED_IMPROVEMENT`, or `REJECTED` with structured feedback. Outcomes:
`VERIFIED_IMPROVEMENT_FOUND`, `NO_VERIFIED_IMPROVEMENT`, `NO_SUPPORTED_CANDIDATE`,
`INCOMPLETE_ANALYSIS`, `MODEL_UNAVAILABLE`, `CANCELLED`.

Budgets (PRD §15, monotonic clock, explicit counters): 3 constructed candidates,
12 tool calls, 6 inference turns, 16,000 output tokens (unreported usage is
charged at the requested cap), 120 s including Stage A, 1 schema-repair retry.
Provider retries spend the same time budget and never reset counters. Identical
proposals are deduplicated by revision, constraint hash, policy, template and
normalized parameters; native construction and verification are idempotent by
the same identity, and a repeated `verify_candidate` reports the recorded result
without re-applying it.

Failure feedback categories: `INVALID_PROPOSAL`, `UNSUPPORTED_TEMPLATE`,
`CONSTRUCTION_FAILED`, `CONSTRAINT_FAILED`, `VERIFICATION_UNKNOWN`,
`NO_REPAIR_PATH`, `REVERSE_INSERTION_FAILED`, `STALE_EVIDENCE`, `PROVIDER_ERROR`,
plus `TOOL_NOT_ALLOWED`, `SCHEMA_ERROR`, `DUPLICATE_CANDIDATE`, `BUDGET_EXHAUSTED`.
Each carries candidate, constraint, parameter, measured value, allowed bound,
evidence ID and whether another attempt is permitted. Measured values are copied
from engine records; constructor refusals add exact parameter arithmetic in the
constructor's local frame, labelled as such.

## B. Repository changes

| Path | Purpose |
|---|---|
| `src/unlock_engine/ai/config.py` | Externalized provider config from `UNLOCK_AI_*`; key never in repr, logs or reports |
| `ai/provider.py` | `ModelProvider` protocol, Fireworks/OpenAI-compatible adapter (stdlib HTTP), error normalization, `FakeProvider` |
| `ai/smoke.py` | Live smoke test: 3 requests, harmless `add_integers` tool, check-by-check report |
| `ai/schemas.py` | Strict tool argument models, `Feedback`, failure categories, outcomes |
| `ai/session.py` | Stage A, run `Deadline`, idempotent cached native construct/verify |
| `ai/native.py` | Worker-side `ai_construct` / `ai_verify` |
| `ai/toolbox.py` | Allowlisted dispatcher, evidence handles, the eight handlers, budgets and counters |
| `ai/prompt.py` | Rules-first system prompt and compact Stage A context |
| `ai/controller.py` | Bounded loop, retries, events, outcome derivation, cost estimate |
| `ai/report_schema.py`, `schemas/AIRunReport.schema.json` | Frontend contract; every report is validated before it leaves the controller |
| `ai/baseline.py` | Deterministic selectors `stable_enumeration` (PRD C2) and `geometry_ranked` |
| `ai/evaluation.py` | Frozen cases and oracles, per-run summary, aggregate table |
| `ai/demo.py` | Labelled offline scripted provider (not Muse) |
| `ai/__main__.py` | CLI: `smoke`, `demo`, `eval`, `schema` |
| `src/unlock_engine/worker.py` | **Only engine edit:** dispatch `ai_construct`/`ai_verify` to `ai.native`; 180 s CPU cap for `ai_verify`, as for `plan` |
| `README.md` | Integration row and scope sentence updated |
| `tests/test_ai_provider.py`, `test_ai_toolbox.py`, `test_ai_controller.py`, `ai_helpers.py` | Offline tests |

Recorded differences from the PRD and the adjustments made:

- The worker accepted a fixed operation list. Two AI operations were added rather
  than running OCCT in the controller process.
- `Problem(candidate=…)` keeps only the static report ID when static
  verification fails, so `ai_verify` runs `verify_candidate` first to return
  per-check evidence, then `Problem` (which repeats the static check).
- The frontend contract splits baseline and redesign into two jobs. The engine
  has no HTTP layer; the proposed `POST /v1/runs/{id}/redesign` must be agreed
  with the coordinator.
- The model sees short run-scoped handles (`rev_`, `rej_`, `plan_`, `cand_`,
  `ver_`, `ev_`) mapped to full SHA-256 identities; reports keep the full hashes.
- `target_id` is optional on the two inspection tools; when present it must equal
  the frozen target.

## C. Provider configuration

| Setting | Value / variable |
|---|---|
| Model | `accounts/fireworks/models/muse-spark-open` (`UNLOCK_AI_MODEL`) |
| Provider / base URL | Fireworks, `https://api.fireworks.ai/inference/v1` (`UNLOCK_AI_PROVIDER`, `UNLOCK_AI_BASE_URL`) |
| Credentials | `FIREWORKS_API_KEY`, server environment only |
| Reasoning effort | `medium` by default; `high` via `UNLOCK_AI_REASONING_EFFORT`; `xhigh` only when set explicitly |
| Client | Python standard-library HTTP against the documented OpenAI-compatible `/chat/completions` with native `tools`/`tool_calls`. Chosen so the pinned lockfile is unchanged; the `ModelProvider` interface accepts an SDK transport |
| Timeouts / retries | `UNLOCK_AI_REQUEST_TIMEOUT_S` (45), `UNLOCK_AI_MAX_RETRIES` (2); `Retry-After` honoured; never past the run deadline |
| Prices | None by default. `UNLOCK_AI_PRICE_PRESET=prd_cited_2026_10_27` opts into the PRD-cited figures (labelled unverified), or set `UNLOCK_AI_PRICE_INPUT_PER_MTOK`, `_OUTPUT_PER_MTOK`, `_CACHED_INPUT_PER_MTOK`, `_SOURCE`, `_RETRIEVED_AT` |
| Fallback | Together only with `UNLOCK_AI_PROVIDER=together` and an explicit `UNLOCK_AI_MODEL`, after its own smoke test. Never automatic |

A response naming a different model raises `MODEL_UNAVAILABLE`: no silent
substitution. `reasoning_content` is never stored or replayed.

## D. Tool integration

| Tool | Connected to |
|---|---|
| `inspect_assembly` | Validated manifest and isolated-import inventory (bounds, volume, geometry hash); imported names only under `untrusted_text` |
| `inspect_constraints` | Frozen manifest constraints, regions, keep-outs, envelope, binding minima; read-only |
| `analyze_removal` | Stage A `isolated_plan` `PlanResult` (labelled as computed in Stage A) |
| `inspect_blocker` | Baseline rejections and their witness certificates (actual BRep findings) |
| `list_interventions` | `templates.SERVER_DOMAINS` ∩ manifest binding domains |
| `construct_candidate` | `templates.admit` in the controller, then `service.construct_candidate` in an isolated worker |
| `verify_candidate` | Fresh worker: reconstruction, `verification.verify_candidate`, `Problem` + `plan_problem` |
| `compare_candidates` | `planning.service.compare_plans` on service-produced records |

All eight are connected to real engine services; none return hardcoded results.

## E. Demonstration (offline, labelled)

`python -m unlock_engine.ai demo --offline --output .work/ai-demo`, evidence in
`evidence/ai/offline_demo_run.json` and `offline_demo.txt`. The provider is the
**scripted offline policy in `ai/demo.py`, not Muse Spark Open**; it reads real
tool results and derives each proposal from the witness and the server domain.
Every engineering result below is real engine output.

| Step | Result |
|---|---|
| Assembly | Synthetic fixture B02, 8 occurrences, genuine AP214 STEP |
| Target | `target` (service module), removal axis Z+ |
| Baseline | `no_path_supported`, search complete; BRep witness `target ∩ bridge`, 640 mm³ at (0, −20, 36) after 13 mm |
| Proposal 1 | T01 `{center_x 0, center_y −20, width 24, depth 8}` |
| Result 1 | Constructed; replanning still blocked: `INSUFFICIENT_CLEARANCE` (an 8 mm cut over an 8 mm target leaves less than the 0.5 mm policy gap) → `REJECTED`, `NO_REPAIR_PATH` feedback |
| Proposal 2 | T01 `{0, −20, 24, 12}`, citing the rejection and plan evidence |
| Result 2 | Constructed; independent reconstruction and static verification passed; revised plan feasible, replay passed, reverse insertion passed, cost `(0,0,0,1)` |
| Decision | Planner comparison: infeasible → feasible. `VERIFIED_IMPROVEMENT_FOUND` |
| Run | 6 turns, 7 tool calls, 2 candidates, 30.7 s wall. Token counts in this run are synthetic (fake provider) and labelled so in the report |

## F. Test results

| Command (from `backend/`) | Outcome |
|---|---|
| `.venv/bin/python -m pytest -q` (before this work) | 177 passed, 0 failed, 79.3 s |
| `.venv/bin/python -m pytest -q` (final) | **220 passed, 0 failed**, 169.2 s — `evidence/ai/pytest.txt`, `pytest.xml` |
| `.venv/bin/ruff check src tests scripts` / `ruff format --check` | Clean — `evidence/ai/ruff.txt` |
| `python -m unlock_engine.ai smoke` | **Skipped: no credentials. Live integration is unverified.** |

All 43 new tests are offline. `test_ai_provider.py` (13) drives the real HTTP
adapter against a local stub: request shape, native tool calls, usage, 401/402/
404/429/5xx/400, `Retry-After`, timeout, malformed/empty/non-JSON responses,
model substitution, missing credentials, key redaction and the smoke sequence.
`test_ai_toolbox.py` (19) covers the allowlist and adversarial inputs: invented
approve/export/shell/HTTP tools, extra fields, malformed JSON, URLs in IDs,
foreign project/occurrence IDs, stale revision, target switching, fabricated
evidence, out-of-domain dimensions, injected component names, request-ID reuse.
`test_ai_controller.py` (11) runs the controller on the real engine: a failed
candidate followed by a revised verified one, all candidates failing with
duplicate and budget refusals plus a false success claim, schema-repair
exhaustion, missing credentials, retried timeouts, cancellation, tool and turn
budgets, the accessible-target shortcut, repeated verification, and both
deterministic selectors. The repeated-verification test was confirmed to fail
without its fix.

## G. Evaluation and resource usage

`python -m unlock_engine.ai eval --conditions c2_stable,c2_geometry,muse`; raw
runs and table in `evidence/ai/evaluation.json`. Expected outcomes were frozen
in `evaluation.ORACLES` from the geometry before any run. The Muse condition did
not run (no credentials).

| Case | Expected | `stable_enumeration` (C2) | `geometry_ranked` |
|---|---|---|---|
| B01 accessible | no candidate | ✓ (model-free exit) | ✓ |
| B02 | improvement | ✗ 3 failed candidates | ✓ T01 (0,−20,24,12), 1st candidate |
| B02 held-out | improvement | ✗ | ✓ T01 (−4,−20,40,12) |
| B02 T02 only | improvement | ✓ T02 +24, 3rd candidate | ✓ T02 +24, 1st |
| B02 tight cut | improvement | ✗ | ✓ T01 (0,−20,24,12) |
| B03 | improvement | ✗ | ✓ T01 (0,−20,24,12) |
| B03 cover (tool plate) | no improvement | ✓ honest failure | ✓ honest failure |
| **Correct** | | **3/7** | **7/7** |

Neither rule produced a false success; there were no failed or unknown mandatory
static checks. Median run time 19.2 s (C2) and 12.9 s (ranked); p95 withheld
below 20 samples. No model tokens were used. These are correlated synthetic
variants of one constructor family: no statistical or industrial claim.

**Interpretation.** The geometry-ranked rule sets a high bar: it solves every
supported case on its first candidate. On these fixtures a model can only show
value by matching it with equal or fewer candidates, or by succeeding where the
rule fails (for example semantically different constraints). That has not been
measured. If Muse merely matches the rule, report that honestly and keep the
rule as the product baseline (PRD §15).

## H. Limitations

- **Live Muse integration is unverified.** No request has been sent to
  Fireworks; account access, the PRD-noted preview caveat (through October 29),
  rate limits and real tool-calling behaviour are all unknown.
- Cost estimation is off until a price table is configured; no prices are
  asserted.
- Only T01 and T02 on the `bridge_bracket_v1` family exist. No other template,
  rotation, flexible part, cable, force or strength analysis.
- Expected outcomes are analytic, not exhaustive enumerations of all 196
  candidates per case.
- Fixtures are synthetic with pending redistribution rights; the evaluation
  cases share one constructor family.
- The native static check runs twice inside `ai_verify` (once for per-check
  evidence, once inside `Problem`), about 1–2 s per candidate.
- Not assessed: structural strength and fatigue, electrical safety,
  manufacturing feasibility, restored function. A verified improvement is a
  design-review result, not a release.
- Linux/container behaviour remains unvalidated, as in the earlier phases.

## I. Next integration step

1. Export `FIREWORKS_API_KEY`, run `UNLOCK_AI_LIVE=1 python -m unlock_engine.ai
   smoke`, then `demo --fixture B02` and `eval --conditions
   c2_stable,c2_geometry,muse`; compare `reasoning_effort` medium and high only
   if medium underperforms.
2. FastAPI coordinator: `POST /v1/revisions/{id}/runs` performs Stage A through
   the same session; `POST /v1/runs/{id}/redesign` calls `run_with_model` on the
   single serial native queue, passing the job's cancel event; stream
   `AIRunReport.events` as SSE in sequence order; persist the final
   `AIRunReport` (it carries full hashes for reproduction).
3. Frontend: map `AIRunReport` into `frontend/src/domain/types.ts` — events to
   the redesign stage list, `candidates[].stages` and `feedback` to the
   candidate panel, `revised_plan` and `comparison` to the comparison view.
   Show green only when `live_model` or a stored computed provenance backs a
   `VERIFIED_IMPROVEMENT` stage; label `offline_fake_provider` runs as fixtures.
