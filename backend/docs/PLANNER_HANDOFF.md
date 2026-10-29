# Deterministic disassembly planner engineering handoff

Implemented and executed locally on October 28, 2026. Branch:
`codex/disassembly-planner`. Existing uncommitted work and frontend preserved.
The previous geometry handoff is historical; this document records the new planner.

## Implemented features and repository changes

Complete supported removal search, state-dependent semantic pruning and real CAD
validation, deterministic lexicographic UCS, full-state memoization, geometry-aware
transition caching, structured rejection/witness evidence, exact placement steps,
independent replay, explicit reverse insertion and screw/tool restoration,
sequence-derived metrics, trusted original/revised comparison, strict frontend
contracts, bounded native execution, cancellation, crash handling and immutable
content-addressed artifacts. No AI inference or frontend responses were fabricated.

| Files | Responsibility |
|---|---|
| `planning/contracts.py`, `state.py` | Typed immutable records, state, connections, placements, costs and metrics |
| `planning/problem.py`, `actions.py` | Frozen geometry/constraint identity, semantic preconditions, finite endpoints, authoritative CAD adapters, cache and obstruction evidence |
| `planning/search.py` | UCS, stable ties, best-cost states, parents, limits and completeness |
| `planning/replay.py` | Fresh forward replay and inverse restoration |
| `planning/service.py`, `runner.py` | Coordinator API, comparisons, isolated workers, persistence and retrieval labeling |
| `planning/fixtures.py`, `demo.py` | Actual synthetic STEP sequences and canonical/revised demonstrations |
| `motion.py`, `tools.py`, `verification.py`, `worker.py`, `cli.py` | Narrow existing-engine integration: terminal contacts, tool-policy propagation, explicit static-only candidate checks, native phase budgets and CLI |
| `tests/test_planning_search.py`, `test_planning_geometry.py` | Independent exhaustive oracles, real geometry, corruption, resource and regression tests |
| `schemas/`, `docs/PLANNER.md`, `PLANNER_AUDIT.md` | JSON Schema, integration commands and compatibility findings |

## Integration and algorithm

Use `planning.runner.isolated_plan(package, target_id, policy, template=...,
cancel_event=...)` from the future coordinator. It constructs actual candidates
through the existing engine. In controlled native workers, use `plan_revision`
or `Problem` plus `plan_problem`. Use `replay_plan` and `validate_reverse` for
validation; `compare_revisions` recomputes both sides. `compare_plans` is for
trusted engine records, not client-supplied verdicts. `save_result` writes CAS
evidence, and `retrieve_result` explicitly labels a historical retrieval.

All geometry comes from the existing STEP/XDE and OCCT services. No collision
algorithm was duplicated. Remaining parts stay assembled. A state consists of
removed occurrence IDs and last tool; connections derive from the manifest.
Actions are enumerated by occurrence then axis. Semantic failures avoid native
checks. Only CLEAR certificates admit transitions. Cache keys bind actual
geometry, revision, removed set, operation parameters, representations, policy,
tool configuration and constraints; replay uses a fresh transition cache.

UCS orders `(unrelated nonfasteners, fasteners, tool changes, operations)` with
stable serial ties. It preserves last tool across hand translations and ignores
initial pickup. Best-cost full-state memoization and stale heap checks prevent
worse re-expansion. Goal settlement proves optimality only in the finite declared
operation graph and only with conclusive alternatives. A feasible complete result
does not claim higher-cost frontier exhaustion. No-path requires actual exhaustion
and no unresolved transition. Unknowns and limits remain incomplete; cancellation
cannot commit success. Defaults: 4096 expanded states / 30s monotonic search time.
The parent also terminates native code that overruns its phase deadline.

See [PLANNER.md](PLANNER.md) for the endpoint rule, phase limits and contract details.

## Executed validation

Baseline before source edits: **109 passed, 0 failures,
0 errors, 0 skipped**, JUnit wall 80.28s.

Final complete suite: **177 passed, 0 failures,
0 errors, 0 skipped**, JUnit wall 67.45s.
Raw pytest output includes dependency deprecation warnings and the intentional
duplicate-ZIP warning; see `evidence/planner_pytest.txt` for the exact count/time.

Commands executed from repository root:

```sh
backend/.venv/bin/python -m pytest backend/tests -q --junitxml=backend/evidence/planner_baseline.xml
backend/.venv/bin/python -m pytest backend/tests -q --junitxml=backend/evidence/planner_pytest.xml --durations=12
backend/.venv/bin/ruff check backend/src backend/tests backend/scripts
backend/.venv/bin/ruff format --check backend/src backend/tests backend/scripts
backend/.venv/bin/python -m pip check
npm --prefix frontend run typecheck
backend/.venv/bin/unlock-engine schemas --output backend/schemas
backend/.venv/bin/unlock-engine plan-demo --output backend/evidence/planning
```

Ruff, formatting, dependency consistency and frontend typechecking passed. The
existing STEP round-trip/export tests remain in the full passing suite. Two
independent exhaustive reference solvers cover exact tiny graphs and all four
legal real-CAD fixture sequences. Tests cover longer lexicographically preferred
routes, tool grouping, unknowns, limits, thin obstacles, missing engagement,
multiple retainers, corrupt/stale/reordered evidence, blocked reinsertion,
terminal contacts, source immutability, candidate rejection and worker failure.
Fault injection never supplies mocked geometry success.

## Actual fixture results

| Case | Target | Status | Cost tuple | Complete / optimal | Replay / reverse |
|---|---|---|---|---|---|
| B01 | target | feasible | (0, 0, 0, 1) | True / True | passed / passed |
| B02 | target | no_path_supported | undefined | True / False | not_run / not_run |
| B03 | target | no_path_supported | undefined | True / False | not_run / not_run |
| B03-cover | cover | no_path_supported | undefined | True / False | not_run / not_run |
| sequence | target | feasible | (1, 2, 1, 4) | True / True | passed / passed |
| B02-T01 | target | feasible | (0, 0, 0, 1) | True / True | passed / passed |
| B02-T02 | target | feasible | (0, 0, 0, 1) | True / True | passed / passed |

B01 reaches its stage without unrelated removals. B02's fixed bridge obstructs
the target. B03's original target also encounters that bridge; its annotated screw
retains the cover, not the original target. B03-cover selects that cover through
new metadata and confirms its tool-access obstruction. No manually authored final
step lists are consumed by search.

The sequence fixture's actual discovered route is:

1. `TRANSLATE_PART` **cover**, X+, 70.520mm
2. `REMOVE_FASTENER` **screw1**, Z+, 80.000mm
3. `REMOVE_FASTENER` **screw2**, Z+, 80.000mm
4. `TRANSLATE_PART` **target**, Z+, 80.000mm

Cost **(1, 2, 1, 4)**; 2 distinct tools;
forward replay **passed**; reverse restoration
**passed**. The replacement geometry is identical to the original
component. Exact matrices, state hashes and tool/extraction subchecks are in
`evidence/planning/sequence/result.json`.

Both `comparison-T01.json` and `comparison-T02.json` record a conclusive
no-path-supported to feasible transition. Baseline operation counts are undefined;
no percentage is invented. A separate real regression case with a removable
bridge verifies feasible baseline improvement from `(1, 0, 0, 2)` to `(0, 0, 0, 1)`.
Non-improving edits and incompatible policy/constraint identities are rejected.

B02's retained actual BRep obstruction witness (not a proxy-only claim):

```json
{
  "status": "blocked",
  "kind": "positive_volume_intersection",
  "component_ids": [
    "target",
    "bridge"
  ],
  "explanation": "Completed BRep common contains positive material volume",
  "distance_mm": null,
  "intersection_volume_mm3": 639.9999999999999,
  "witness_mm": [
    3.5527136788005016e-16,
    -19.999999999999996,
    36.0
  ],
  "witness_travel_mm": 13.0
}
```

## Measured performance

Hardware/runtime: macOS-27.0-arm64-arm-64bit, 10 logical CPUs,
Python 3.12.16, CadQuery 2.6.1,
cadquery-ocp 7.8.1.1.post1. RAM was not measured. One observation
per case, executed serially without a concurrent native benchmark. Search timers
exclude runtime startup, import and candidate preparation. Worker wall includes
those stages plus replay/reverse/final checks. No percentile or cold-cache claim.

| Case | Search ms | Expanded | Peak frontier | Search geometry calls | Rejected / unknown | Cache hits / misses | Replay / reverse ms | Worker wall ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B01 | 53.42 | 1 | 2 | 2 | 3 / 0 | 0 / 2 | 25.27 / 55.86 | 2041.86 |
| B02 | 392.58 | 2 | 1 | 3 | 14 / 0 | 0 / 3 | 0.00 / 0.00 | 2591.03 |
| B03 | 563.18 | 1 | 1 | 3 | 10 / 0 | 0 / 2 | 0.00 / 0.00 | 2972.51 |
| B03-cover | 568.01 | 1 | 1 | 3 | 10 / 0 | 0 / 2 | 0.00 / 0.00 | 3012.54 |
| sequence | 955.89 | 6 | 2 | 16 | 12 / 0 | 0 / 10 | 198.23 / 320.83 | 3351.39 |
| B02-T01 | 151.32 | 1 | 2 | 2 | 6 / 0 | 0 / 2 | 77.20 / 107.23 | 4143.29 |
| B02-T02 | 149.58 | 1 | 2 | 2 | 6 / 0 | 0 / 2 | 76.84 / 107.02 | 4159.49 |

Search cache hit ratio is zero in these small canonical runs because state
memoization already avoids repeated checks. Dedicated tests demonstrate cache
reuse and invalidation; no speedup is inferred from the zero-hit observations.
Forward and reverse validation deliberately use fresh caches.

## Limits and next-phase readiness

The Python planner interface is ready for bounded tool orchestration. Meta
inference, provider credentials/access, HTTP jobs, persistent coordinator database,
authentication, frontend integration and production scheduling remain separate.
A future AI controller can request analysis and bounded templates; it cannot
override geometry, metrics, replay, reverse or improvement verdicts. Production
hosting still needs a serial native job queue, cancellation integration and the
previously outstanding Linux/container validation.

The scope remains 5–12 rigid single-solid occurrences, millimetres, six world axes,
declared reusable screws, narrow planar contacts and finite stage endpoints. No
temporary displacement, subassembly carrying, arbitrary rotation, flex, cables,
force, torque, thread simulation or real repair certification. Unknown relations
fail the whole existing readiness gate. Any observed unknown edge conservatively
withholds completeness/optimality. A hard worker interruption may discard a
found but uncommitted route and returns incomplete rather than inventing proof.

These fixtures are synthetic, with simplified mating and assumed workholding.
Fixture redistribution licensing, an authorized real assembly and independent
mechanical review remain outstanding. Strength, electrical safety, manufacturing
feasibility and restored function are unassessed. Linux caps/container behavior
have not been validated on this Mac.

## Evidence and reproducibility

`evidence/planner_source_snapshot.json` records source/schema/test hashes, installed
dependencies, evidence hashes and changed files relative to the earlier geometry
snapshot. Prior evidence is preserved. `evidence/planning_bundle.zip` contains the
canonical inputs, result records, comparisons, schemas, test output and this
handoff. `planning_bundle.sha256` verifies the archive. Regenerate this document
and archive with `backend/.venv/bin/python backend/scripts/write_planner_handoff.py`.
The writer refuses failed/skipped mandatory tests and invalid result identities.
