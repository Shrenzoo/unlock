"""Private bounded engineering jobs, callable locally or from an authenticated Function."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from ..ai.config import load_config
from ..api.contracts import DecisionInput, StartRun
from ..api.coordinator import Coordinator, TERMINAL
from ..artifacts import atomic_write
from ..contracts import EngineError, POLICY
from ..fixture_catalog import EXPECTED, GALLERY, NAMES
from .snapshot import MAX_JOB_BYTES, MAX_STORAGE_BYTES, save_snapshot, storage_size
from .status import checked_job_id, read_status as read_status

JOB_TIMEOUT_S = 300
_running = threading.Lock()


def validate_export(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        bundle = json.loads(archive.read("bundle.json"))
        if bundle["status"] != "full_assembly":
            raise EngineError(
                "VERIFICATION_UNKNOWN", "full assembly export was not verified"
            )
        # Existing export manifest is authoritative, including its exact file set.
        files = bundle["files"]
        if set(archive.namelist()) != set(files) | {"bundle.json"}:
            raise EngineError("GEOMETRY_FAILED", "export file inventory differs")
        for name, metadata in files.items():
            expected = metadata["sha256"] if isinstance(metadata, dict) else metadata
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise EngineError("GEOMETRY_FAILED", "export content hash mismatch")
    return hashlib.sha256(data).hexdigest()


def run_job(
    root,
    job_id,
    *,
    files=None,
    fixture="B02",
    target_id="target",
    live=False,
    commit=lambda: None,
):
    """One full bounded workflow. No public HTTP route invokes this function.

    `root` is durable artifact storage; SQLite always lives in a local tmpdir.
    Modal enforces max_containers=1 and serial input delivery as the outer lock.
    The local lock also rejects simultaneous in-process invocations in tests/tools.
    """
    checked_job_id(job_id)
    if files is None and fixture not in EXPECTED:
        raise EngineError("INVALID_PACKAGE", "fixture has no pre-registered outcome")
    if not _running.acquire(blocking=False):
        raise EngineError("LIMIT_EXCEEDED", "one engineering job may execute at a time")
    c = None
    temporary = None
    created = False
    destination = Path(root) / job_id
    started = time.monotonic()
    status = dict(
        job_id=job_id,
        state="running",
        fixture=fixture if files is None else None,
        live_model=live,
        run_id=None,
        updated_at=time.time(),
    )

    def publish():
        status["updated_at"] = time.time()
        atomic_write(destination / "status.json", json.dumps(status).encode())
        commit()

    def wait(ids):
        id = ids["job_id"]
        last = None
        while True:
            job = c.store.get("job", id)
            state = job["state"]
            events = c.store.events(id)
            cursor = (state, len(events))
            if cursor != last:
                logging.getLogger(__name__).info(
                    "engineering job %s phase=%s state=%s events=%s",
                    job_id,
                    job["kind"],
                    state,
                    len(events),
                )
                status.update(engineering_job_id=id, phase=job["kind"], events=events)
                save_snapshot(c, destination, run_id=status["run_id"])
                publish()
                last = cursor
            if state in TERMINAL:
                if state != "completed":
                    raise EngineError(
                        "GEOMETRY_FAILED",
                        "Engineering stage failed; inspect preserved job evidence",
                    )
                return
            if time.monotonic() - started > JOB_TIMEOUT_S:
                c.cancel(id)
                raise EngineError(
                    "LIMIT_EXCEEDED", "engineering job exceeded its wall-time budget"
                )
            time.sleep(0.2)

    try:
        if files is not None and (
            not files
            or sum(len(v) for v in files.values()) > POLICY.max_compressed_bytes
        ):
            raise EngineError("LIMIT_EXCEEDED", "package exceeds 25 MiB")
        # Reserve a complete job's maximum before starting. One cloud writer only.
        if storage_size(root) + MAX_JOB_BYTES > MAX_STORAGE_BYTES:
            raise EngineError(
                "LIMIT_EXCEEDED",
                "workspace artifact budget is full; operator cleanup required",
            )
        destination.mkdir(parents=True, exist_ok=False)
        created = True
        publish()
        temporary = tempfile.TemporaryDirectory(prefix="unlock-job-")
        local = temporary.name
        # No implicit environment-file key loading for an offline job.
        config = load_config() if live else load_config({"AI_PROVIDER": "mock"})
        if live and (config.provider != "meta" or not config.api_key):
            raise EngineError(
                "FORBIDDEN",
                "live job requires the Meta configuration and a server-side secret",
            )
        c = Coordinator(Path(local), config=config)
        if files is None:
            meta = GALLERY.get(fixture, dict(name=NAMES.get(fixture), description=None))
            project_id = "fixture_" + fixture
            c.project(project_id, meta["name"], fixture, meta["description"])

            def generate(job, cancel):
                data, blobs = c._native("http_fixture", dict(code=fixture), cancel)
                c.commit_import(data, blobs, True)

            wait(c.submit("fixture", None, generate, parent=project_id))
        else:
            wait(c.import_files("default", job_id, files))
        revision = c.store.list("revision")[-1]
        ids = c.start_run(
            revision["id"],
            StartRun(
                target_id=target_id,
                policy_id="planner_v1",
                constraint_hash=revision["constraint_hash"],
            ),
            "baseline",
        )
        status["run_id"] = ids["run_id"]
        wait(ids)
        wait(c.redesign(status["run_id"], "redesign"))
        run = c.store.get("run", status["run_id"])
        expected = EXPECTED.get(fixture) if files is None else None
        if run["outcome"] != (expected or "VERIFIED_IMPROVEMENT_FOUND"):
            raise EngineError(
                "VERIFICATION_UNKNOWN",
                f"Outcome {run['outcome']} differs from the pre-registered {expected}"
                if expected
                else "No independently verified improvement was found",
            )
        if run["outcome"] != "VERIFIED_IMPROVEMENT_FOUND":
            # A recorded refusal or no-op is the result; nothing is accepted or exported.
            c.executor.shutdown(wait=True)
            save_snapshot(c, destination, run_id=run["id"])
            status.update(
                state="completed",
                outcome=run["outcome"],
                export_sha256=None,
                elapsed_seconds=round(time.monotonic() - started, 3),
                artifact_bytes=storage_size(destination),
            )
            publish()
            return status
        candidate = c.store.get("candidate", run["selected_candidate_id"])
        c.decide(
            candidate["id"],
            DecisionInput(decision="accept", input_hash=candidate["input_hash"]),
        )
        wait(c.export(candidate["id"], "export"))
        run = c.store.get("run", status["run_id"])
        if run["export"]["roundtrip_status"] != "passed":
            raise EngineError("VERIFICATION_UNKNOWN", "STEP round trip did not pass")
        export_hash = validate_export(
            c.store.artifacts.get(run["export"]["artifact_id"])
        )
        c.executor.shutdown(wait=True)
        save_snapshot(c, destination, run_id=run["id"])
        status.update(
            state="completed",
            outcome=run["outcome"],
            export_sha256=export_hash,
            elapsed_seconds=round(time.monotonic() - started, 3),
            artifact_bytes=storage_size(destination),
        )
        publish()
        return status
    except Exception as exc:
        if created:
            if c is not None:
                for id, event in c.cancels.items():
                    if not event.is_set():
                        c.cancel(id)
                c.executor.shutdown(wait=True)
                save_snapshot(c, destination, run_id=status["run_id"])
            status.update(
                state="failed",
                error=exc.code if isinstance(exc, EngineError) else "JOB_FAILED",
            )
            publish()
        raise
    finally:
        try:
            if c is not None:
                c.close()
        finally:
            if temporary is not None:
                temporary.cleanup()
            _running.release()
