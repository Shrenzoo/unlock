"""Judge isolation, durable controls and genuine uploaded CAD workflow."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from unlock_engine.deployment.judges import create_judge_app, MAX_UPLOAD
from unlock_engine.deployment.jobs import run_job

CODE = "test-only-code-never-deployed"
ORIGIN = "https://judges.example"


def gateway(root, submit=lambda *args: None, clock=lambda: 1000):
    return create_judge_app(
        root,
        code_hash=hashlib.sha256(CODE.encode()).hexdigest(),
        origins=[ORIGIN],
        submit=submit,
        clock=clock,
    )


def login(client):
    r = client.post("/sessions", json={"code": CODE})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def upload(client, headers, key="a" * 32, content=b"bad ZIP"):
    return client.post(
        "/jobs",
        files={"package": ("assembly.zip", content)},
        headers={**headers, "Idempotency-Key": key},
    )


def test_auth_origin_chunked_body_and_revocation(tmp_path):
    with TestClient(gateway(tmp_path)) as c:
        assert c.post("/sessions", json={"code": "wrong"}).status_code == 401
        assert c.get("/session").status_code == 401
        assert (
            c.post(
                "/sessions",
                json={"code": CODE},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        h = login(c)
        assert c.get("/session", headers=h).json()["remaining"] == 2
        assert (
            c.post(
                "/jobs",
                content=iter([b"x" * 1024] * (MAX_UPLOAD // 1024 + 65)),
                headers=h,
            ).status_code
            == 413
        )
        assert c.get("/session", headers=h).json()["remaining"] == 2
        assert c.delete("/session", headers=h).status_code == 200
        assert c.get("/session", headers=h).status_code == 401


def test_idempotency_concurrent_admission_restart_and_isolation(tmp_path):
    submitted = []
    app = gateway(tmp_path, lambda *x: submitted.append(x))
    with TestClient(app) as c:
        h = login(c)
        other = login(c)
        with ThreadPoolExecutor(2) as pool:
            rs = list(pool.map(lambda _: upload(c, h), range(2)))
        assert [r.status_code for r in rs] == [202, 202]
        job = rs[0].json()["job_id"]
        assert rs[1].json()["job_id"] == job and len(submitted) == 1
        assert upload(c, h, content=b"different").status_code == 409
        assert upload(c, other, key="b" * 32).status_code == 409
        assert c.get("/jobs/" + job, headers=other).status_code == 404
        assert c.get("/jobs/" + job + "/view/health", headers=other).status_code == 404
    with TestClient(gateway(tmp_path)) as c:
        assert c.get("/session", headers=h).json()["remaining"] == 1
        assert upload(c, h).json()["job_id"] == job
        assert upload(c, h, key="c" * 32).status_code == 409


def test_failed_dispatch_and_total_quota_are_not_refunded(tmp_path):
    def failed(*args):
        raise RuntimeError("test transport interruption")

    with TestClient(gateway(tmp_path, failed)) as c:
        for _ in range(3):
            h = login(c)
            assert upload(c, h).status_code == 503
            assert upload(c, h, key="b" * 32).status_code == 503
            assert upload(c, h, key="c" * 32).status_code == 429
        h = login(c)
        assert upload(c, h).status_code == 429
    with TestClient(gateway(tmp_path)) as c:
        h = login(c)
        assert c.get("/session", headers=h).json()["remaining"] == 0


def test_expiry_and_attempts_survive_restart(tmp_path):
    clock = [1000]
    with TestClient(gateway(tmp_path, clock=lambda: clock[0])) as c:
        h = login(c)
    clock[0] += 7201
    with TestClient(gateway(tmp_path, clock=lambda: clock[0])) as c:
        assert c.get("/session", headers=h).status_code == 401
        for _ in range(60):
            assert c.post("/sessions", json={"code": "wrong"}).status_code == 401
    with TestClient(gateway(tmp_path, clock=lambda: clock[0])) as c:
        assert c.post("/sessions", json={"code": CODE}).status_code == 429


@pytest.fixture(scope="module")
def uploaded(tmp_path_factory, fixture_dirs):
    root = tmp_path_factory.mktemp("judge-upload")
    files = {
        n: (fixture_dirs["B02"] / n).read_bytes()
        for n in ["assembly.step", "manifest.json"]
    }

    def compute(id, uploaded_files, target):
        run_job(root, id, files=uploaded_files, target_id=target)

    with TestClient(gateway(root, compute)) as c:
        h = login(c)
        r = c.post(
            "/jobs",
            files=[("package", (n, b)) for n, b in files.items()],
            data={"target_id": "target"},
            headers={**h, "Idempotency-Key": "d" * 32},
        )
        assert r.status_code == 202, r.text
        job = r.json()["job_id"]
        result = c.get("/jobs/" + job, headers=h).json()
        assert result["state"] == "completed", result
    return root, h, job, result


def test_real_cad_private_view_and_export(uploaded):
    root, h, job, result = uploaded
    with TestClient(gateway(root)) as c:
        base = "/jobs/" + job + "/view/"
        assert c.get(base + "health").status_code == 401
        stranger = login(c)
        assert c.get(base + "v1/projects", headers=stranger).status_code == 404
        health = c.get(base + "health", headers=h).json()
        assert health["provider"]["access"] == "read_only"
        run = c.get(base + "v1/runs/" + result["run_id"], headers=h).json()
        assert (
            run["model"]["live"] is False
            and run["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
            and run["export"]["roundtrip_status"] == "passed"
        )
        artifact = run["export"]["artifact_id"]
        data = c.get(base + "v1/artifacts/" + artifact, headers=h)
        assert (
            hashlib.sha256(data.content).hexdigest() == artifact
            and data.headers["cache-control"] == "no-store"
        )
        assert (
            c.get(base + "v1/artifacts/" + artifact, headers=stranger).status_code
            == 404
        )
        assert c.get(base + "v1/artifacts/" + "0" * 64, headers=h).status_code == 404
        assert c.post(base + "v1/projects", headers=h).status_code == 405
        assert c.get(base + "v1/projects/fixture_B01", headers=h).status_code == 404


def test_mounted_gateway_keeps_login_and_upload_boundaries(tmp_path):
    from fastapi import FastAPI

    app = FastAPI()
    app.mount("/judge", gateway(tmp_path))
    with TestClient(app) as c:
        r = c.post("/judge/sessions", json={"code": CODE})
        assert r.status_code == 200
        h = {"Authorization": "Bearer " + r.json()["token"]}
        assert (
            c.post(
                "/judge/jobs",
                files={"package": ("a.zip", b"x")},
                headers={**h, "Idempotency-Key": "z" * 32},
            ).status_code
            == 202
        )
        assert c.get("/judge/session").status_code == 401


def test_strict_package_names_and_stale_dispatch(tmp_path):
    clock = [1000]
    with TestClient(gateway(tmp_path, clock=lambda: clock[0])) as c:
        h = login(c)
        for name in ("../a.zip", "a.py", "a\\\\b.zip"):
            assert (
                c.post(
                    "/jobs",
                    files={"package": (name, b"x")},
                    headers={**h, "Idempotency-Key": "z" * 32},
                ).status_code
                == 422
            )
        job = upload(c, h).json()["job_id"]
        clock[0] += 601
        assert c.get("/jobs/" + job, headers=h).json()["state"] == "interrupted"
        assert upload(c, h, key="z" * 32).status_code == 202
