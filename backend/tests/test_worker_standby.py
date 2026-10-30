"""Warm single-use worker standby: same results, same isolation, no leaked processes."""

import subprocess
import sys
import threading

import pytest

import unlock_engine.worker as worker
from unlock_engine.contracts import EngineError
from unlock_engine.package import load_files
from unlock_engine.worker import cpu_limit_for, isolated_import, prewarmed_workers


@pytest.fixture
def package(fixture_dirs):
    p = fixture_dirs["B01"]
    return load_files(
        {n: (p / n).read_bytes() for n in ("assembly.step", "manifest.json")}
    )


@pytest.fixture
def spawned(monkeypatch):
    processes = []
    original = worker._spawn_standby

    def record():
        process = original()
        processes.append(process)
        return process

    monkeypatch.setattr(worker, "_spawn_standby", record)
    return processes


def stable(inventory):
    return {k: inventory[k] for k in ("input_hash", "geometry_hash", "components")}


def test_standby_results_match_cold_start_in_fresh_single_use_processes(
    package, spawned
):
    cold = isolated_import(package)
    handovers = worker.STANDBY_STATS["handovers"]
    with prewarmed_workers():
        warm = [isolated_import(package) for _ in range(2)]
    assert [stable(w) for w in warm] == [stable(cold)] * 2
    assert worker.STANDBY_STATS["handovers"] - handovers == 2
    # Pool entry plus one replacement per operation: every operation had its own
    # process, and every process has exited (the idle one at pool exit).
    assert len(spawned) == 3 and len({p.pid for p in spawned}) == 3
    assert all(p.poll() is not None for p in spawned)
    assert worker._standby is None


def test_no_standby_outside_a_pool(package, spawned):
    cold_starts = worker.STANDBY_STATS["cold_starts"]
    isolated_import(package)
    assert spawned == [] and worker.STANDBY_STATS["cold_starts"] == cold_starts + 1


def test_dead_standby_falls_back_to_a_cold_start(package, spawned):
    with prewarmed_workers():
        spawned[0].kill()
        spawned[0].wait()
        cold_starts = worker.STANDBY_STATS["cold_starts"]
        inventory = isolated_import(package)
        assert worker.STANDBY_STATS["cold_starts"] == cold_starts + 1
    assert stable(inventory)["components"]


def test_cancellation_and_timeout_still_stop_a_handed_over_worker(package, spawned):
    cancel = threading.Event()
    cancel.set()
    with prewarmed_workers():
        with pytest.raises(EngineError, match="cancelled"):
            isolated_import(package, cancel_event=cancel)
        with pytest.raises(EngineError, match="timed out"):
            isolated_import(package, timeout_seconds=0.001)
        used = spawned[:2]
    assert all(p.poll() is not None for p in used)


def test_nested_pools_share_one_standby_until_the_outer_exit(spawned):
    with prewarmed_workers():
        with prewarmed_workers():
            pass
        assert len(spawned) == 1 and spawned[0].poll() is None
    assert spawned[0].poll() is not None and worker._standby is None


def test_standby_environment_excludes_credentials(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "never-in-a-worker")
    monkeypatch.setenv("SOME_TOKEN", "never-in-a-worker")
    seen = {}
    real_popen = subprocess.Popen

    def capture(command, **kwargs):
        seen.update(command=command, env=kwargs["env"])
        return real_popen([sys.executable, "-c", "pass"], stdin=subprocess.PIPE)

    monkeypatch.setattr(worker.subprocess, "Popen", capture)
    worker._stop(worker._spawn_standby())
    assert seen["command"][-1] == "--standby"
    assert "MODEL_API_KEY" not in seen["env"] and "SOME_TOKEN" not in seen["env"]
    assert seen["env"]["OMP_NUM_THREADS"] == "1"


@pytest.mark.parametrize(
    "operation, limit",
    [
        ("import", 60),
        ("ai_construct", 60),
        ("demo_prepare", 60),
        ("plan", 180),
        ("ai_verify", 180),
        ("http_export", 180),
    ],
)
def test_handed_over_operations_keep_their_own_cpu_limit(operation, limit):
    # The cold and standby paths both install cpu_limit_for(operation).
    assert cpu_limit_for(operation) == limit
