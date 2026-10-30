"""Small status reader usable without loading native CAD libraries."""

import json
import re
import time
from pathlib import Path


def checked_job_id(value):
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("job ID must be a generated UUID hex value")
    return value


def read_status(root, job_id, *, clock=time.time):
    data = json.loads(
        (Path(root) / checked_job_id(job_id) / "status.json").read_bytes()
    )
    if data["state"] == "running" and clock() - data["updated_at"] > 420:
        data.update(
            state="interrupted",
            error="Worker stopped before completion; saved evidence remains available.",
        )
    return data
