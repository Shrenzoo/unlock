"""Native operations for the AI tools. Executed only inside an isolated worker process.

ai_construct: trusted constructor for one admitted template request.
ai_verify:    independent reconstruction in a fresh process, static verification,
              then the existing state-aware planner (search, replay, reverse and
              mandatory checks) on the reconstructed revision.
No caller pass flags, meshes or action lists are accepted.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..artifacts import atomic_write
from ..contracts import EngineError

TEMPLATE_FIELDS = {"bracket_id", "template_id", "parameters"}


def run_ai_operation(work: Path, operation: str) -> dict:
    from ..service import construct_candidate, import_revision

    work = Path(work)
    request = json.loads((work / "request.json").read_text())

    def phase(name):
        atomic_write(
            work / "phase.json",
            json.dumps(dict(name=name, started=time.monotonic())).encode(),
        )

    phase("import")
    revision = import_revision(
        work / "assembly.step", json.loads((work / "manifest.json").read_text())
    )
    if revision.input_hash != request["expected_revision_hash"]:
        return dict(
            ok=False,
            error=EngineError(
                "STALE_REVISION", "revision input hash changed"
            ).envelope(),
        )
    template = request["template"]
    if set(template) != TEMPLATE_FIELDS:
        return dict(
            ok=False,
            error=EngineError(
                "UNSUPPORTED_TEMPLATE", "template request has unexpected fields"
            ).envelope(),
        )
    phase("prepare")
    started = time.monotonic()
    try:
        candidate = construct_candidate(revision, **template)
    except EngineError as exc:
        return dict(
            ok=False,
            error=exc.envelope(),
            construct_ms=(time.monotonic() - started) * 1000,
        )
    construct_ms = (time.monotonic() - started) * 1000
    if operation == "ai_construct":
        from ..geometry import boolean, bounds, difference_volume, volume

        original = revision.by_id()[candidate.bracket_id].shape
        modified = candidate.shapes[candidate.bracket_id]
        removed = boolean("cut", original, modified)
        added = boolean("cut", modified, original)
        region = bounds(removed) if removed.Solids() else bounds(added)
        if request.get("persist_geometry"):
            import cadquery as cq
            from ..assembly import export_assembly
            from ..preview import preview_meshes

            atomic_write(
                work / "preview.json",
                json.dumps(preview_meshes(candidate.shapes), allow_nan=False).encode(),
            )
            cq.exporters.export(modified.copy(), str(work / "changed_bracket.step"))
            export_assembly(
                revision.assembly,
                work / "constructed_assembly.step",
                {
                    revision.by_id()[
                        candidate.bracket_id
                    ].source_occurrence_path: modified.copy()
                },
            )
        return dict(
            ok=True,
            candidate=candidate.record(),
            geometry_diff=dict(
                changed_component_id=candidate.bracket_id,
                removed_volume_mm3=volume(removed),
                added_volume_mm3=volume(added),
                region_min_mm=region.min,
                region_max_mm=region.max,
            ),
            changed_volume_mm3=difference_volume(
                original, candidate.shapes[candidate.bracket_id]
            ),
            construct_ms=construct_ms,
        )
    if operation != "ai_verify":
        raise ValueError("unsupported AI native operation")

    from ..planning.contracts import SearchPolicy
    from ..planning.problem import Problem
    from ..planning.service import empty_result, plan_problem
    from ..verification import verify_candidate

    if candidate.id != request["expected_candidate_id"]:
        # Independent reconstruction disagrees with the constructed record.
        return dict(
            ok=False,
            error=EngineError(
                "VERIFICATION_UNKNOWN",
                "reconstructed candidate identity differs from the constructed record",
            ).envelope(),
        )
    phase("constraints")
    started = time.monotonic()
    report = verify_candidate(revision, candidate, static_only=True)
    static_ms = (time.monotonic() - started) * 1000
    out = dict(
        ok=True,
        candidate_id=candidate.id,
        static_report=report.model_dump(mode="json"),
        static_ms=static_ms,
        plan=None,
    )
    if report.status != "passed":
        return out
    policy = SearchPolicy.model_validate(request["search_policy"])
    try:
        problem = Problem(revision, request["target_id"], policy, candidate=candidate)
        plan = plan_problem(problem, phase=phase)
    except EngineError as exc:
        plan = empty_result(
            request["target_id"], policy, revision_id=candidate.id, error=exc.envelope()
        )
    out["plan"] = plan.model_dump(mode="json")
    return out
