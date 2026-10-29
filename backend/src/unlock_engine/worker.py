"""Bounded native import worker. Coordinator cancellation terminates the process."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .contracts import EngineError


def isolated_import(package, *, timeout_seconds=60, cancel_event=None):
    if not 0 < timeout_seconds <= 60:
        raise ValueError("import budget must be in (0,60] seconds")
    with tempfile.TemporaryDirectory(prefix="unlock-worker-") as tmp:
        work = Path(tmp)
        (work / "assembly.step").write_bytes(package.step)
        (work / "manifest.json").write_text(
            json.dumps(package.manifest, allow_nan=False)
        )
        return _run_worker(work, "import", timeout_seconds, cancel_event)


def isolated_operation(operation, request, *, timeout_seconds=30, cancel_event=None):
    if operation not in ("demo_prepare", "demo_verify", "demo_export", "benchmark"):
        raise ValueError("unsupported native operation")
    if not 0 < timeout_seconds <= 30:
        raise ValueError("native operation budget must be in (0,30] seconds")
    with tempfile.TemporaryDirectory(prefix="unlock-worker-") as tmp:
        work = Path(tmp)
        (work / "request.json").write_text(json.dumps(request, allow_nan=False))
        return _run_worker(work, operation, timeout_seconds, cancel_event)


def _run_worker(work, operation, timeout_seconds, cancel_event, *, phase_limits=None):
    env = {
        k: v
        for k, v in os.environ.items()
        if not (
            k.endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD"))
            or k in ("AWS_SESSION_TOKEN",)
        )
    }
    source = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = source + os.pathsep + env.get("PYTHONPATH", "")
    env["OMP_NUM_THREADS"] = "1"
    with (work / "native.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "unlock_engine.worker", str(work), operation],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            env=env,
        )
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise EngineError("CANCELLED", "native operation cancelled")
                if time.monotonic() - started > timeout_seconds:
                    raise EngineError(
                        "GEOMETRY_FAILED",
                        "native operation timed out; no completed revision",
                    )
                if phase_limits and (work / "phase.json").exists():
                    phase = json.loads((work / "phase.json").read_text())
                    if (
                        time.monotonic() - phase["started"]
                        > phase_limits[phase["name"]]
                    ):
                        raise EngineError(
                            "LIMIT_EXCEEDED",
                            f"native {phase['name']} phase exceeded its deadline",
                        )
                elif phase_limits and time.monotonic() - started > 60:
                    raise EngineError(
                        "LIMIT_EXCEEDED", "native runtime startup exceeded its deadline"
                    )
                time.sleep(0.02)
            if process.returncode != 0 or not (work / "result.json").exists():
                detail = (
                    json.loads((work / "failure.json").read_text())
                    if (work / "failure.json").exists()
                    else {}
                )
                raise EngineError(
                    "GEOMETRY_FAILED",
                    f"native worker interrupted (exit {process.returncode}): {detail}; no completed revision",
                )
            return json.loads((work / "result.json").read_text())
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    work = Path(sys.argv[1])
    # Limits are installed before importing the CAD stack. RLIMIT_AS is Linux-only
    # here because macOS mapped frameworks make an address-space cap misleading.
    import resource

    cpu_limit = (
        180
        if len(sys.argv) > 2 and sys.argv[2] in ("plan", "ai_verify", "http_export")
        else 60
    )
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024**2, 100 * 1024**2))
    from .artifacts import atomic_write

    try:
        operation = sys.argv[2]
        if operation == "import":
            from .service import import_revision

            result = import_revision(
                work / "assembly.step", json.loads((work / "manifest.json").read_text())
            ).inventory()
        elif operation == "plan":
            from .planning.runner import run_native

            result = run_native(work)
        elif operation in ("http_fixture", "http_import", "http_export"):
            from .api.native import run

            result = run(work, operation)
        elif operation in ("ai_construct", "ai_verify"):
            from .ai.native import run_ai_operation

            result = run_ai_operation(work, operation)
        elif operation in ("demo_prepare", "demo_verify", "demo_export", "benchmark"):
            from .cli import run_demo_stage, benchmark_iteration

            request = json.loads((work / "request.json").read_text())
            result = (
                run_demo_stage if operation.startswith("demo_") else benchmark_iteration
            )(**request)
        else:
            raise ValueError("unsupported native operation")
        atomic_write(work / "result.json", json.dumps(result, allow_nan=False).encode())
    except Exception as exc:
        # Separate failure record; never the completed-result filename.
        atomic_write(
            work / "failure.json",
            json.dumps(dict(error=type(exc).__name__, message=str(exc))).encode(),
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
