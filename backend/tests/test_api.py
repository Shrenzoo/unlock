"""Real HTTP contracts and engineering workflows. The provider alone is scripted offline."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from unlock_engine.ai.config import load_config
from unlock_engine.api.app import create_app


def wait_job(client, id, timeout=125):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        r = client.get("/v1/jobs/" + id)
        assert r.status_code == 200, r.text
        job = r.json()
        if job["state"] in ("completed", "failed", "cancelled", "interrupted"):
            return job
        time.sleep(0.05)
    pytest.fail("job did not terminate within its declared deadline")


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    app = create_app(
        root=tmp_path_factory.mktemp("api"),
        config=load_config({"AI_PROVIDER": "mock"}),
        seed=True,
    )
    with TestClient(app) as client:
        for job in app.state.coordinator.store.list("job"):
            assert wait_job(client, job["id"])["state"] == "completed"
        yield client


def start(client, project="fixture_B02", **overrides):
    project = client.get("/v1/projects/" + project).json()
    rev = client.get("/v1/revisions/" + project["revision"]).json()
    body = dict(
        target_id="target",
        policy_id="planner_v1",
        constraint_hash=rev["constraint_hash"],
        **overrides,
    )
    r = client.post(
        "/v1/revisions/" + rev["id"] + "/runs",
        json=body,
        headers={"Idempotency-Key": "baseline-" + str(time.monotonic_ns())},
    )
    return rev, r


def test_real_import_baseline_rejection_revised_verification_and_evidence(api):
    rev, r = start(api)
    assert r.status_code == 202, r.text
    ids = r.json()
    assert wait_job(api, ids["job_id"])["state"] == "completed"
    run = api.get("/v1/runs/" + ids["run_id"]).json()
    assert (
        run["baseline"]["status"] == "no_path_supported" and run["baseline"]["complete"]
    )
    assert any(
        r["evidence_level"] == "confirmed_witness"
        for r in run["baseline"]["rejections"]
    )
    assert all(
        r["obstacle_ids"] == ["bridge"]
        for r in run["baseline"]["rejections"]
        if r["evidence_level"] == "confirmed_witness"
    )
    preview = api.get("/v1/artifacts/" + rev["preview_artifact_id"]).json()
    assert {c["occurrence_id"] for c in preview["components"]} == {
        c["id"] for c in rev["manifest"]["components"]
    }
    r = api.post(
        "/v1/runs/" + ids["run_id"] + "/redesign",
        headers={"Idempotency-Key": "redesign-success"},
    )
    assert r.status_code == 202, r.text
    job = wait_job(api, r.json()["job_id"])
    assert job["state"] == "completed", job
    run = api.get("/v1/runs/" + ids["run_id"]).json()
    assert run["outcome"] == "VERIFIED_IMPROVEMENT_FOUND", run
    assert len(run["candidates"]) == 2 and run["candidates"][0]["state"] == "failed"
    candidate = next(
        c for c in run["candidates"] if c["id"] == run["selected_candidate_id"]
    )
    assert (
        candidate["state"] == "checked"
        and candidate["verification"]["status"] == "passed"
    )
    assert candidate["revised_plan"]["replacement_verified"]
    assert all(
        c["result"] == "pass"
        for c in candidate["verification"]["checks"]
        if c.get("mandatory", True)
    )
    assert run["model"]["provider"] == "fake" and "offline" in run["provenance"]["note"]
    # The view states plainly that the scripted policy is not live inference.
    assert run["model"]["live"] is False and run["model"]["turns"] > 0
    assert run["metrics"][1]["original"] is None and run["metrics"][1]["revised"] == "0"
    assert candidate["revised_plan"]["steps"][0]["end_mm"] == [0.0, 0.0, 80.0]
    assert (
        api.get("/v1/artifacts/" + candidate["preview_artifact_id"]).status_code == 200
    )
    report = api.get("/v1/artifacts/" + run["ai_report_artifact_id"]).json()
    assert report["engineering_evidence"]["verified"]
    assert run["evidence_refs"] and candidate["metrics"] == run["metrics"]
    assert any(
        e["state"] == "failed" and e.get("tool", {}).get("name") == "verify_candidate"
        for e in run["events"]
    )
    assert (
        api.post(
            "/v1/candidates/" + candidate["id"] + "/decision",
            json={"decision": "accept", "input_hash": "0" * 64},
        ).status_code
        == 409
    )
    assert (
        api.post(
            "/v1/candidates/" + run["candidates"][0]["id"] + "/decision",
            json={
                "decision": "accept",
                "input_hash": run["candidates"][0]["input_hash"],
            },
        ).status_code
        == 409
    )
    assert (
        api.post(
            "/v1/candidates/" + candidate["id"] + "/decision",
            json={"decision": "accept", "input_hash": candidate["input_hash"]},
        ).status_code
        == 200
    )
    r = api.post(
        "/v1/candidates/" + candidate["id"] + "/exports",
        headers={"Idempotency-Key": "export-checked"},
    )
    assert r.status_code == 202, r.text
    exported = wait_job(api, r.json()["job_id"])
    assert exported["state"] == "completed", exported
    run = api.get("/v1/runs/" + ids["run_id"]).json()
    assert run["export"]["roundtrip_status"] == "passed"
    import io
    import zipfile
    import hashlib

    data = api.get("/v1/artifacts/" + run["export"]["artifact_id"]).content
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        bundle = json.loads(z.read("bundle.json"))
        assert bundle["status"] == "full_assembly"
        for name, hash in bundle["files"].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == hash
        assert json.loads(z.read("paths.json"))["replacement_verified"]


def test_stale_constraints_unknown_and_fixed_targets_fail_before_jobs(api):
    rev, _ = start(api)
    path = "/v1/revisions/" + rev["id"] + "/runs"
    for target, hash, status in [
        ("absent", rev["constraint_hash"], 404),
        ("base", rev["constraint_hash"], 422),
        ("target", "0" * 64, 409),
    ]:
        r = api.post(
            path,
            json=dict(target_id=target, policy_id="planner_v1", constraint_hash=hash),
            headers={"Idempotency-Key": target + hash},
        )
        assert r.status_code == status, r.text
    assert (
        api.post(
            path,
            json=dict(
                target_id="target",
                policy_id="arbitrary",
                constraint_hash=rev["constraint_hash"],
            ),
            headers={"Idempotency-Key": "x"},
        ).status_code
        == 422
    )


def test_idempotency_event_resume_and_cancel(api):
    rev, r = start(api, project="fixture_B01")
    ids = r.json()
    wait_job(api, ids["job_id"])
    events = api.app.state.coordinator.store.events(ids["job_id"])
    assert events[-1]["terminal"] and [e["sequence"] for e in events] == list(
        range(1, len(events) + 1)
    )
    stream = api.get(
        "/v1/jobs/" + ids["job_id"] + "/events",
        headers={"Last-Event-ID": str(events[-2]["sequence"])},
    )
    assert stream.status_code == 200 and stream.text.count("data:") == 1
    run = api.get("/v1/runs/" + ids["run_id"]).json()
    assert run["baseline"]["status"] == "feasible"
    assert run["baseline"]["steps"][0]["end_mm"] == [0.0, 0.0, 80.0]
    payload = dict(
        target_id="target",
        policy_id="planner_v1",
        constraint_hash=rev["constraint_hash"],
    )
    path = "/v1/revisions/" + rev["id"] + "/runs"
    first = api.post(path, json=payload, headers={"Idempotency-Key": "same-input"})
    repeat = api.post(path, json=payload, headers={"Idempotency-Key": "same-input"})
    assert first.json() == repeat.json()
    job = first.json()["job_id"]
    assert (
        api.post(
            "/v1/jobs/" + job + "/cancel", headers={"Idempotency-Key": "cancel"}
        ).status_code
        == 202
    )
    assert wait_job(api, job)["state"] == "cancelled"


def test_credentials_do_not_leak_and_local_boundary(api):
    assert "api_key" not in json.dumps(api.get("/health").json()).lower()
    assert (
        api.get("/v1/projects", headers={"Origin": "https://evil.invalid"}).status_code
        == 403
    )
    assert api.get("/v1/projects", headers={"Host": "evil.invalid"}).status_code == 400
    assert api.get("/v1/artifacts/not-a-hash").status_code == 404
    r = api.post(
        "/v1/projects/default/imports",
        files={"package": ("bad.stl", b"mesh")},
        headers={"Idempotency-Key": "bad-upload"},
    )
    assert r.status_code == 422


def test_cancelled_or_active_run_cannot_accept_or_export_old_success(api):
    coordinator = api.app.state.coordinator
    success = next(
        r for r in coordinator.store.list("run") if r.get("selected_candidate_id")
    )
    candidate = next(
        c for c in success["candidates"] if c["id"] == success["selected_candidate_id"]
    )
    for state in ("cancelled", "failed", "queued"):
        altered = dict(success, state=state)
        coordinator.store.put("run", success["id"], altered, success["revision_id"])
        assert (
            api.post(
                "/v1/candidates/" + candidate["id"] + "/decision",
                json={"decision": "accept", "input_hash": candidate["input_hash"]},
            ).status_code
            == 409
        )
        assert (
            api.post(
                "/v1/candidates/" + candidate["id"] + "/exports",
                headers={"Idempotency-Key": "invalid-" + state},
            ).status_code
            == 409
        )
    coordinator.store.put("run", success["id"], success, success["revision_id"])


def test_missing_meta_key_retains_baseline_and_reports_unavailable(api):
    coordinator = api.app.state.coordinator
    previous = coordinator.config
    coordinator.config = load_config({})
    try:
        _, r = start(api)
        ids = r.json()
        assert wait_job(api, ids["job_id"])["state"] == "completed"
        r = api.post(
            "/v1/runs/" + ids["run_id"] + "/redesign",
            headers={"Idempotency-Key": "missing-key"},
        )
        assert wait_job(api, r.json()["job_id"])["state"] == "completed"
        run = api.get("/v1/runs/" + ids["run_id"]).json()
        assert run["outcome"] == "MODEL_UNAVAILABLE"
        assert (
            run["baseline"]["status"] == "no_path_supported"
            and not run["selected_candidate_id"]
        )
        assert run["model"] is None and not run["candidates"]
        assert any(e["state"] == "failed" for e in run["events"])
    finally:
        coordinator.config = previous


def test_interrupted_jobs_recover_without_completed_artifacts(tmp_path):
    from unlock_engine.api.store import Store

    store = Store(tmp_path)
    store.put("project", "project", {"id": "project"})
    store.put("job", "job", dict(id="job", state="running", run_id=None), "project")
    store.db.close()
    reopened = Store(tmp_path)
    assert reopened.get("job", "job")["state"] == "interrupted"
    assert reopened.events("job")[-1]["terminal"]
    reopened.db.close()
