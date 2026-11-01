"""Private CPU jobs. Importing this module creates no cloud resources or public URL."""

import os
from pathlib import Path
import uuid

import modal

HERE = Path(__file__).resolve().parent
app = modal.App("unlock-engineering")
volume = modal.Volume.from_name("unlock-engineering-artifacts", create_if_missing=False)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglu1-mesa", "libglib2.0-0", "libxrender1", "libxext6")
    .pip_install_from_requirements(str(HERE / "requirements.lock"))
    .env(
        {
            "PYTHONPATH": "/opt/unlock/src",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "UNLOCK_PREWARM_WORKERS": "0",
            "RUN_META_LIVE_TESTS": "0",
            "UNLOCK_ALLOW_LIVE_META": "1"
            if os.environ.get("UNLOCK_ALLOW_LIVE_META") == "1"
            else "0",
        }
    )
    .add_local_dir(
        HERE / "src",
        remote_path="/opt/unlock/src",
        ignore=["**/__pycache__/**", "**/*.pyc"],
    )
)
secret_name = os.environ.get("UNLOCK_META_SECRET")
secrets = (
    [modal.Secret.from_name(secret_name, required_keys=["MODEL_API_KEY"])]
    if secret_name
    else []
)


@app.function(
    image=image,
    cpu=(1, 1),
    memory=(2048, 4096),
    timeout=420,
    startup_timeout=180,
    max_containers=1,
    min_containers=0,
    buffer_containers=0,
    scaledown_window=2,
    retries=0,
    volumes={"/artifacts": volume},
    secrets=secrets,
)
def engineering_job(
    job_id: str,
    files: dict[str, bytes] | None = None,
    target_id="target",
    live=False,
    fixture="B02",
):
    from unlock_engine.deployment.jobs import run_job

    if live and os.environ.get("UNLOCK_ALLOW_LIVE_META") != "1":
        raise ValueError(
            "Live inference requires a separately approved deployment with UNLOCK_ALLOW_LIVE_META=1"
        )
    volume.reload()
    return run_job(
        Path("/artifacts"),
        job_id,
        files=files,
        fixture=fixture,
        target_id=target_id,
        live=live,
        commit=volume.commit,
    )


@app.function(
    image=image,
    cpu=(0.125, 0.25),
    memory=(256, 512),
    timeout=30,
    max_containers=1,
    min_containers=0,
    scaledown_window=2,
    volumes={"/artifacts": volume.with_mount_options(read_only=True)},
)
def job_status(job_id: str):
    from unlock_engine.deployment.status import read_status
    from unlock_engine.deployment.snapshot import SnapshotStore

    volume.reload()
    result = read_status(Path("/artifacts"), job_id)
    if result["state"] == "completed":
        store = SnapshotStore(Path("/artifacts") / job_id)
        run = store.get("run", result["run_id"])
        store.artifacts.get(run["export"]["artifact_id"])
        result["persisted_export_integrity"] = "passed"
    return result


@app.function(
    image=image,
    cpu=(0.25, 0.5),
    memory=(512, 1024),
    timeout=120,
    max_containers=1,
    min_containers=0,
    scaledown_window=2,
    retries=0,
    volumes={"/artifacts": volume},
)
def compose_gallery(gallery_id: str, job_ids: list[str]):
    """Merge completed fixture jobs and refuse to commit anything that would not publish."""
    from unlock_engine.deployment.publication import validate_public_gallery
    from unlock_engine.deployment.snapshot import compose_gallery as compose
    from unlock_engine.deployment.status import checked_job_id

    volume.reload()
    root = Path("/artifacts")
    destination = root / checked_job_id(gallery_id)
    destination.mkdir(exist_ok=False)
    compose([root / checked_job_id(id) for id in job_ids], destination)
    published = validate_public_gallery(destination)
    volume.commit()
    return published


@app.local_entrypoint()
def gallery():
    """Run every licensed fixture privately, one at a time, then compose the gallery."""
    from unlock_engine.fixture_catalog import EXPECTED

    job_ids = []
    for code in EXPECTED:
        job_id = uuid.uuid4().hex
        result = engineering_job.remote(job_id, fixture=code)
        print(code, job_id, result["outcome"], result["elapsed_seconds"], "s")
        job_ids.append(job_id)
    gallery_id = uuid.uuid4().hex
    published = compose_gallery.remote(gallery_id, job_ids)
    for code, row in published.items():
        print(code, row["outcome"], row["export_sha256"] or "no export")
    print(f"Gallery ID: {gallery_id}  (set UNLOCK_DEMO_JOB to this value)")


@app.local_entrypoint()
def smoke():
    """Private B02 smoke test. No ASGI function exists in this app."""
    job_id = uuid.uuid4().hex
    call = engineering_job.spawn(job_id)
    print(f"Job ID: {job_id}; FunctionCall ID: {call.object_id}")
    result = call.get(timeout=420)
    print(
        {
            k: result[k]
            for k in (
                "state",
                "outcome",
                "elapsed_seconds",
                "artifact_bytes",
                "export_sha256",
            )
        }
    )
