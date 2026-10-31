"""Deployment boundaries exercised against genuine B02 engineering results."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from unlock_engine.contracts import EngineError
from unlock_engine.deployment import jobs
from unlock_engine.deployment.publication import validate_public_b02
from unlock_engine.deployment.snapshot import (
    RequestLimiter,
    SnapshotStore,
    create_snapshot_app,
)


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    root = tmp_path_factory.mktemp("modal-job")
    id = uuid.uuid4().hex
    result = jobs.run_job(root, id)
    assert result["state"] == "completed"
    assert result["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
    # Temporary SQLite and coordinator processes have already been closed/removed.
    assert not list(root.rglob("*.sqlite3*"))
    return root / id, result


def test_restart_snapshot_retains_real_verified_cad_and_export(completed):
    root, result = completed
    store = SnapshotStore(root)
    run = store.get("run", result["run_id"])
    assert run["baseline"]["status"] == "no_path_supported"
    assert run["model"]["live"] is False
    assert run["export"]["roundtrip_status"] == "passed"
    data = store.artifacts.get(run["export"]["artifact_id"])
    assert jobs.validate_export(data) == result["export_sha256"]
    candidate = store.get("candidate", run["selected_candidate_id"])
    assert candidate["verification"]["status"] == "passed"
    assert candidate["revised_plan"]["replacement_verified"]
    assert candidate["revised_plan"]["steps"][0]["end_mm"] == [0.0, 0.0, 80.0]
    assert validate_public_b02(root)["export_sha256"] == result["export_sha256"]


def test_publication_refuses_pending_license_snapshot(completed, tmp_path):
    import shutil

    root, _ = completed
    shutil.copytree(root, tmp_path / "copy")
    path = tmp_path / "copy" / "snapshot.json"
    data = json.loads(path.read_bytes())
    revision = next(r["data"] for r in data["records"] if r["kind"] == "revision")
    revision["manifest"]["provenance"]["license"] = "pending author approval"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="CC BY 4.0 grant"):
        validate_public_b02(tmp_path / "copy")


def test_public_reads_reuse_routes_and_refuse_every_write(completed):
    root, result = completed
    with TestClient(create_snapshot_app(root), client=("198.51.100.8", 123)) as client:
        health = client.get("/health").json()
        assert health["mode"] == "read_only"
        assert health["provider"]["demo_run_id"] == result["run_id"]
        assert len(client.get("/v1/projects").json()) == 1
        assert client.get("/v1/runs/" + result["run_id"]).status_code == 200
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert (
                client.request(method, "/v1/projects", content=b"untrusted").status_code
                == 403
            )
        assert client.get("/v1/artifacts/" + "0" * 64).status_code == 404
        assert client.get("/v1/projects/private-user-project").status_code == 404
        assert (
            client.get(
                "/health", headers={"Origin": "https://evil.invalid"}
            ).status_code
            == 403
        )
        assert (
            client.get("/health", headers={"Host": "evil.invalid"}).status_code == 400
        )
    # New API instance, no recomputation, no database migration or WAL writer.
    with TestClient(create_snapshot_app(root)) as restarted:
        assert (
            restarted.get("/v1/runs/" + result["run_id"]).json()["export"][
                "artifact_id"
            ]
            == result["export_sha256"]
        )


def test_request_rate_caps_have_bounded_memory_and_recover():
    clock = [0.0]
    limiter = RequestLimiter(2, 3, lambda: clock[0])
    assert limiter.allow() and limiter.allow() and not limiter.allow()
    clock[0] = 61
    assert limiter.allow() and not limiter.allow()
    clock[0] = 3662
    assert limiter.allow() and len(limiter.requests) == 1


def test_rate_limit_errors_remain_readable_by_allowed_frontend(completed):
    root, _ = completed
    app = create_snapshot_app(root)
    with TestClient(app) as client:
        app.state.coordinator.limiter = RequestLimiter(1, 1)
        headers = {"Origin": "http://localhost:5183"}
        assert client.get("/health", headers=headers).status_code == 200
        limited = client.get("/health", headers=headers)
        assert limited.status_code == 429
        assert limited.headers["access-control-allow-origin"] == headers["Origin"]
        assert limited.headers["retry-after"] == "60"


def test_concurrent_jobs_are_refused_before_work(tmp_path):
    with jobs._running:
        with pytest.raises(EngineError, match="one engineering job"):
            jobs.run_job(tmp_path, uuid.uuid4().hex)
    assert not list(tmp_path.iterdir())


def test_failed_job_preserves_terminal_state_and_no_false_pass(tmp_path):
    id = uuid.uuid4().hex
    with pytest.raises(EngineError):
        jobs.run_job(tmp_path, id, files={"model.stl": b"unsupported"})
    status = jobs.read_status(tmp_path, id)
    assert status["state"] == "failed" and "export_sha256" not in status


def test_interrupted_worker_and_path_traversal_are_explicit(tmp_path):
    id = uuid.uuid4().hex
    (tmp_path / id).mkdir()
    (tmp_path / id / "status.json").write_text(
        json.dumps(dict(state="running", updated_at=1))
    )
    assert jobs.read_status(tmp_path, id, clock=lambda: 500)["state"] == "interrupted"
    with pytest.raises(ValueError):
        jobs.read_status(tmp_path, "../../another-user")


def test_storage_budget_refuses_new_compute(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "storage_size", lambda _: jobs.MAX_STORAGE_BYTES)
    with pytest.raises(EngineError, match="artifact budget"):
        jobs.run_job(tmp_path, uuid.uuid4().hex)
    assert not list(tmp_path.iterdir())
