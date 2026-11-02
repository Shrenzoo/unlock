# The agent loop

[← Back to the README](../README.md)

UNLOCK's redesign loop is a bounded tool-calling agent. This document records exactly what the model can do, what stops it, and what it did in the recorded live runs. Source: `backend/src/unlock_engine/ai/`.

## The connection

| Setting | Value | Where |
|:--|:--|:--|
| Model | `muse-spark-1.3`, direct Meta Model API | `ai/config.py` |
| Endpoint | `https://api.meta.ai/v1/chat/completions` | `ai/config.py` |
| Client | Official OpenAI-compatible SDK, `openai==2.6.1`, with `max_retries=0` | `ai/meta.py` |
| Tool choice | `auto`; anything else is refused locally | `ai/meta.py:85` |
| Reasoning effort | `medium` by default; never raised automatically | `META_REASONING_EFFORT` |
| Output cap per request | `max_completion_tokens = min(4096, remaining run budget)` | `ai/controller.py:563` |

The offline mode, `AI_PROVIDER=mock`, swaps the provider for the labelled scripted policy in `ai/demo.py`. It runs the same toolbox and the same engine, and its reports carry `provenance: offline_fake_provider`.

## The eight tools

`TOOL_ARGS` in `ai/schemas.py` is the complete list. Each tool definition sent to the model is generated from the same Pydantic model that later validates the call, so the schema the model reads and the schema the server enforces cannot drift apart.

| Tool | What it runs | Effect |
|:--|:--|:--|
| `inspect_assembly` | Validated manifest and measured inventory, for up to 12 components | Read |
| `inspect_constraints` | Frozen constraints, regions, keep-outs and envelope | Read |
| `analyze_removal` | The deterministic Stage A plan for the frozen target | Read |
| `inspect_blocker` | One rejection's certificates and BRep witness | Read |
| `list_interventions` | `SERVER_DOMAINS` intersected with the manifest's binding | Read |
| `construct_candidate` | `templates.admit`, then the trusted constructor in a fresh worker | Builds a candidate; the original revision never changes |
| `verify_candidate` | Fresh worker: reconstruct, check, replan, replay, reverse | Records a verdict |
| `compare_candidates` | `planning.service.compare_plans` on service-produced records | Records a comparison |

There is no shell, Python, URL or filesystem tool, and no accept or export tool. A human decision and a separate endpoint handle acceptance and export.

## The decision space

```python
# backend/src/unlock_engine/templates.py:21
SERVER_DOMAINS = {
    "T01": dict(
        center_x_mm=(-4.0, 0.0, 4.0),
        center_y_mm=(-24.0, -20.0, -16.0, 0.0),
        width_mm=(24.0, 40.0, 46.0, 52.0),
        depth_mm=(8.0, 12.0, 16.0, 20.0),
    ),
    "T02": dict(offset_y_mm=(-12.0, 12.0, 24.0, 36.0)),
}
```

That is 19 values across 5 parameters: 3 × 4 × 4 × 4 = 192 T01 reliefs plus 4 T02 offsets, 196 possible designs. A fixture's manifest can narrow this further. B05 binds only T02, and B06 caps the cut at 1,200 mm³.

## What the dispatcher enforces

Every call passes through `Toolbox.execute` (`ai/toolbox.py:298`), in this order:

1. **Allowlist.** A name outside `TOOL_ARGS` returns `TOOL_NOT_ALLOWED` and is never dispatched.
2. **Strict schema.** Arguments parse with `strict=True`. Extra properties, wrong types, NaN or infinity, and unknown enum values return `SCHEMA_ERROR` before any handler runs.
3. **Frozen identity.** Project, revision and target must equal the run's frozen values. A foreign project or stale revision returns `STALE_EVIDENCE`.
4. **Evidence citation.** A proposal's `evidence_ids` must all be handles this run issued, and at least one must be a rejection (`rej_`), plan (`plan_`) or verification (`ver_`). Otherwise construction does not start.
5. **Finite domain.** Parameters must be values from the server's list, and the template must be enabled for that bracket.
6. **Budget.** Candidate, tool-call, turn, token and time limits are checked as the run goes.

Imported names reach the model only under an `untrusted_text` key, and the system prompt says they are data, never instructions. `test_injected_component_name_is_returned_only_as_untrusted_data` covers this.

## Budgets

`ai/toolbox.py:40`. `Budget.__post_init__` raises if any value is set above these ceilings, so a caller cannot widen them.

| Budget | Ceiling |
|:--|--:|
| Constructed candidates | 3 |
| Tool calls | 12 |
| Model turns | 6 |
| Output tokens, whole run | 16,000 |
| Output tokens, per request | 4,096 |
| Wall clock, including Stage A | 120 s |
| Schema repairs | 1 |

Output tokens are reserved before each request and charged at the cap when a provider response reports no usage. Provider errors retry at most twice, only when retryable, and never past the deadline.

## Rejection and retry

Failures return typed `Feedback`: a category, a message, and where relevant the constraint, parameter, measured value, allowed bound and evidence ID. Measurements are copied from engine records, never estimated.

There are 13 categories, from `INVALID_PROPOSAL` to `BUDGET_EXHAUSTED`. Identical proposals are deduplicated by revision, constraint hash, policy, template and normalized parameters, and return `DUPLICATE_CANDIDATE`.

## Who decides the outcome

`derive` in `ai/controller.py:252` computes the outcome from candidate records and the planner's comparison. It does not read a model message. The six outcomes are `VERIFIED_IMPROVEMENT_FOUND`, `NO_VERIFIED_IMPROVEMENT`, `NO_SUPPORTED_CANDIDATE`, `INCOMPLETE_ANALYSIS`, `MODEL_UNAVAILABLE` and `CANCELLED`.

The model's closing message is stored with an annotation the engine writes at `ai/controller.py:399`:

```json
{
  "decision": "candidate_proposed",
  "candidate_ids": ["cand_eaafba557ae0"],
  "summary": "T01 cut on bridge clears Z+ witness [0,-20,36]; verified feasible 1-step removal. Evidence ev_83077a556f31, ev_afa690947095, ev_376f5dc775ac, ev_174b5dfa252c, ev_946617b05d3f.",
  "structured": true,
  "authority": "none: model statement, not engineering evidence"
}
```

`test_all_candidates_fail_duplicate_and_budget_and_false_success_claim` covers a model that claims success on failing candidates. The verdict does not change.

## The live records

### B01: tool-calling check, 2026-10-29

Two requests, read-only. Muse requested `inspect_assembly`, the backend validated and ran it, and the final answer matched the tool's payload field by field. All 15 outcome checks passed. Full record: [`META_TOOL_CALLING_VERIFICATION.md`](../backend/docs/META_TOOL_CALLING_VERIFICATION.md).

### B02: T01 relief, 2026-10-29

| t (s) | Turn | Call | Result |
|--:|:--|:--|:--|
| 16.0 | — | Stage A baseline | `no_path_supported`, complete, with a BRep witness |
| 20.7 | 1 | `inspect_blocker`, `list_interventions` | Witness at (0, −20, 36) mm; finite domains |
| 25.4 | 2 | `construct_candidate` T01 **24 × 12**, citing two `ev_` handles | **Refused before construction**: `INVALID_PROPOSAL` |
| 34.4 | 3 | `construct_candidate` T01 **40 × 16**, citing `rej_17a84dbaf811` | Built; 2,560 mm³ removed |
| 44.5 | 4 | `verify_candidate` | Static checks passed, then replanning |
| 46.1 | 5 | `compare_candidates` | `verified_improvement: true` |
| 48.1 | 6 | Final JSON | Recorded with no authority |

The refused 24 × 12 was the minimal design the deterministic control verifies. It was refused for its citations, not its geometry. The message did not say that resubmitting the same parameters was allowed, and the prompt told the model not to repeat a proposal, which plausibly led to the larger cut. Commit `fffc1e4` fixed the message and added a regression test.

Full record: [`LIVE_B02_REDESIGN.md`](../backend/docs/LIVE_B02_REDESIGN.md).

### B05: T02 relocation, 2026-11-01

| t (s) | Turn | Call | Stated intent or result |
|--:|:--|:--|:--|
| 19.5 | — | Stage A baseline | `no_path_supported`, complete |
| 22.4 | 1 | `inspect_blocker`, `list_interventions` | "inspect the confirmed obstruction and pull the allowed redesign options" |
| 26.9 | 2 | `analyze_removal` | "confirm the baseline before proposing the shift" |
| 29.2 | 3 | `inspect_assembly` | "check component bounds to pick the correct offset direction" |
| 47.1 | 4 | `construct_candidate` T02 **−12 mm**, citing `rej_` and `plan_` handles | "Witness y=8 vs target y 4-26 overlaps bridge y -12..12; shift web -12 to clear Z+ path" |
| 72.2 | 5 | `verify_candidate` | Static checks passed, then replanning |
| 73.3 | 6 | `compare_candidates` | `verified_improvement: true` |

All 7 calls passed on the first attempt. The run stopped on `turn_budget`, because the comparison used the last turn, so there is no closing model message. The outcome did not need one.

Full record: [`LIVE_B05_REDESIGN.md`](../backend/docs/LIVE_B05_REDESIGN.md).

### Tool coverage

Across the live records, seven of the eight tools have run: five distinct tools on B02, seven on B05. `inspect_constraints` has not been called live. All eight are covered offline in `tests/test_ai_toolbox.py`.

## Model against deterministic baselines

| | Muse Spark 1.3 (live) | `geometry_ranked` | `stable_enumeration` |
|:--|:--|:--|:--|
| B02 outcome | Verified improvement | Verified improvement | No verified improvement |
| B02 design | T01 40 × 16, 2,560 mm³ | T01 24 × 12, 1,152 mm³ | None |
| B02 tool calls | 6 | 2 | 4 |
| B02 run time | 48.1 s | 24.1 s | 30.3 s |
| B02 model cost | ≈ $0.030 list price | $0 | $0 |

**Muse matched the geometry-ranked rule on B02 and did not beat it.** It removed about 2.2× more material for the same route. On B05 the offline scripted policy picks the same −12 mm offset. Two runs on two synthetic fixtures measure neither reliability nor superiority.

The older offline evaluation in [`AI_CONTROLLER.md`](../backend/docs/AI_CONTROLLER.md) ran both deterministic rules over seven correlated B01–B03 cases: `geometry_ranked` got 7 of 7 and `stable_enumeration` 3 of 7. The geometry-ranked rule is a high bar on these fixtures.

## API usage

| Run | Requests | Input tokens (cached) | Output tokens (reasoning) | Model latency | Wall time | List-price estimate |
|:--|--:|--:|--:|--:|--:|--:|
| B01 check | 2 | 2,903 (0) | 411 (199) | 5.77 s | 15.1 s | $0.0054 |
| B02 redesign | 6 | 28,272 (16,068) | 2,850 (1,596) | 20.0 s | 48.1 s | $0.0298 |
| B05 redesign | 6 | 29,621 (14,803) | 3,013 (1,822) | 16.8 s | 73.3 s | $0.0335 |

Tokens are provider-reported. Costs are estimates at Meta's public Standard list price retrieved 2026-10-29 ($1.25 input, $0.15 cached input, $4.25 output per million tokens), not account-verified charges.
