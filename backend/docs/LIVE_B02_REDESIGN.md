# First live AI-driven CAD redesign — B02, Muse Spark 1.3

A second live run, on the B05 battery bay, is recorded in [LIVE_B05_REDESIGN.md](LIVE_B05_REDESIGN.md).

Executed October 29, 2026 (UTC 2026-10-30T01:59) on `feature/live-b02-redesign`.
**Outcome: `VERIFIED_IMPROVEMENT_FOUND`.** Muse Spark 1.3 investigated the real
obstruction, chose its own supported T01 relief, and the trusted constructor
built it. The independent verifier, the planner and the comparison service
established the improvement. The model's own statements carry no authority in
this result.

B02 is a **synthetic repository fixture**. Geometric verification does not
establish strength, fatigue, manufacturing readiness, electrical safety or
restored function.

## What ran

One authorised live run, with no retry:

```sh
RUN_META_LIVE_TESTS=1 PYTHONPATH=src .venv/bin/python -m unlock_engine.ai demo --fixture B02 --output .work/live-b02/live
```

- **Provider and model:** `meta`, `muse-spark-1.3` at `https://api.meta.ai/v1`,
  `reasoning_effort=medium`.
- **Limits (unchanged):** 3 candidates, 12 tool calls, 6 turns, 16,000 output
  tokens, 120 s, one schema repair.
- **Retries:** SDK retries off; the controller's bounded retries (2, retryable
  errors only) were available but unused.
- **Prompt:** the existing system prompt and Stage A context. No parameter
  values were suggested.

## Identity

| Item | Value |
|---|---|
| Fixture / target | `fixture_B02` / `target` (synthetic) |
| Original revision | `93eb0bd14037cfc686ef5c311893c0e92aa08a7b1ac6eaf177f0fc6ca2272df6` |
| Geometry hash | `4a5f487e6df0374e0ff8c8d59949ceffce53874fd9c92abf41b820b71c7b49fb` |
| Constraint hash | `6ae089e659619419573c82d43ba378fadfda034ffa9851bc2162e04385167bb4` |
| Numerical / search policy | `policy_v1` / `planner_v1`, search-policy digest `fdc677c43564b7e25696ebc4b745985a7c5d78ccc8e7c97bd219aa5657dd6915` |
| Candidate revision | `84541a71d966739e58d9ff612902be92173d4576ca6505b9ea85eca71c7cdb87` |
| Changed bracket | Geometry hash `7aebefb8395f5414…`; STEP SHA-256 `3963ce4dce4ea8157aaf9f24a71e0e6e06d72a0e8397fdef2c247f681f095fea` |

## Decision sequence

| t (s) | Model turn | Tool call (validated) | Result |
|---:|---|---|---|
| 16.0 | — | Stage A baseline | `no_path_supported`, complete. Two `CONFIRMED_GEOMETRIC_OBSTRUCTION` rejections of `target Z+`, with an actual BRep witness |
| 20.7 | 1 (4.7 s) | `inspect_blocker(rej_17a84dbaf811)` and `list_interventions(bridge)` | ok: blocked witness at (0, −20, 36) mm; T01/T02 finite domains |
| 25.4 | 2 (4.7 s) | `construct_candidate` T01 (0, −20) **24 × 12**, citing two `ev_` handles | **Refused before construction** (`INVALID_PROPOSAL`): "cite at least one rejection, plan or verification evidence ID" |
| 34.4 | 3 (5.3 s) | `construct_candidate` T01 (0, −20) **40 × 16**, citing `rej_17a84dbaf811` | Constructed `cand_eaafba557ae0`; 2,560 mm³ removed from `bridge`, all inside the editable web |
| 44.5 | 4 (1.7 s) | `verify_candidate(cand_eaafba557ae0)` | Static checks passed, then independent replanning |
| 46.1 | 5 (1.6 s) | `compare_candidates` | `verified_improvement: true` |
| 48.1 | 6 (2.0 s) | Final JSON (`candidate_proposed`) | Recorded as a model statement with no authority |

Every executed call passed the strict dispatcher: schema, frozen
project/revision/target identity, run-issued evidence handles and the server
domains. One proposal was refused by that validation. Five of the eight tools
were called live. `inspect_assembly`, `inspect_constraints` and `analyze_removal`
were not needed, because the initial context already carried the baseline
rejections. All eight remain covered offline in `tests/test_ai_toolbox.py`.

## Verification

- **Static checks:** 12/12 mandatory checks **pass**:
  - integrity and solid validity;
  - trusted reconstruction (an independent rebuild, compared by two-way BRep
    difference);
  - actual change (2,560 mm³);
  - editable region (0 mm³ removed outside it);
  - protected interfaces and hole geometry;
  - fixed components and placements;
  - design envelope and keep-outs;
  - assembled intersections.

  `tool_access` is non-mandatory and `not_applicable` at the static stage. It is
  deferred to state-aware replay, which passed.
- **Failed, unknown, missing or stale checks:** none.
- **Revised plan:** `feasible`, complete and optimal within scope. One step:
  `target` TRANSLATE Z+ 80 mm. Cost (0, 0, 0, 1), with a 0.5 mm non-contact
  clearance lower bound.
- **Replay and reverse insertion:** forward replay passed; reverse insertion
  passed; `target_path` passed.
- **Comparison:** `no_path_supported` → `feasible`. The original has no defined
  operation count, so no percentage is reported.

## Defect found and fixed

Muse's **first** proposal was T01 (0, −20) 24 × 12. That is the same relief the
geometry-ranked selector verifies on B02. It was refused because it cited only
`ev_` handles. The dispatcher requires a `rej_`, `plan_` or `ver_` handle, but the
prompt asked only for "real evidence IDs issued by tools". The refusal also didn't
say that construction never started or that resubmission was allowed. Together
with "never repeat an attempted proposal", that plausibly led Muse to change the
design instead of only the citation.

Commit `fffc1e4` fixes this:
- The prompt and the `construct_candidate` description now state the rule.
- The refusal now says construction did not start, invites resubmission of the
  same parameters and sets `retry_permitted`.
- The no-repeat rule now covers only constructed proposals.

A regression test replays the recorded proposal shape and fails on the previous
code. The fix adds no parameter guidance.

## Comparison with the deterministic baseline

All three ran on the same fixture. The selectors ran before the live call and
are unmodified.

| | Muse Spark 1.3 (live) | `geometry_ranked` | `stable_enumeration` (PRD C2) |
|---|---|---|---|
| Outcome | VERIFIED_IMPROVEMENT_FOUND | VERIFIED_IMPROVEMENT_FOUND | NO_VERIFIED_IMPROVEMENT |
| Proposals / constructed | 2 / 1 (1 refused before construction) | 1 / 1 | 3 / 3 (1 no repair path, 2 construction failed) |
| Verified design | T01 (0, −20) 40 × 16, 2,560 mm³ removed | T01 (0, −20) 24 × 12, 1,152 mm³ removed | — |
| Revised route | target Z+ 80 mm, cost (0, 0, 0, 1) | same | — |
| Tool calls | 6 | 2 | 4 |
| Runtime | 48.1 s (20.0 s model, 12.0 s geometry) | 24.1 s | 30.3 s |
| Model cost | ≈ $0.030 at list price | $0 | $0 |

- **Overall:** Muse **matched** the geometry-ranked selector's outcome. It did not
  outperform it.
- **Design and route:** its verified relief removes about 2.2× more material than
  the minimal verified relief. Both give the same revised route and cost.
- **Effort:** it needed one more proposal, four more tool calls and about twice
  the runtime.
- **Single run:** one run on one synthetic case is not a statistical comparison.

## API usage

- **Requests:** 6, with 0 retries and 0 schema repairs.
- **Tokens:**
  - input 28,272, of which 16,068 were cached;
  - output 2,850, including 1,596 reasoning;
  - total 31,122. All of these were provider-reported for every turn.
- **Latency:** 20.0 s across six turns (1.6–5.3 s each). Total run time was
  48.1 s, inside the 120 s limit.
- **Estimated cost:** **$0.0298** at Meta's public Standard list price ($1.25
  input, $0.15 cached input, $4.25 output per million tokens). That price comes
  from <https://dev.meta.ai/docs/pricing-rate-limits>, retrieved 2026-10-29, and
  is not account-verified. The API reports no credit balance.

## Runtime hardening (commits `c9b2c3a`, `12ed6f6`)

The offline preflight run took 77.9 s of the 120 s budget with zero model
latency. Each native operation cold-starts Python and imports OCP, CadQuery and
VTK, which takes 4–6 s under load. The engineering work itself is about 8 s per
candidate in-process.

A warm, single-use standby worker takes the start-up cost off the critical path.
The standby imports libraries only, then takes exactly one request, lowers its
CPU cap to that operation's own limit, and exits. Per-operation isolation,
independent reconstruction, phase deadlines, cancellation and credential
stripping are unchanged.

The live run above used the first version (`c9b2c3a`), in which a replacement
standby warmed while the operation was still running. Review of PR #4 led to
four changes (`12ed6f6`):

| Change | Behaviour now |
|---|---|
| Spawning | Best-effort: if the OS refuses a standby, the operation cold-starts. |
| Memory | At most one pooled CAD process exists at a time. A replacement starts only after the operation using the previous one has exited. Peak worker memory therefore equals the cold path: about 440 MiB peak RSS on B02. `UNLOCK_PREWARM_WORKERS=0` turns prewarming off. |
| Handoff | A standby writes an explicit acceptance before any work. Without it, the operation provably never ran and is cold-started; after it, a failure is never retried. |
| Requests | Operations and work directories are allowlisted before any process starts. |

The one-process policy can't warm a worker during back-to-back engine steps, so
the benefit now comes from overlap with the model's think time.

| Measurement | Cold | Warm |
|---|---:|---:|
| First version, no model latency, load ≈ 5–6 | 46.1 / 47.0 s | 29.5 / 29.7 s |
| One-process policy, no model latency, load ≈ 12 | 59.2 s | 55.2 s |
| One-process policy, simulated 3 s model turns (live turns took 1.6–5.3 s), load ≈ 10 | 80.5 s | 60.0 s |

All of these runs produced identical candidates and outcomes. Replaying the
live-chosen 40 × 16 relief through the current engine gives the same geometry
hash (`7aebefb8395f5414…`), 2,560 mm³ removed, 12/12 mandatory checks, the same
route, and `VERIFIED_IMPROVEMENT`.

| Option | Saving | Decision |
|---|---|---|
| Defer preview and STEP exports until after verification | ≈ 0.8 s per candidate | Not changed |
| Cache the STEP import across workers | ≈ 0.5 s per worker | Not changed: it would share BRep state across processes |

The limits were not changed.

## Evidence

All in `backend/evidence/live-b02/`:

| File | Contents |
|---|---|
| `live_run.json` | Full `AIRunReport`: events, every tool response, plans, certificates, artifact hashes |
| `live_engineering_summary.json` | Derived by `scripts/summarize_ai_run.py` |
| `live_changed_bridge.step` | The constructed bracket |
| `selector_*.json` | The two deterministic selector runs |
| `worker_standby_benchmark.jsonl` | Cold-versus-warm timings |

No private reasoning or credentials are stored. `tests/test_ai_live_evidence.py`
treats the recorded report as a labelled fixture; it is not new inference.

## Remaining scope

- **Evidence base:** one live run on one synthetic fixture. No reliability rate,
  no effort comparison, and no other cases (B01, B03, held-out) live.
- **Behaviour after the fix:** the corrected citation contract has not yet been
  exercised live. The next live run would show whether Muse then resubmits the
  minimal relief.
- **Tool coverage:** three of the eight tools were not exercised live.
- **Budget headroom:** at this run's pace, a two-candidate live run is estimated
  at about 30 s of engine time plus 7 turns × about 3 s. That's within budget,
  but unmeasured live.
- **Material change:** the model preferred a larger cut. The improvement rule
  ranks removal cost, not material change, so a minimal-change objective would
  be a separate product decision.
