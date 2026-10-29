"""Reproducible demonstrations; action lists are always discovered by UCS."""

import json
from pathlib import Path
import time

from ..artifacts import atomic_write
from ..fixtures import generate_fixture
from .fixtures import sequence_fixture
from .runner import begin_run, plan_files, save_result
from .service import compare_plans


def run_planning_demo(output):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Never leave an earlier passing overview as the current run on interruption.
    previous = root / "summary.json"
    if previous.exists():
        from ..artifacts import ArtifactStore

        ArtifactStore(root / "history").put(previous.read_bytes())
        previous.unlink()
    results = {}
    measurements = {}

    def run(name, inputs, target="target", template=None):
        print(f"Planning {name} (real CAD, isolated worker)", flush=True)
        begin_run(root / name)
        started = time.monotonic()
        result = plan_files(
            inputs / "assembly.step",
            inputs / "manifest.json",
            target,
            template=template,
        )
        measurements[name] = dict(
            worker_wall_ms=(time.monotonic() - started) * 1000,
            search_ms=result.elapsed_ms,
            expanded_states=result.expanded_states,
            peak_frontier=result.stats.peak_frontier,
            geometry_calls=result.stats.geometry_validation_calls,
            cache_hits=result.stats.cache_hits,
            cache_misses=result.stats.cache_misses,
            rejected=result.stats.rejected_transitions,
            unknown=result.stats.unknown_transitions,
            replay_ms=result.replay.elapsed_ms,
            reverse_ms=result.reverse.elapsed_ms,
        )
        save_result(result, root / name)
        results[name] = result
        return result

    inputs = {}
    for code in ("B01", "B02", "B03"):
        inputs[code] = generate_fixture(root / "inputs" / code, code)
        run(code, inputs[code])
    # B03's original selected target is not retained by its obstructed screw.
    # Selecting its annotated cover is a separate, explicitly versioned problem.
    p = inputs["B03"]
    m = json.loads((p / "manifest.json").read_text())
    for c in m["components"]:
        if c["id"] == "cover":
            c["replaceable"] = True
    m["constraints"][0]["component_ids"] = ["cover"]
    cover_input = root / "inputs" / "B03-cover"
    cover_input.mkdir(parents=True, exist_ok=True)
    (cover_input / "assembly.step").write_bytes((p / "assembly.step").read_bytes())
    (cover_input / "manifest.json").write_text(json.dumps(m, indent=2))
    run("B03-cover", cover_input, "cover")
    sequence = sequence_fixture(
        root / "inputs" / "sequence", tools=("driver_a", "driver_b")
    )
    run("sequence", sequence)
    for template, params in (
        ("T01", dict(center_x_mm=0, center_y_mm=-20, width_mm=40, depth_mm=16)),
        ("T02", dict(offset_y_mm=24)),
    ):
        revised = run(
            "B02-" + template,
            inputs["B02"],
            template=dict(bracket_id="bridge", template_id=template, parameters=params),
        )
        atomic_write(
            root / ("comparison-" + template + ".json"),
            json.dumps(compare_plans(results["B02"], revised), indent=2).encode(),
        )
    overview = dict(
        synthetic=True,
        sample_count_per_case=1,
        cases={
            k: dict(
                status=r.status,
                target_id=r.target_id,
                cost=r.metrics.cost if r.metrics else None,
                complete=r.complete,
                optimal=r.optimal_within_scope,
                steps=[
                    dict(
                        kind=s.kind,
                        component_id=s.component_id,
                        axis=s.axis,
                        distance_mm=s.distance_mm,
                    )
                    for s in r.steps
                ],
                replay=r.replay.status,
                reverse=r.reverse.status,
                replacement_verified=r.replacement_verified,
                result_path=str(root / k / "result.json"),
            )
            for k, r in results.items()
        },
        measurements=measurements,
    )
    atomic_write(root / "summary.json", json.dumps(overview, indent=2).encode())
    expected = {
        "B01": "feasible",
        "B02": "no_path_supported",
        "B03": "no_path_supported",
        "B03-cover": "no_path_supported",
        "sequence": "feasible",
        "B02-T01": "feasible",
        "B02-T02": "feasible",
    }
    if any(results[k].status != value for k, value in expected.items()) or not all(
        results[k].replacement_verified
        for k in ("B01", "sequence", "B02-T01", "B02-T02")
    ):
        raise ValueError(
            "planning demonstration gate failed; inspect actual serialized outcomes"
        )
    return overview
