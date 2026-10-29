"""Bounded native coordinator adapter and content-addressed result persistence."""

import json
from pathlib import Path
import tempfile
import time

from ..artifacts import ArtifactStore, atomic_write
from ..contracts import EngineError
from ..package import load_files
from ..worker import _run_worker
from .contracts import PlanResult, SearchPolicy
from .service import empty_result


def isolated_plan(
    package,
    target_id,
    policy=SearchPolicy(),
    *,
    template=None,
    expected_revision_id=None,
    cancel_event=None,
):
    """Accept a validated InputPackage; no caller-supplied native shape or pass flag."""
    with tempfile.TemporaryDirectory(prefix="unlock-plan-") as tmp:
        root = Path(tmp)
        (root / "assembly.step").write_bytes(package.step)
        (root / "manifest.json").write_text(
            json.dumps(package.manifest, allow_nan=False)
        )
        (root / "request.json").write_text(
            json.dumps(
                dict(
                    target_id=target_id,
                    policy=policy.model_dump(),
                    template=template,
                    expected_revision_id=expected_revision_id,
                ),
                allow_nan=False,
            )
        )
        try:
            data = _run_worker(
                root,
                "plan",
                180,
                cancel_event,
                phase_limits={
                    "import": 60,
                    "prepare": 30,
                    "search": policy.max_seconds,
                    "replay": 30,
                    "reverse": 30,
                    "constraints": 30,
                },
            )
            result = PlanResult.model_validate(data)
            if cancel_event is not None and cancel_event.is_set():
                return interrupted_result(
                    root,
                    target_id,
                    policy,
                    "cancelled",
                    "cancelled before result commit",
                )
            return result
        except KeyboardInterrupt:
            return interrupted_result(
                root, target_id, policy, "cancelled", "keyboard cancellation"
            )
        except EngineError as exc:
            return interrupted_result(
                root,
                target_id,
                policy,
                "cancelled" if exc.code == "CANCELLED" else "incomplete",
                str(exc),
            )


def interrupted_result(root, target_id, policy, status, reason):
    error = EngineError(
        "CANCELLED" if status == "cancelled" else "GEOMETRY_FAILED", reason
    ).envelope()
    checkpoint = root / "checkpoint.json"
    if checkpoint.exists():
        data = json.loads(checkpoint.read_text())
        data.update(
            status=status,
            complete=False,
            optimal_within_scope=False,
            steps=[],
            metrics=None,
            replacement_verified=False,
            error=error,
        )
        data["stats"]["termination"] = "native_interruption"
        data["stats"]["frontier_status"] = "interrupted"
        phase_file = root / "phase.json"
        if phase_file.exists():
            phase = json.loads(phase_file.read_text())
            if phase["name"] == "search":
                data["elapsed_ms"] = (time.monotonic() - phase["started"]) * 1000
        # A killed geometry query has no conclusive certificate.
        data["unresolved_transition_count"] += int(status == "incomplete")
        from .service import result_record

        data.pop("id")
        validated = PlanResult.model_validate({"id": "pending", **data})
        return result_record(**validated.model_dump(exclude={"id"}))
    return empty_result(target_id, policy, status=status, error=error)


def run_native(root):
    """Executed only in the isolated worker; phase deadlines are parent-enforced."""
    from ..service import construct_candidate, import_revision
    from .problem import Problem
    from .service import plan_problem, result_record, base_fields

    root = Path(root)
    request = json.loads((root / "request.json").read_text())
    policy = SearchPolicy.model_validate(request["policy"])

    def phase(name):
        atomic_write(
            root / "phase.json",
            json.dumps(dict(name=name, started=time.monotonic())).encode(),
        )

    def checkpoint(result):
        atomic_write(root / "checkpoint.json", result.model_dump_json().encode())

    try:
        phase("import")
        revision = import_revision(
            root / "assembly.step", json.loads((root / "manifest.json").read_text())
        )
        phase("prepare")
        candidate = None
        if request["template"]:
            template = request["template"]
            if set(template) != {"bracket_id", "template_id", "parameters"}:
                raise EngineError(
                    "UNSUPPORTED_TEMPLATE", "template request has unexpected fields"
                )
            candidate = construct_candidate(revision, **template)
        problem = Problem(
            revision,
            request["target_id"],
            policy,
            candidate=candidate,
            expected_revision_id=request["expected_revision_id"],
        )
        checkpoint(
            result_record(
                **base_fields(problem),
                status="incomplete",
                complete=False,
                optimal_within_scope=False,
            )
        )
        return plan_problem(problem, progress=checkpoint, phase=phase).model_dump(
            mode="json"
        )
    except EngineError as exc:
        return empty_result(
            request["target_id"], policy, error=exc.envelope()
        ).model_dump(mode="json")


def plan_files(step_path, manifest_path, target_id, policy=SearchPolicy(), **kwargs):
    paths = {"assembly.step": Path(step_path), "manifest.json": Path(manifest_path)}
    from ..contracts import POLICY

    try:
        data = {}
        for name, path in paths.items():
            with path.open("rb") as stream:
                data[name] = stream.read(POLICY.max_compressed_bytes + 1)
            if len(data[name]) > POLICY.max_compressed_bytes:
                raise EngineError("LIMIT_EXCEEDED", "input exceeds byte budget")
        package = load_files(data)
        return isolated_plan(package, target_id, policy, **kwargs)
    except (EngineError, OSError) as exc:
        error = (
            exc
            if isinstance(exc, EngineError)
            else EngineError("INVALID_PACKAGE", str(exc))
        )
        return empty_result(target_id, policy, error=error.envelope())


def begin_run(output):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    store = ArtifactStore(root / "artifacts")
    for name in ("result.json", "latest.json"):
        old = root / name
        if old.exists():
            store.put(old.read_bytes())
            old.unlink()
    atomic_write(
        root / "latest.json",
        json.dumps(dict(status="running", completed=False)).encode(),
    )


def retrieve_result(output, artifact_id):
    from .service import validate_saved_result

    data = ArtifactStore(Path(output).resolve() / "artifacts").get(artifact_id)
    result = PlanResult.model_validate_json(data)
    validate_saved_result(result)
    return result.model_copy(update={"provenance": "retrieved"})


def save_result(result, output):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # CAS preserves earlier evidence. The mutable pointer names the actual latest
    # computation, including incomplete/invalid/cancelled results.
    artifact_id = ArtifactStore(root / "artifacts").put(
        result.model_dump_json(indent=2).encode()
    )
    atomic_write(root / "result.json", result.model_dump_json(indent=2).encode())
    atomic_write(
        root / "latest.json",
        json.dumps(
            dict(artifact_id=artifact_id, plan_id=result.id, status=result.status)
        ).encode(),
    )
    return artifact_id
