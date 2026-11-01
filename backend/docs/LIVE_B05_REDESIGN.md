# Second live AI-driven CAD redesign — B05 battery bay, Muse Spark 1.3

Executed 2026-11-01 (UTC 22:06). **Outcome: `VERIFIED_IMPROVEMENT_FOUND`.**
Muse Spark 1.3 investigated why the battery pack could not be lifted out, chose
to move the retaining strap rather than cut anything, and the trusted
constructor built that edit. The independent verifier, the planner and the
comparison service established the improvement. The model's own statements
carry no authority in this result.

B05 is a **synthetic gallery fixture** (CC BY 4.0, see [GALLERY.md](GALLERY.md)).
Geometric verification does not establish strength, fatigue, manufacturing
readiness, electrical safety or restored function.

## What ran

One authorised live run, with no retry, from `main` at `fbc1b83` plus the CLI
change that admits gallery fixtures:

```sh
RUN_META_LIVE_TESTS=1 PYTHONPATH=src .venv/bin/python -m unlock_engine.ai demo --fixture B05 --output .work/live-b05/live
```

- **Provider and model:** `meta`, `muse-spark-1.3` at `https://api.meta.ai/v1`,
  `reasoning_effort=medium`.
- **Limits (unchanged from B02):** 3 candidates, 12 tool calls, 6 turns, 16,000
  output tokens, 120 s, one schema repair.
- **Prompt:** the existing system prompt and Stage A context. No parameter values
  were suggested.
- **Expectation, written before the run:** B05 binds only T02, so Muse can only
  move the strap by −12, +12, +24 or +36 mm. The offline scripted policy's −12
  verifies with a 4 mm gap. Which offset Muse would pick, and whether it would
  verify within budget, was unknown.

## Decision sequence

Times are from the run start, including Stage A import and baseline.

| t (s) | Turn | Tool call (validated) | Model's stated intent |
|---:|:--|:--|:--|
| 19.5 | — | Stage A baseline | `no_path_supported`, complete: `target Z+` `CONFIRMED_GEOMETRIC_OBSTRUCTION` |
| 22.4 | 1 | `inspect_blocker(rej_682b3fdd3ffd)` and `list_interventions(bridge)` | "inspect the confirmed obstruction and pull the allowed redesign options" |
| 26.9 | 2 | `analyze_removal` | "confirm the baseline before proposing the shift" |
| 29.2 | 3 | `inspect_assembly([target, bridge])` | "check component bounds to pick the correct offset direction" |
| 47.1 | 4 | `construct_candidate` T02 **offset_y −12 mm**, citing `rej_682b3fdd3ffd` and `plan_d1f00d45bb61` | Rationale: "Witness y=8 vs target y 4-26 overlaps bridge y -12..12; shift web -12 to clear Z+ path". Built `cand_da9877d1295f` |
| 72.2 | 5 | `verify_candidate(cand_da9877d1295f)` | Static checks passed, then independent replanning |
| 73.3 | 6 | `compare_candidates` | `verified_improvement: true` |

All 7 calls passed the strict dispatcher on the first attempt: no refusals, no
schema repairs, no retries. Muse cited `rej_` and `plan_` handles first time, so
the citation defect recorded in the [B02 live run](LIVE_B02_REDESIGN.md#defect-found-and-fixed)
did not recur. The run stopped on `turn_budget` because the comparison used the
sixth and last turn, leaving none for a closing message. The outcome is derived
from the candidate evidence and the planner comparison, not from a model message.

## Verification

- **Static checks:** 11 of 12 pass; `tool_access` is `not_applicable` because no
  screw retains the pack. Passed: integrity, solid validity, trusted
  reconstruction, actual change (11,328 mm³ changed in `bridge`), protected
  interfaces, hole geometry, fixed components, placements, design envelope,
  keep-outs and assembled intersections. Failed or unknown: none.
- **Revised plan:** `feasible`; the pack lifts Z+ with cost (0, 0, 0, 1).
  Reverse insertion passed and `target_path` passed.
- **Comparison:** `no_path_supported` → `feasible`.

## Usage and cost

6 provider requests; 29,621 input tokens (14,803 cached), 3,013 output tokens
(1,822 reasoning). Model latency 16.8 s, geometry 37.0 s, total 73.3 s. The run
had no price table configured. At the muse-spark-1.3 Standard list price in
`ai/config.py` ($1.25 input, $0.15 cached input, $4.25 output per million
tokens; not account-verified) it is about **$0.0335**.

## Comparison with the offline scripted policy

The public gallery's B05 run uses the offline scripted policy. It chose the same
−12 mm offset and verified it on Modal earlier the same day (job `de56b63d…`). Muse reached the
same design by its own investigation; it did not find a different or better one.
What the run shows is that the model, admitted with eight bounded tools and no
authority, reached a verified result on a second assembly with a different edit
type (moving material rather than cutting it).

## Evidence

All in `backend/evidence/live-b05/`:

- `live_run.json`: the complete AIRunReport (run `run_789e002df8dc4aec`).
- `live_summary.txt`: the CLI summary.
- `live_changed_bridge.step`: the verified bracket as constructed, SHA-256
  `7afa8af335f262e8…`.

The API key was read from the local, git-ignored `backend/.env` and appears in
none of these files.
