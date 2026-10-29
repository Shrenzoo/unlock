"""Reproducible local harness. No web server, model inference or planner is implied."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time


PARAMETERS = dict(center_x_mm=0, center_y_mm=-20, width_mm=40, depth_mm=16)


def read_bounded(path: Path, limit: int):
    from .contracts import EngineError

    if path.stat().st_size > limit:
        raise EngineError("LIMIT_EXCEEDED", "input exceeds byte budget")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise EngineError("LIMIT_EXCEEDED", "input exceeds byte budget")
    return data


def run_demo_stage(stage: str, output: str, held_out: bool = False):
    from .export import export_bundle
    from .fixtures import generate_fixture
    from .geometry import fingerprint, volume, boolean
    from .service import construct_candidate, direct_path, import_revision
    from .verification import verify_candidate

    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    fixture = root / "input"
    if stage == "prepare":
        generate_fixture(fixture, "B02", held_out=held_out)
    timings = {}

    def measure(label, fn):
        started = time.perf_counter()
        value = fn()
        timings[label] = (time.perf_counter() - started) * 1000
        return value

    revision = measure(
        "import_ms",
        lambda: import_revision(
            fixture / "assembly.step",
            json.loads((fixture / "manifest.json").read_text()),
        ),
    )
    initial = {k: fingerprint(o.shape) for k, o in revision.by_id().items()}
    if stage == "prepare":
        baseline = measure(
            "translation_validation_ms",
            lambda: direct_path(revision, "target", "Z+", 80),
        )
    candidate = measure(
        "candidate_construction_ms",
        lambda: construct_candidate(revision, "bridge", "T01", PARAMETERS),
    )
    result = dict(candidate_id=candidate.id, timings_ms=timings)
    if stage == "prepare":
        result.update(
            synthetic=True,
            held_out=held_out,
            source_hash=revision.assembly.source_hash,
            manifest_hash=revision.manifest_hash,
            revision_id=revision.input_hash,
            occurrences=len(revision.assembly.occurrences),
            baseline=baseline.model_dump(mode="json"),
            candidate=candidate.record(),
            removed_volume_mm3=volume(
                boolean(
                    "cut", revision.by_id()["bridge"].shape, candidate.shapes["bridge"]
                )
            ),
        )
    elif stage == "verify":
        report = measure(
            "verification_ms", lambda: verify_candidate(revision, candidate)
        )
        result["verification"] = report.model_dump(mode="json")
    elif stage == "export":
        result["export"] = measure(
            "export_and_roundtrip_ms",
            lambda: export_bundle(revision, candidate, root / "export"),
        )
    else:
        raise ValueError("unsupported demo stage")
    result["original_unchanged"] = initial == {
        k: fingerprint(o.shape) for k, o in revision.by_id().items()
    }
    return result


def run_demo(output: str, held_out: bool = False):
    from .artifacts import ArtifactStore, atomic_write
    from .worker import isolated_operation

    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    history = ArtifactStore(root / "history")
    for name in (
        "summary.json",
        "failed_summary.json",
        "prepare.stage.json",
        "verify.stage.json",
        "export.stage.json",
    ):
        old = root / name
        if old.exists():
            history.put(old.read_bytes())
            old.unlink()
    stages = {}
    started = time.monotonic()
    for stage in ("prepare", "verify", "export"):
        if time.monotonic() - started >= 120:
            raise ValueError("whole demo exceeded 120 second budget")
        try:
            stages[stage] = isolated_operation(
                "demo_" + stage, dict(stage=stage, output=str(root), held_out=held_out)
            )
        except Exception as exc:
            atomic_write(
                root / "failed_summary.json",
                json.dumps(
                    dict(
                        status="failed",
                        stage=stage,
                        error=str(exc),
                        completed_stages=list(stages),
                    ),
                    indent=2,
                ).encode(),
            )
            raise
        atomic_write(
            root / (stage + ".stage.json"),
            json.dumps(stages[stage], sort_keys=True, indent=2).encode(),
        )
    summary = stages["prepare"]
    summary["verification"] = stages["verify"]["verification"]
    summary["export"] = stages["export"]["export"]
    summary["timings_ms"].update(
        verification_ms=stages["verify"]["timings_ms"]["verification_ms"],
        export_and_roundtrip_ms=stages["export"]["timings_ms"][
            "export_and_roundtrip_ms"
        ],
    )
    summary["worker_stages"] = {
        s: dict(
            candidate_id=r["candidate_id"], original_unchanged=r["original_unchanged"]
        )
        for s, r in stages.items()
    }
    summary["original_unchanged"] = all(
        r["original_unchanged"] for r in stages.values()
    )
    summary["claims"] = (
        "Known direct-segment obstruction becomes a checked forward/reverse direct segment after T01. No complete disassembly/replacement planner was run."
    )
    if (
        len({r["candidate_id"] for r in stages.values()}) != 1
        or not summary["original_unchanged"]
        or summary["verification"]["status"] != "passed"
        or summary["export"]["status"] != "full_assembly"
    ):
        atomic_write(
            root / "failed_summary.json",
            json.dumps(summary, sort_keys=True, indent=2).encode(),
        )
        raise ValueError("demo engineering gate failed; inspect failed_summary.json")
    atomic_write(
        root / "summary.json", json.dumps(summary, sort_keys=True, indent=2).encode()
    )
    return summary


def benchmark_iteration(fixtures_root: str, fixture_code: str):
    from .assembly import import_step
    from .geometry import collision, validate_solid
    from .service import import_revision, construct_candidate, direct_path
    from .verification import verify_candidate

    root = Path(fixtures_root)
    results = {}

    def timed(fn):
        t = time.perf_counter()
        value = fn()
        return value, (time.perf_counter() - t) * 1000

    if fixture_code not in ("B01", "B02", "B03"):
        raise ValueError("unknown benchmark fixture")
    for code in (fixture_code,):
        p = root / code
        assembly, import_ms = timed(lambda: import_step(p / "assembly.step"))
        _, validation_ms = timed(
            lambda: [validate_solid(o.shape) for o in assembly.occurrences]
        )
        rev, ready_ms = timed(
            lambda: import_revision(
                p / "assembly.step", json.loads((p / "manifest.json").read_text())
            )
        )
        ids = rev.by_id()
        _, collision_ms = timed(
            lambda: collision(ids["target"].shape, ids["base"].shape)
        )
        path, motion_ms = timed(lambda: direct_path(rev, "target", "Z+", 80))
        row = dict(
            import_ms=import_ms,
            solid_validation_ms=validation_ms,
            import_and_semantics_ms=ready_ms,
            collision_check_ms=collision_ms,
            translation_validation_ms=motion_ms,
            path_status=path.status,
            revision_id=rev.input_hash,
        )
        if code == "B02":
            c, construction_ms = timed(
                lambda: construct_candidate(rev, "bridge", "T01", PARAMETERS)
            )
            v, verification_ms = timed(lambda: verify_candidate(rev, c))
            row.update(
                candidate_construction_ms=construction_ms,
                verification_ms=verification_ms,
                verification_status=v.status,
            )
        results[code] = row
    return results


def write_schemas(output: Path):
    from .contracts import Manifest, InventoryItem, Finding, Policy, Proposal
    from .motion import PathResult
    from .verification import VerificationReport

    output.mkdir(parents=True, exist_ok=True)
    from .planning.contracts import (
        Action,
        Certificate,
        Metrics,
        PlanResult,
        Rejection,
        SearchPolicy,
        Step,
        ValidationReport,
        ErrorEnvelope,
    )

    for cls in (
        Manifest,
        InventoryItem,
        Finding,
        PathResult,
        VerificationReport,
        Policy,
        Proposal,
        Action,
        Certificate,
        Metrics,
        PlanResult,
        Rejection,
        SearchPolicy,
        Step,
        ValidationReport,
        ErrorEnvelope,
    ):
        schema = cls.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:unlock:{cls.__name__}:1.0"
        (output / f"{cls.__name__}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True)
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--held-out", action="store_true")
    fixture = sub.add_parser("fixtures")
    fixture.add_argument("--output", type=Path, required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--zip", type=Path)
    imp.add_argument("--step", type=Path)
    imp.add_argument("--manifest", type=Path)
    schemas = sub.add_parser("schemas")
    schemas.add_argument("--output", type=Path, required=True)
    bench = sub.add_parser("benchmark")
    bench.add_argument("--fixtures", type=Path, required=True)
    bench.add_argument("--output", type=Path, required=True)
    bench.add_argument("--repetitions", type=int, default=10)
    planner = sub.add_parser(
        "plan", help="Bounded state-aware CAD disassembly planning"
    )
    planner.add_argument("--step", type=Path, required=True)
    planner.add_argument("--manifest", type=Path, required=True)
    planner.add_argument("--target", required=True)
    planner.add_argument("--output", type=Path, required=True)
    planner.add_argument("--max-seconds", type=float, default=30)
    planner.add_argument("--max-states", type=int, default=4096)
    planner.add_argument("--expected-revision-id")
    planning_demo = sub.add_parser(
        "plan-demo", help="Real canonical, sequence and revised CAD planning evidence"
    )
    planning_demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            from .planning.contracts import SearchPolicy
            from .planning.runner import begin_run, plan_files, save_result

            begin_run(args.output)
            result = plan_files(
                args.step,
                args.manifest,
                args.target,
                SearchPolicy(
                    max_seconds=args.max_seconds, max_expanded_states=args.max_states
                ),
                expected_revision_id=args.expected_revision_id,
            )
            artifact = save_result(result, args.output)
            print(
                json.dumps(
                    dict(
                        status=result.status,
                        result_path=str((args.output / "result.json").resolve()),
                        artifact_id=artifact,
                        cost=result.metrics.cost if result.metrics else None,
                        steps=[
                            f"{s.kind} {s.component_id} {s.axis} {s.distance_mm:g}mm"
                            for s in result.steps
                        ],
                        complete=result.complete,
                        optimal_within_scope=result.optimal_within_scope,
                        replay=result.replay.status,
                        reverse=result.reverse.status,
                    ),
                    indent=2,
                )
            )
            if result.status in ("incomplete", "invalid_input", "cancelled"):
                raise SystemExit(2)
        elif args.command == "plan-demo":
            from .planning.demo import run_planning_demo

            print(json.dumps(run_planning_demo(args.output), indent=2))
        elif args.command == "demo":
            result = run_demo(str(args.output.resolve()), held_out=args.held_out)
            print(
                json.dumps(
                    dict(
                        summary_path=str((args.output / "summary.json").resolve()),
                        baseline=result["baseline"]["status"],
                        verification=result["verification"]["status"],
                        export=result["export"]["status"],
                        removed_volume_mm3=result["removed_volume_mm3"],
                        original_unchanged=result["original_unchanged"],
                    ),
                    indent=2,
                )
            )
        elif args.command == "fixtures":
            from .fixtures import generate_fixture

            for code in ("B01", "B02", "B03"):
                generate_fixture(args.output / code, code)
            generate_fixture(args.output / "B02-held-out", "B02", held_out=True)
            print(str(args.output.resolve()))
        elif args.command == "schemas":
            write_schemas(args.output)
        elif args.command == "import":
            from .contracts import POLICY
            from .package import load_files, load_zip
            from .worker import isolated_import

            if args.zip and not (args.step or args.manifest):
                package = load_zip(read_bounded(args.zip, POLICY.max_compressed_bytes))
            elif args.step and args.manifest and not args.zip:
                package = load_files(
                    {
                        "assembly.step": read_bounded(
                            args.step, POLICY.max_compressed_bytes
                        ),
                        "manifest.json": read_bounded(
                            args.manifest, POLICY.max_compressed_bytes
                        ),
                    }
                )
            else:
                parser.error("provide --zip or both --step and --manifest")
            print(json.dumps(isolated_import(package), indent=2))
        else:
            from .worker import isolated_operation

            if not 1 <= args.repetitions <= 100:
                parser.error("repetitions must be 1–100")
            runs = []
            for i in range(args.repetitions):
                t = time.perf_counter()
                row = {}
                for code in ("B01", "B02", "B03"):
                    row.update(
                        isolated_operation(
                            "benchmark",
                            dict(
                                fixtures_root=str(args.fixtures.resolve()),
                                fixture_code=code,
                            ),
                        )
                    )
                runs.append(
                    dict(
                        iteration=i,
                        worker_wall_ms=(time.perf_counter() - t) * 1000,
                        fixtures=row,
                    )
                )
                print(
                    f"Measured repetition {i + 1}/{args.repetitions} (three isolated fixture workers)",
                    flush=True,
                )
            aggregate = {}
            for code in ("B01", "B02", "B03"):
                aggregate[code] = {}
                for key in runs[0]["fixtures"][code]:
                    if key.endswith("_ms"):
                        values = sorted(r["fixtures"][code][key] for r in runs)
                        aggregate[code][key] = dict(
                            n=len(values),
                            p50=statistics.median(values),
                            p95=values[
                                max(0, __import__("math").ceil(0.95 * len(values)) - 1)
                            ],
                            min=values[0],
                            max=values[-1],
                        )
            result = dict(
                runtime=sys.version,
                platform=platform.platform(),
                machine=platform.machine(),
                cpu_count=os.cpu_count(),
                methodology="Three fresh native processes per repetition, one per fixture. Stage timers exclude Python/CAD import startup; worker_wall_ms spans the three processes. solid_validation_ms runs after import and can reuse internally cached validity for identical BReps. OS filesystem caches remain warm after the first iteration. No controlled cold-disk benchmark. p95 nearest rank.",
                runs=runs,
                aggregate_ms=aggregate,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2))
    except Exception as exc:
        from .contracts import EngineError

        print(
            json.dumps(
                exc.envelope()
                if isinstance(exc, EngineError)
                else dict(error=type(exc).__name__, message=str(exc))
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
