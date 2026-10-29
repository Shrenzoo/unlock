"""Build the handoff from observed JSON/JUnit evidence, never expected outcomes."""

from importlib.metadata import version
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
summary = json.loads((root / "evidence/demo/summary.json").read_text())
benchmark = json.loads((root / "evidence/benchmark.json").read_text())
suites = ET.parse(root / "evidence/pytest.xml").getroot().findall(".//testsuite")
counts = {
    key: sum(int(s.attrib.get(key, 0)) for s in suites)
    for key in ("tests", "failures", "errors", "skipped")
}
if counts["failures"] or counts["errors"]:
    raise SystemExit("Refusing to write a successful handoff for a failing suite")
if (
    summary["verification"]["status"] != "passed"
    or summary["export"]["status"] != "full_assembly"
    or not summary["original_unchanged"]
):
    raise SystemExit("Refusing to describe an incomplete demo as completed")
lines = [
    "# UNLOCK geometry engineering handoff",
    "",
    "Implemented and executed locally on October 28, 2026. Scope is the supported geometry subsystem. The full UNLOCK application and complete repair-route verification remain separate work.",
    "",
    "## Implemented",
    "",
    "Safe STEP/manifest packages; XDE hierarchy, occurrence identity and placements; single-solid validity; BRep collision and clearance evidence; continuous conservative six-axis translations; restricted planar contacts; shaft/handle tool volumes and screw extraction; matched bridge constructors with T01/T02; independent material/constraint checks; immutable artifacts; preview mapping; STEP export and actual reimport. Existing frontend code is unchanged.",
    "",
    "Primary files: `src/unlock_engine/{contracts,package,assembly,geometry,motion,tools,templates,service,verification,export,artifacts,preview,worker,cli}.py`. Seven versioned JSON schemas are in `schemas/`. Numerical and interpretation decisions, requirement mapping and source-document hashes are in [DECISIONS.md](DECISIONS.md).",
    "",
    "## Runtime and checks",
    "",
    f"- Python: `{sys.version.split()[0]}`.",
    f"- CadQuery `{version('cadquery')}`; cadquery-ocp `{version('cadquery-ocp')}`; Pydantic `{version('pydantic')}`; pytest `{version('pytest')}`; Ruff `{version('ruff')}`.",
    f"- Final pytest: **{counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']} passed, {counts['failures']} failed, {counts['errors']} errors, {counts['skipped']} skipped**. Actual output and durations: [pytest.txt](../evidence/pytest.txt), [JUnit XML](../evidence/pytest.xml).",
    "- Ruff format/check, dependency consistency check and existing frontend TypeScript check passed. Dependency deprecation warnings and the intentional duplicate-ZIP warning remain visible in pytest output.",
    "",
    "Commands executed from the repository root:",
    "",
    "```sh",
    "backend/.venv/bin/python -m pytest backend/tests -q --junitxml=backend/evidence/pytest.xml --durations=10",
    "backend/.venv/bin/ruff check backend/src backend/tests",
    "backend/.venv/bin/ruff format --check backend/src backend/tests",
    "backend/.venv/bin/python -m pip check",
    "npm --prefix frontend run typecheck",
    "backend/.venv/bin/unlock-engine fixtures --output backend/evidence/fixtures",
    "backend/.venv/bin/unlock-engine demo --output backend/evidence/demo",
    "backend/.venv/bin/unlock-engine benchmark --fixtures backend/evidence/fixtures --output backend/evidence/benchmark.json --repetitions 10",
    "```",
    "",
    "Tests use real OCCT geometry, including a 0.001 mm intermediate obstacle between clear endpoints, contact/inward/hidden-material cases, rotated nested hierarchy, repeated definitions and occurrence-local bracket editing, protected-hole corruption, disconnected geometry, stale parameters, unknown/missing mandatory checks, export failures, cancellation, abrupt worker termination and actual assembly reimport. Kernel mocking is not used to establish geometric correctness; injected writer failures and a killed process exercise supervision/error handling.",
    "",
    "Initial implementation runs exposed absent OCP APIs, solid/solid tangency returning no contact face, mutation of shared topology flags, and contamination of a shared test fixture. These were corrected with installed-binding probes, explicit planar boundary checks, private copies and isolated corrupt-candidate inputs. Timeouts remained failures; they were addressed by separate bounded stages.",
    "",
    "## Executed CAD demonstration",
    "",
    f"- Imported **{summary['occurrences']}** separate occurrences from genuine synthetic AP214 STEP, including a repeated screw definition at distinct placements.",
    f"- Original target direct Z+ segment: **{summary['baseline']['status']}**, with stored BRep obstruction evidence.",
    f"- T01 parameters: `{json.dumps(summary['candidate']['parameters'], sort_keys=True)}`; actual removed material **{summary['removed_volume_mm3']:.3f} mm³**.",
    f"- Independent verification: **{summary['verification']['status']}**, {len(summary['verification']['checks'])} individual checks. Explicit forward and reverse direct segments are included; the staging endpoint is checked.",
    f"- Original geometry unchanged: **{summary['original_unchanged']}**.",
    f"- Export: **{summary['export']['status']}**; actual reimport and independent geometry/path checks **{summary['export']['roundtrip_status']}**. Changed-part STEP also passed reimport.",
    "",
    f"[Actual CAD/evidence ZIP](../evidence/demo/export/{Path(summary['export']['zip_path']).name}) · [Machine-readable summary](../evidence/demo/summary.json)",
    "",
    "| Identity | SHA-256 |",
    "|---|---|",
    f"| Source STEP | `{summary['source_hash']}` |",
    f"| Manifest | `{summary['manifest_hash']}` |",
    f"| Original bracket BRep | `{summary['candidate']['original_shape_ref']['geometry_hash']}` |",
    f"| Revised bracket BRep | `{summary['candidate']['revised_shape_ref']['geometry_hash']}` |",
    f"| Candidate | `{summary['candidate']['id']}` |",
    f"| Verification report | `{summary['verification']['id']}` |",
    "",
    "## Observed performance",
    "",
    f"Environment: `{benchmark['platform']}`, {benchmark['cpu_count']} logical CPUs. RAM capacity was not verified through the sandbox. These are local development observations on synthetic fixtures, not qualification of the PRD's reference 8-core/16-GB Linux worker.",
    "",
    benchmark["methodology"],
    "",
    "| Fixture / stage | n | p50 ms | p95 ms |",
    "|---|---:|---:|---:|",
]
for code, stages in benchmark["aggregate_ms"].items():
    for name, data in stages.items():
        lines.append(
            f"| {code} / {name} | {data['n']} | {data['p50']:.2f} | {data['p95']:.2f} |"
        )
lines += [
    "",
    f"Final demo export plus reimport and repeated constraints/path checks: **{summary['timings_ms']['export_and_roundtrip_ms']:.2f} ms**, n=1. No export p95 is claimed. Raw samples: [benchmark.json](../evidence/benchmark.json).",
    "",
    "## Limits and next integration",
    "",
    "Only uniformly millimetre STEP assemblies and single closed-solid leaf occurrences are supported. Contact exceptions require isolated world-axis planar material regions; complex/terminal contacts can remain unknown. Proxy overlap without decisive CAD evidence stays unknown. Exact strength, force, torque, threads, flexible parts, manufacturing, electrical safety and restored function are unverified. STEP preserves editable solids and supported assembly structure, not native feature history or mates.",
    "",
    "No disassembly optimizer or complete state-based reverse sequence was integrated, so no full repair-route or operation-count improvement is claimed. No Muse calls, FastAPI coordinator, authentication or live frontend integration were added. No real manufactured assembly or independent human engineering review was performed. Synthetic fixture redistribution rights remain pending. Docker/Podman was unavailable: the Linux image, base digest and Linux resource caps remain unvalidated. The supplied Dockerfile is a deployment starting point, not a tested container release.",
    "",
    "The planner should consume `validate_translation` and `evaluate_fastener` under checked semantic states. The Muse controller should consume the Proposal schema, server grids and `construct_candidate`, while the independent verifier owns pass/fail. FastAPI should own immutable job/revision state, one-job scheduling, isolated native execution and access control. The frontend adapter should consume normalized inventory, findings, certificates, reports and explicitly metre-scaled previews. All are separate integration responsibilities; the current viewer still uses its existing fixture/HTTP boundary.",
    "",
]
ap242 = json.loads((root / "evidence/ap242_smoke.json").read_text())
if ap242["status"] != "passed":
    raise SystemExit("AP242 smoke did not pass")
lines += [
    "",
    "## Additional AP242 check",
    "",
    f"Real AP214 → XDE → AP242 export/reimport preserved {ap242['occurrences']} occurrences; measured symmetric material differences were `{ap242['symmetric_differences_mm3']}` mm³. [Actual AP242 STEP](../evidence/ap242_assembly.step), [report](../evidence/ap242_smoke.json), reproducible command: `backend/.venv/bin/python backend/scripts/check_ap242.py`.",
    "",
]
(root / "docs/HANDOFF.md").write_text("\n".join(lines))
print(root / "docs/HANDOFF.md")
