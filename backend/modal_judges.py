"""Judge-only bounded uploads, independent of the public read-only B02 API."""

import os
import modal
from modal_app import image, volume

app = modal.App("unlock-judges")
origins = os.environ.get("UNLOCK_CORS_ORIGINS", "").split(",")
if not origins or any(not x.startswith("https://") or "*" in x for x in origins):
    raise ValueError("Exact HTTPS judge frontend origins required")


@app.function(
    image=image.add_local_python_source("modal_app"),
    secrets=[
        modal.Secret.from_name(
            "unlock-judge-access", required_keys=["UNLOCK_JUDGE_CODE_HASH"]
        )
    ],
    env={"UNLOCK_CORS_ORIGINS": ",".join(origins)},
    volumes={"/artifacts": volume},
    cpu=(0.125, 0.5),
    memory=(256, 512),
    timeout=30,
    max_containers=1,
    min_containers=0,
    buffer_containers=0,
    scaledown_window=2,
)
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def web():
    from unlock_engine.deployment.judges import create_judge_app

    # Look up the separately deployed private worker: never inline a new worker
    # with different limits, credentials or live-model settings in this app.
    worker = modal.Function.from_name("unlock-engineering", "engineering_job")
    return create_judge_app(
        "/artifacts",
        code_hash=os.environ["UNLOCK_JUDGE_CODE_HASH"],
        origins=origins,
        refresh=volume.reload,
        commit=volume.commit,
        submit=lambda id, files, target: worker.spawn(
            id, files=files, target_id=target, live=False
        ),
    )
