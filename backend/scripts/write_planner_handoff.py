"""Build the planner handoff and archive from actual completed run evidence."""

from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET
import zipfile

from jsonschema import Draft202012Validator

from unlock_engine.planning import PlanResult
from unlock_engine.planning.service import validate_saved_result

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite(path):
    suites = ET.parse(path).getroot().iter("testsuite")
    totals = {k: 0 for k in ("tests", "failures", "errors", "skipped")}
    seconds = 0
    for item in suites:
        for key in totals:
            totals[key] += int(item.attrib.get(key, 0))
        seconds += float(item.attrib.get("time", 0))
    return totals, seconds


def main():
    totals, seconds = suite(ROOT / "evidence/planner_pytest.xml")
    baseline, baseline_seconds = suite(ROOT / "evidence/planner_baseline.xml")
    if not totals["tests"] or any(totals[k] for k in ("failures", "errors", "skipped")):
        raise ValueError(f"mandatory regression gate did not pass: {totals}")
    overview = json.loads((ROOT / "evidence/planning/summary.json").read_text())
    schema = Draft202012Validator(
        json.loads((ROOT / "schemas/PlanResult.schema.json").read_text())
    )
    plans = {}
    for name in overview["cases"]:
        data = json.loads(
            (ROOT / "evidence/planning" / name / "result.json").read_text()
        )
        schema.validate(data)
        plan = PlanResult.model_validate(data)
        validate_saved_result(plan)
        plans[name] = plan
    if not all(
        plans[k].replacement_verified for k in ("B01", "sequence", "B02-T01", "B02-T02")
    ):
        raise ValueError("demonstration replacement gates did not pass")
    sequence = plans["sequence"]
    steps = "\n".join(
        f"{i}. `{s.kind}` **{s.component_id}**, {s.axis}, {s.distance_mm:.3f}mm"
        for i, s in enumerate(sequence.steps, 1)
    )
    cases = "\n".join(
        f"| {name} | {p.target_id} | {p.status} | {p.metrics.cost if p.metrics else 'undefined'} | {p.complete} / {p.optimal_within_scope} | {p.replay.status} / {p.reverse.status} |"
        for name, p in plans.items()
    )
    performance = "\n".join(
        f"| {name} | {m['search_ms']:.2f} | {m['expanded_states']} | {m['peak_frontier']} | {m['geometry_calls']} | {m['rejected']} / {m['unknown']} | {m['cache_hits']} / {m['cache_misses']} | {m['replay_ms']:.2f} / {m['reverse_ms']:.2f} | {m['worker_wall_ms']:.2f} |"
        for name, m in overview["measurements"].items()
    )
    obstruction = next(
        (
            f
            for c in plans["B02"].certificates
            for p in c.paths
            for f in p.findings
            if "bridge" in f.component_ids and f.kind == "positive_volume_intersection"
        ),
        None,
    )
    witness = obstruction.model_dump(mode="json") if obstruction else None
    dependencies = {
        k: version(k)
        for k in (
            "cadquery",
            "cadquery-ocp",
            "pydantic",
            "jsonschema",
            "pytest",
            "ruff",
        )
    }
    previous = json.loads((ROOT / "evidence/source_snapshot.json").read_text())
    source_paths = sorted(
        {
            *ROOT.glob("src/**/*.py"),
            *ROOT.glob("tests/**/*.py"),
            *ROOT.glob("scripts/*.py"),
            *ROOT.glob("schemas/*.json"),
            ROOT / "requirements.lock",
            ROOT / "pyproject.toml",
            ROOT / "Dockerfile",
            ROOT / "docs/PLANNER.md",
            ROOT / "docs/PLANNER_AUDIT.md",
        }
    )
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    changed = [
        k
        for k, h in source_hashes.items()
        if k in previous["source_files"] and previous["source_files"][k] != h
    ]
    snapshot = dict(
        generated_at=datetime.now(timezone.utc).isoformat(),
        python=sys.version,
        platform=platform.platform(),
        machine=platform.machine(),
        logical_cpus=os.cpu_count(),
        engine_version="0.1.0",
        planner_version="planner_v1",
        dependencies=dependencies,
        previous_snapshot_sha256=sha(ROOT / "evidence/source_snapshot.json"),
        source_files=source_hashes,
        changed_previous_files=changed,
        evidence={
            str(p.relative_to(ROOT)): sha(p)
            for p in sorted((ROOT / "evidence/planning").rglob("*"))
            if p.is_file() and "artifacts" not in p.parts and "history" not in p.parts
        },
        baseline_tests=baseline,
        final_tests=totals,
    )
    (ROOT / "evidence/planner_source_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True)
    )
    handoff = f"""# Deterministic disassembly planner engineering handoff

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

Baseline before source edits: **{baseline["tests"]} passed, {baseline["failures"]} failures,
{baseline["errors"]} errors, {baseline["skipped"]} skipped**, JUnit wall {baseline_seconds:.2f}s.

Final complete suite: **{totals["tests"]} passed, {totals["failures"]} failures,
{totals["errors"]} errors, {totals["skipped"]} skipped**, JUnit wall {seconds:.2f}s.
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
{cases}

B01 reaches its stage without unrelated removals. B02's fixed bridge obstructs
the target. B03's original target also encounters that bridge; its annotated screw
retains the cover, not the original target. B03-cover selects that cover through
new metadata and confirms its tool-access obstruction. No manually authored final
step lists are consumed by search.

The sequence fixture's actual discovered route is:

{steps}

Cost **{sequence.metrics.cost}**; {sequence.metrics.unique_tools} distinct tools;
forward replay **{sequence.replay.status}**; reverse restoration
**{sequence.reverse.status}**. The replacement geometry is identical to the original
component. Exact matrices, state hashes and tool/extraction subchecks are in
`evidence/planning/sequence/result.json`.

Both `comparison-T01.json` and `comparison-T02.json` record a conclusive
no-path-supported to feasible transition. Baseline operation counts are undefined;
no percentage is invented. A separate real regression case with a removable
bridge verifies feasible baseline improvement from `(1, 0, 0, 2)` to `(0, 0, 0, 1)`.
Non-improving edits and incompatible policy/constraint identities are rejected.

B02's retained actual BRep obstruction witness (not a proxy-only claim):

```json
{json.dumps(witness, indent=2)}
```

## Measured performance

Hardware/runtime: {platform.platform()}, {os.cpu_count()} logical CPUs,
Python {platform.python_version()}, CadQuery {dependencies["cadquery"]},
cadquery-ocp {dependencies["cadquery-ocp"]}. RAM was not measured. One observation
per case, executed serially without a concurrent native benchmark. Search timers
exclude runtime startup, import and candidate preparation. Worker wall includes
those stages plus replay/reverse/final checks. No percentile or cold-cache claim.

| Case | Search ms | Expanded | Peak frontier | Search geometry calls | Rejected / unknown | Cache hits / misses | Replay / reverse ms | Worker wall ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{performance}

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
"""
    (ROOT / "docs/PLANNER_HANDOFF.md").write_text(handoff)
    selected = [
        p
        for p in (ROOT / "evidence/planning").rglob("*")
        if p.is_file() and "artifacts" not in p.parts and "history" not in p.parts
    ]
    selected += list((ROOT / "schemas").glob("*.json"))
    selected += [
        ROOT / "docs/PLANNER_HANDOFF.md",
        ROOT / "docs/PLANNER.md",
        ROOT / "docs/PLANNER_AUDIT.md",
        ROOT / "requirements.lock",
        ROOT / "evidence/planner_source_snapshot.json",
        ROOT / "evidence/planner_pytest.xml",
        ROOT / "evidence/planner_pytest.txt",
        ROOT / "evidence/planner_baseline.xml",
        ROOT / "evidence/planner_demo.txt",
        ROOT / "evidence/planner_cli.txt",
    ]
    archive = ROOT / "evidence/planning_bundle.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(selected):
            bundle.write(path, str(path.relative_to(ROOT)))
    archive_hash = sha(archive)
    (ROOT / "evidence/planning_bundle.sha256").write_text(
        f"{archive_hash}  planning_bundle.zip\n"
    )
    print(
        json.dumps(
            dict(
                tests=totals,
                archive=str(archive),
                sha256=archive_hash,
                changed_previous_files=changed,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
