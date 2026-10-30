"""Bounded native import worker. Coordinator cancellation terminates the process."""

from __future__ import annotations

import contextlib
import functools
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import threading
import time

from .contracts import EngineError

# Every operation a worker can run. Callers pass internal literals only; anything
# else is refused before a process starts (and again inside a standby).
NATIVE_OPERATIONS = frozenset(
    {
        "import",
        "plan",
        "http_fixture",
        "http_import",
        "http_export",
        "ai_construct",
        "ai_verify",
        "demo_prepare",
        "demo_verify",
        "demo_export",
        "benchmark",
    }
)
HEAVY_OPERATIONS = ("plan", "ai_verify", "http_export")
STARTUP_LIMIT_S = 60

# Optional warm standby. Process start-up and the CAD stack import cost several
# seconds per operation; a standby pays that cost while the model thinks between
# operations. It is a fresh, single-use process that has installed its limits and
# imported libraries only: it accepts exactly one request and exits, so no
# engineering state is ever shared between operations.
#
# Resource policy: at most one pooled CAD process exists at a time. A replacement
# starts only after the operation that consumed the previous standby has exited,
# so peak worker memory equals the cold path. UNLOCK_PREWARM_WORKERS=0 disables it.
#
# Handoff: a standby writes ACCEPTED before doing any work. Without it the
# operation provably never started and is safely cold-started; after it, any
# failure is the operation's own and is never retried.
ACCEPTED = b"accepted\n"
_standby_lock = threading.Lock()
_standby: subprocess.Popen | None = None
_standby_depth = 0
STANDBY_STATS = dict(handovers=0, cold_starts=0, spawn_failures=0, handoff_failures=0)


def cpu_limit_for(operation: str) -> int:
    return 180 if operation in HEAVY_OPERATIONS else 60


def prewarm_enabled() -> bool:
    return os.environ.get("UNLOCK_PREWARM_WORKERS", "1") != "0"


def _checked_request(work, operation) -> Path:
    if operation not in NATIVE_OPERATIONS:
        raise ValueError("unsupported native operation")
    work = Path(work)
    if not work.is_absolute() or not work.is_dir():
        raise ValueError("native work directory must be an existing absolute path")
    return work


def _worker_env() -> dict:
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
    return env


def _spawn_standby() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "unlock_engine.worker", "--standby"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_worker_env(),
    )


def _stop(process: subprocess.Popen):
    for pipe in (process.stdin, process.stdout):
        with contextlib.suppress(OSError):
            if pipe:
                pipe.close()
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _replenish():
    """Start an idle standby if a pool is active and no pooled process exists.

    Best-effort: a refused process start only means the next operation cold-starts.
    """
    global _standby
    with _standby_lock:
        if _standby_depth == 0 or _standby is not None or not prewarm_enabled():
            return
        try:
            _standby = _spawn_standby()
        except (OSError, subprocess.SubprocessError):
            STANDBY_STATS["spawn_failures"] += 1


def _take_standby() -> subprocess.Popen | None:
    """Claim the idle standby; its replacement starts after this operation ends."""
    global _standby
    with _standby_lock:
        process, _standby = _standby, None
    if process is not None and process.poll() is not None:
        _stop(process)
        return None  # died while idle; the caller cold-starts instead
    return process


def _await_acceptance(process, started, timeout_seconds, cancel_event, phase_limits):
    """True once the standby accepted; False if it ended or answered otherwise."""
    fd = process.stdout.fileno()
    received = b""
    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise EngineError("CANCELLED", "native operation cancelled")
        elapsed = time.monotonic() - started
        if elapsed > timeout_seconds:
            raise EngineError(
                "GEOMETRY_FAILED", "native operation timed out; no completed revision"
            )
        if phase_limits and elapsed > STARTUP_LIMIT_S:
            raise EngineError(
                "LIMIT_EXCEEDED", "native runtime startup exceeded its deadline"
            )
        ready, _, _ = select.select([fd], [], [], 0.02)
        if not ready:
            continue
        chunk = os.read(fd, len(ACCEPTED))
        if not chunk:
            return False
        received += chunk
        if received == ACCEPTED:
            return True
        if not ACCEPTED.startswith(received):
            return False


def _hand_over(work, operation, started, timeout_seconds, cancel_event, phase_limits):
    """The accepted standby process, or None when the caller should cold-start."""
    process = _take_standby()
    if process is None:
        return None
    try:
        process.stdin.write((json.dumps([str(work), operation]) + "\n").encode())
        process.stdin.close()
        accepted = _await_acceptance(
            process, started, timeout_seconds, cancel_event, phase_limits
        )
    except OSError:
        accepted = False
    except EngineError:
        _stop(process)
        raise
    if not accepted:
        _stop(process)
        STANDBY_STATS["handoff_failures"] += 1
        return None
    process.stdout.close()
    STANDBY_STATS["handovers"] += 1
    return process


@contextlib.contextmanager
def prewarmed_workers():
    """Keep one idle single-use worker ready between operations in the block."""
    global _standby, _standby_depth
    with _standby_lock:
        _standby_depth += 1
    try:
        _replenish()
        yield
    finally:
        with _standby_lock:
            _standby_depth -= 1
            idle = _standby if _standby_depth == 0 else None
            if idle is not None:
                _standby = None
        if idle is not None:
            _stop(idle)


def with_prewarmed_workers(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with prewarmed_workers():
            return fn(*args, **kwargs)

    return wrapper


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
    work = _checked_request(work, operation)
    try:
        return _supervise(work, operation, timeout_seconds, cancel_event, phase_limits)
    finally:
        _replenish()


def _supervise(work, operation, timeout_seconds, cancel_event, phase_limits):
    with (work / "native.log").open("wb") as log:
        started = time.monotonic()
        process = _hand_over(
            work, operation, started, timeout_seconds, cancel_event, phase_limits
        )
        if process is None:
            STANDBY_STATS["cold_starts"] += 1
            process = subprocess.Popen(
                [sys.executable, "-m", "unlock_engine.worker", str(work), operation],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env=_worker_env(),
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
    standby = sys.argv[1:2] == ["--standby"]
    # Limits are installed before importing the CAD stack. RLIMIT_AS is Linux-only
    # here because macOS mapped frameworks make an address-space cap misleading.
    import resource

    # A standby does not know its operation yet: it starts under the larger cap
    # and lowers it to that operation's own cap before any work begins. CPU time
    # is counted from process start either way.
    cpu_limit = (
        cpu_limit_for(HEAVY_OPERATIONS[0])
        if standby
        else cpu_limit_for(sys.argv[2] if len(sys.argv) > 2 else "")
    )
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024**2, 100 * 1024**2))
    from .artifacts import atomic_write

    if standby:
        from . import service  # noqa: F401  (warm the CAD stack only)
        from .planning import runner  # noqa: F401

        line = sys.stdin.readline()
        try:
            work_text, operation = json.loads(line)
            _checked_request(work_text, operation)
        except (ValueError, TypeError):
            return  # pool closed, parent gone or invalid request: never accepted
        # Accept before any engineering work, so a missing acceptance proves the
        # operation never ran and the parent may cold-start it.
        os.write(1, ACCEPTED)
        log = os.open(
            Path(work_text) / "native.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND
        )
        os.dup2(log, 1)
        os.dup2(log, 2)
        os.close(log)
        limit = cpu_limit_for(operation)
        resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
        sys.argv[1:] = [work_text, operation]
    work = Path(sys.argv[1])

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
