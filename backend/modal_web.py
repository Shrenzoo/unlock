"""Public read-only API. Run `modal deploy modal_web.py` only after approval."""

import os
import re

import modal
from modal_app import image, volume

app = modal.App("unlock-demo")
job_id = os.environ.get("UNLOCK_DEMO_JOB", "")
origins = os.environ.get("UNLOCK_CORS_ORIGINS", "")
if not re.fullmatch(r"[a-f0-9]{32}", job_id):
    raise ValueError("UNLOCK_DEMO_JOB must select a completed verified B02 job")
if not origins or any(
    not value.startswith("https://") or "*" in value for value in origins.split(",")
):
    raise ValueError("Set exact HTTPS frontend origins before public deployment")


@app.function(
    image=image.add_local_python_source("modal_app"),
    env={"UNLOCK_CORS_ORIGINS": origins, "UNLOCK_DEMO_JOB": job_id},
    cpu=(0.125, 0.5),
    memory=(256, 512),
    timeout=30,
    max_containers=1,
    min_containers=0,
    buffer_containers=0,
    scaledown_window=2,
    volumes={"/demo": volume.with_mount_options(read_only=True, sub_path="/" + job_id)},
)
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def web():
    from unlock_engine.deployment.publication import validate_public_b02
    from unlock_engine.deployment.snapshot import create_snapshot_app

    validate_public_b02("/demo")
    return create_snapshot_app("/demo", allowed_hosts=["*.modal.run"])
