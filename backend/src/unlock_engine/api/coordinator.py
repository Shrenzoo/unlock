"""One serial engineering queue. HTTP handlers only validate and coordinate bytes/IDs."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from ..ai.config import load_config
from ..ai.controller import run_with_model
from ..ai.provider import build_provider
from ..ai.session import Deadline, EngineeringSession
from ..ai.schemas import Handle
from pydantic import TypeAdapter
from ..contracts import EngineError, Manifest, digest
from ..package import load_files, load_zip
from ..worker import _run_worker
from .store import Store
from .views import apply_ai, plan_view, provenance, revision_view

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return prefix + "_" + uuid.uuid4().hex[:24]


class Coordinator:
    def __init__(self, root: Path, *, config=None):
        self.store = Store(root)
        self.config = config or load_config()
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="unlock-engineering"
        )
        self.lock = threading.RLock()
        self.cancels = {}
        self.sessions = {}
        self.closed = False

    def close(self):
        self.closed = True
        for event in self.cancels.values():
            event.set()
        self.executor.shutdown(wait=True, cancel_futures=False)
        self.store.db.close()

    def event(self, job, stage, state, message, **extra):
        return self.store.event(
            job["id"],
            dict(
                t_ms=round((time.monotonic() - job["_start"]) * 1000),
                stage=stage,
                state=state,
                message=message,
                **extra,
            ),
        )

    def submit(self, kind, run_id, function, *, parent=None):
        if self.closed or sum(not e.is_set() for e in self.cancels.values()) >= 8:
            raise EngineError("LIMIT_EXCEEDED", "engineering queue is full")
        id = uid("job")
        job = dict(
            id=id,
            kind=kind,
            run_id=run_id,
            state="queued",
            error=None,
            created_at=now(),
            _start=time.monotonic(),
        )
        cancel = threading.Event()
        self.cancels[id] = cancel
        self.store.put("job", id, job, run_id or parent)
        self.event(
            job, "inspect", "started", "Queued for the serial engineering worker"
        )

        def run():
            try:
                if cancel.is_set():
                    raise EngineError("CANCELLED", "job cancelled before execution")
                job["state"] = "running"
                self.store.put("job", id, job, run_id or parent)
                function(job, cancel)
                with self.lock:
                    if cancel.is_set():
                        raise EngineError(
                            "CANCELLED", "job cancelled before completion"
                        )
                    job["state"] = "completed"
                    self.store.put("job", id, job, run_id or parent)
            except EngineError as e:
                job["state"] = "cancelled" if e.code == "CANCELLED" else "failed"
                job["error"] = e.envelope()
                if run_id:
                    record = self.store.get("run", run_id)
                    record["state"] = job["state"]
                    if kind == "redesign":
                        record.update(
                            selected_candidate_id=None,
                            export=None,
                            outcome="CANCELLED"
                            if e.code == "CANCELLED"
                            else "INCOMPLETE_ANALYSIS",
                            explanation=str(e),
                        )
                    if kind == "export":
                        record["export"] = None
                        record["state"] = "completed"
                    self.store.put("run", run_id, record, record["revision_id"])
            except Exception:
                # Do not reflect SDK exception text or imported metadata into logs.
                job["state"] = "failed"
                job["error"] = EngineError(
                    "GEOMETRY_FAILED",
                    "engineering job interrupted; baseline and original input are preserved",
                ).envelope()
                if run_id:
                    record = self.store.get("run", run_id)
                    record["state"] = "failed"
                    if kind == "redesign":
                        record.update(
                            selected_candidate_id=None,
                            export=None,
                            outcome="INCOMPLETE_ANALYSIS",
                        )
                    if kind == "export":
                        record["export"] = None
                        record["state"] = "completed"
                    self.store.put("run", run_id, record, record["revision_id"])
            finally:
                self.store.put("job", id, job, run_id or parent)
                self.event(
                    job,
                    "compare",
                    "completed" if job["state"] == "completed" else "failed",
                    "Job " + job["state"],
                    terminal=True,
                    job_state=job["state"],
                    error=job["error"],
                )
                cancel.set()

        self.executor.submit(run)
        return dict(job_id=id, **({"run_id": run_id} if run_id else {}))

    def mutation(self, scope, key, payload, create):
        with self.lock:
            ih = digest(payload)
            response = self.store.idem(scope, key, ih)
            if response:
                return response
            response = create()
            return self.store.idem(scope, key, ih, response)

    def _native(self, operation, request, cancel, *, package=None, timeout=60):
        with tempfile.TemporaryDirectory(prefix="unlock-http-") as tmp:
            work = Path(tmp)
            if package:
                (work / "assembly.step").write_bytes(package.step)
                (work / "manifest.json").write_text(
                    json.dumps(package.manifest, allow_nan=False)
                )
            (work / "request.json").write_text(json.dumps(request, allow_nan=False))
            data = _run_worker(work, operation, timeout, cancel)
            if cancel.is_set():
                raise EngineError(
                    "CANCELLED", "native result cancelled before artifact commit"
                )
            blobs = {
                name: self.store.artifacts.put((work / name).read_bytes())
                for name in (
                    "assembly.step",
                    "manifest.json",
                    "preview.json",
                    "checked_export.zip",
                )
                if (work / name).is_file()
            }
            return data, blobs

    def project(self, id, name, code="LOCAL"):
        try:
            return self.store.get("project", id)
        except EngineError as e:
            if e.code != "NOT_FOUND":
                raise
        value = dict(
            id=id,
            fixture_code=code,
            name=name,
            description="Synthetic engineering fixture"
            if code != "LOCAL"
            else "Locally supplied engineering assembly",
            occurrences=None,
            revision=None,
            status="not_authored",
            provenance="illustrative",
            updated_at=None,
        )
        self.store.put("project", id, value)
        return value

    def commit_import(self, data, blobs, synthetic):
        inv = data["inventory"]
        manifest = inv["manifest"]
        if manifest is None:
            raise EngineError("INVALID_MANIFEST", "assembly metadata did not validate")
        project_id = manifest["project_id"]
        project = self.project(project_id, manifest["assembly_id"])
        record = dict(
            id=inv["input_hash"],
            project_id=project_id,
            manifest=manifest,
            inventory=inv,
            constraint_hash=digest(Manifest.model_validate(manifest)),
            step=blobs["assembly.step"],
            manifest_artifact=blobs["manifest.json"],
            preview=blobs["preview.json"],
            created_at=now(),
            synthetic=synthetic,
        )
        try:
            existing = self.store.get("revision", record["id"])
            record = existing
        except EngineError:
            self.store.put("revision", record["id"], record, project_id, immutable=True)
        project.update(
            occurrences=len(inv["components"]),
            revision=record["id"],
            status="ready",
            provenance="computed_earlier",
            updated_at=record["created_at"],
        )
        self.store.put("project", project_id, project)
        return record

    def seed(self):
        for code, name in [
            ("B01", "Accessible cartridge"),
            ("B02", "Trapped service component"),
            ("B03", "Tool-access conflict"),
        ]:
            project = self.project("fixture_" + code, name, code)
            if project["revision"]:
                continue

            def generate(job, cancel, code=code):
                self.event(
                    job,
                    "inspect",
                    "started",
                    "Generating and importing real synthetic " + code + " STEP",
                )
                data, blobs = self._native("http_fixture", dict(code=code), cancel)
                record = self.commit_import(data, blobs, True)
                self.event(
                    job,
                    "inspect",
                    "completed",
                    "Assembly imported",
                    revision_id=record["id"],
                    project_id=record["project_id"],
                )

            self.submit("fixture", None, generate, parent=project["id"])

    def import_files(self, project_id, key, files):
        package = (
            load_zip(next(iter(files.values())))
            if len(files) == 1 and next(iter(files)).lower().endswith(".zip")
            else load_files(files)
        )
        manifest = Manifest.model_validate(package.manifest)
        # HTTP routes and model tools share the same supported opaque-ID alphabet.
        id_type = TypeAdapter(Handle)
        id_type.validate_python(manifest.project_id)
        for component in manifest.components:
            id_type.validate_python(component.id)
        for constraint in manifest.constraints:
            id_type.validate_python(constraint.id)
        if project_id != "default" and manifest.project_id != project_id:
            raise EngineError(
                "FORBIDDEN", "manifest project does not match import destination"
            )
        self.project(manifest.project_id, manifest.assembly_id)
        payload = dict(
            project_id=manifest.project_id,
            step=self.store.artifacts.put(package.step),
            manifest=self.store.artifacts.put_json(package.manifest),
        )

        def create():
            def perform(job, cancel):
                self.event(
                    job,
                    "inspect",
                    "started",
                    "Importing supplied STEP and validated metadata",
                )
                data, blobs = self._native("http_import", {}, cancel, package=package)
                record = self.commit_import(data, blobs, False)
                self.event(
                    job,
                    "inspect",
                    "completed",
                    "Import complete",
                    revision_id=record["id"],
                    project_id=record["project_id"],
                )

            return self.submit("import", None, perform, parent=manifest.project_id)

        return self.mutation("import:" + project_id, key, payload, create)

    def package(self, revision):
        return load_files(
            {
                "assembly.step": self.store.artifacts.get(revision["step"]),
                "manifest.json": self.store.artifacts.get(
                    revision["manifest_artifact"]
                ),
            }
        )

    def start_run(self, revision_id, body, key):
        revision = self.store.get("revision", revision_id)
        if body.constraint_hash != revision["constraint_hash"]:
            raise EngineError(
                "STALE_REVISION", "constraint hash differs from frozen revision"
            )
        if not all(x["ok"] for x in revision["inventory"]["readiness"]):
            raise EngineError("UNSUPPORTED_SEMANTICS", "revision is not analysis ready")
        component = next(
            (
                c
                for c in revision["manifest"]["components"]
                if c["id"] == body.target_id
            ),
            None,
        )
        if component is None:
            raise EngineError("NOT_FOUND", "selected occurrence is absent")
        if component["fixed"] or not component["replaceable"]:
            raise EngineError(
                "UNSUPPORTED_SEMANTICS",
                "target must be an explicitly replaceable nonfixed occurrence",
            )

        def create():
            run_id = uid("run")
            record = dict(
                id=run_id,
                revision_id=revision_id,
                target_id=body.target_id,
                policy_version="policy_v1",
                provenance=provenance(revision_id, None, "Baseline analysis pending"),
                model=None,
                baseline=None,
                events=[],
                candidates=[],
                selected_candidate_id=None,
                metrics=[],
                state="queued",
                outcome=None,
                explanation=None,
                ai_report_artifact_id=None,
                export=None,
            )
            self.store.put("run", run_id, record, revision_id)

            def analyze(job, cancel):
                self.event(
                    job,
                    "baseline",
                    "started",
                    "Running real deterministic disassembly analysis",
                )
                pkg = self.package(revision)
                deadline = Deadline(120, cancel)
                try:
                    session = EngineeringSession.open(
                        pkg.step, pkg.manifest, body.target_id, deadline=deadline
                    )
                finally:
                    deadline.close()
                if cancel.is_set():
                    raise EngineError("CANCELLED", "baseline cancelled")
                self.sessions[run_id] = session
                while len(self.sessions) > 8:
                    self.sessions.pop(next(iter(self.sessions)))
                record.update(
                    baseline=plan_view(session.baseline.model_dump(mode="json")),
                    state="completed",
                    provenance=provenance(
                        revision_id,
                        now(),
                        "Real deterministic baseline; synthetic input"
                        if revision["synthetic"]
                        else "Real deterministic baseline",
                    ),
                )
                record["baseline_artifact"] = self.store.artifacts.put_json(
                    session.full_evidence()
                )
                # Internal references are separate from the typed frontend view.
                self.store.put("run", run_id, record, revision_id)
                self.event(
                    job, "baseline", "completed", "Baseline " + session.baseline.status
                )

            return self.submit("baseline", run_id, analyze)

        return self.mutation(
            "run:" + revision_id, key, body.model_dump(mode="json"), create
        )

    def redesign(self, run_id, key):
        record = self.store.get("run", run_id)
        if record["baseline"] is None or record["state"] != "completed":
            raise EngineError(
                "VERIFICATION_UNKNOWN", "baseline job must complete before redesign"
            )

        def create():
            for j in self.store.list("job"):
                if j["run_id"] == run_id and j["state"] not in TERMINAL:
                    raise EngineError(
                        "LIMIT_EXCEEDED", "a job is already active for this run"
                    )

            def improve(job, cancel):
                revision = self.store.get("revision", record["revision_id"])
                pkg = self.package(revision)

                def observer(event):
                    tool = event.get("tool")
                    stage = {
                        "construct_candidate": "construct",
                        "verify_candidate": "verify",
                        "compare_candidates": "compare",
                        "list_interventions": "interventions",
                        "inspect_blocker": "obstruction",
                        "analyze_removal": "baseline",
                    }.get(tool, "inspect")
                    self.event(
                        job,
                        stage,
                        "started"
                        if event.get("status") == "started"
                        else "failed"
                        if event.get("kind") == "provider_error"
                        or event.get("status")
                        in (
                            "failed",
                            "rejected",
                            "not_executed",
                            "CANCELLED",
                            "MODEL_UNAVAILABLE",
                            "INCOMPLETE_ANALYSIS",
                            "NO_VERIFIED_IMPROVEMENT",
                        )
                        else "completed",
                        event.get("stage_label", "Engineering stage")
                        + ((": " + event["detail"]) if event.get("detail") else ""),
                        **(
                            {
                                "tool": dict(
                                    name=tool,
                                    args=json.dumps(event.get("arguments") or {}),
                                )
                            }
                            if tool
                            else {}
                        ),
                    )

                report = run_with_model(
                    pkg.step,
                    pkg.manifest,
                    record["target_id"],
                    build_provider(self.config),
                    request_timeout_s=self.config.request_timeout_s,
                    max_retries=self.config.max_retries,
                    prices=self.config.prices,
                    cancel=cancel,
                    run_id=run_id,
                    session=self.sessions.get(run_id),
                    on_event=observer,
                    artifact_root=self.store.artifacts.root,
                )
                with self.lock:
                    if cancel.is_set():
                        raise EngineError(
                            "CANCELLED", "redesign cancelled before result commit"
                        )
                    updated = apply_ai(
                        self.store.get("run", run_id), report, self.store
                    )
                    updated.update(
                        state="cancelled"
                        if report["outcome"] == "CANCELLED"
                        else "completed",
                        export=None,
                    )
                    self.store.put("run", run_id, updated, updated["revision_id"])

            return self.submit("redesign", run_id, improve)

        return self.mutation("redesign:" + run_id, key, dict(run_id=run_id), create)

    def decide(self, candidate_id, body):
        with self.lock:
            candidate = self.store.get("candidate", candidate_id)
            if body.input_hash != candidate["input_hash"]:
                raise EngineError("STALE_REVISION", "review input hash is stale")
            if body.decision == "accept":
                self.require_current_candidate(candidate)
            if body.decision == "accept" and (
                candidate["state"] != "checked"
                or not candidate["verified_improvement"]
                or not candidate["revised_plan"]["replacement_verified"]
            ):
                raise EngineError(
                    "VERIFICATION_UNKNOWN",
                    "only independently verified improvements can be accepted",
                )
            id = uid("review")
            self.store.put(
                "review",
                id,
                dict(
                    id=id,
                    candidate_id=candidate_id,
                    decision=body.decision,
                    input_hash=body.input_hash,
                    at=now(),
                ),
                candidate_id,
                immutable=True,
            )
            run = self.store.get("run", candidate["run_id"])
            for c in run["candidates"]:
                if c["id"] == candidate_id:
                    c["review_decision"] = body.decision
            self.store.put("run", run["id"], run, run["revision_id"])
            return dict(review_event_id=id)

    def require_current_candidate(self, candidate, *, allow_job=None):
        run = self.store.get("run", candidate["run_id"])
        active = [
            j
            for j in self.store.list("job")
            if j["run_id"] == run["id"]
            and j["state"] not in TERMINAL
            and j["id"] != allow_job
        ]
        if (
            active
            or run["state"] != "completed"
            or run.get("outcome") != "VERIFIED_IMPROVEMENT_FOUND"
            or run["selected_candidate_id"] != candidate["id"]
        ):
            raise EngineError(
                "VERIFICATION_UNKNOWN",
                "candidate is not selected by a completed current redesign",
            )
        return run

    def cancel(self, id):
        with self.lock:
            job = self.store.get("job", id)
            if job["state"] in TERMINAL:
                return dict(job_id=id, state=job["state"])
            self.cancels[id].set()
            return dict(job_id=id, state="cancellation_requested")

    def export(self, candidate_id, key):
        candidate = self.store.get("candidate", candidate_id)
        reviews = [
            r for r in self.store.list("review") if r["candidate_id"] == candidate_id
        ]
        if (
            not reviews
            or reviews[-1]["decision"] != "accept"
            or reviews[-1]["input_hash"] != candidate["input_hash"]
        ):
            raise EngineError(
                "VERIFICATION_UNKNOWN",
                "candidate must have a current acceptance before export",
            )
        record = self.store.get("run", candidate["run_id"])

        def create():
            self.require_current_candidate(candidate)

            def perform(job, cancel):
                with self.lock:
                    self.require_current_candidate(candidate, allow_job=job["id"])
                    current = [
                        r
                        for r in self.store.list("review")
                        if r["candidate_id"] == candidate_id
                    ]
                    if not current or current[-1]["decision"] != "accept":
                        raise EngineError(
                            "VERIFICATION_UNKNOWN", "candidate acceptance was withdrawn"
                        )
                self.event(
                    job,
                    "verify",
                    "started",
                    "Reconstructing, replanning, and round-tripping STEP export",
                )
                revision = self.store.get("revision", record["revision_id"])
                report = json.loads(
                    self.store.artifacts.get(record["ai_report_artifact_id"])
                )
                request = dict(
                    template=candidate["template"],
                    candidate_id=candidate["geometry_candidate_id"],
                    target_id=record["target_id"],
                    baseline_metrics=record["baseline"]["metrics"],
                    comparison=candidate["comparison"],
                    ai_report=report,
                )
                result, blobs = self._native(
                    "http_export",
                    request,
                    cancel,
                    package=self.package(revision),
                    timeout=120,
                )
                with self.lock:
                    if cancel.is_set():
                        raise EngineError(
                            "CANCELLED", "export cancelled before completion"
                        )
                    self.require_current_candidate(candidate, allow_job=job["id"])
                    current = [
                        r
                        for r in self.store.list("review")
                        if r["candidate_id"] == candidate_id
                    ]
                    if not current or current[-1]["decision"] != "accept":
                        raise EngineError(
                            "VERIFICATION_UNKNOWN",
                            "candidate acceptance was withdrawn during export",
                        )
                    fresh = self.store.get("run", record["id"])
                    fresh["export"] = dict(
                        result,
                        artifact_id=blobs["checked_export.zip"],
                        review_candidate_id=candidate_id,
                    )
                    self.store.put("run", record["id"], fresh, fresh["revision_id"])
                self.event(
                    job,
                    "compare",
                    "completed",
                    "Export "
                    + result["status"]
                    + "; round trip "
                    + result["roundtrip_status"],
                    artifact_id=blobs["checked_export.zip"],
                )

            return self.submit("export", record["id"], perform)

        return self.mutation(
            "export:" + candidate_id,
            key,
            dict(input_hash=candidate["input_hash"]),
            create,
        )

    def run_view(self, id):
        record = self.store.get("run", id)
        events = []
        for job in self.store.list("job"):
            if job["run_id"] == id:
                events.extend(self.store.events(job["id"]))
        record["events"] = events
        return {k: v for k, v in record.items() if k != "baseline_artifact"}

    def revision_view(self, id):
        return revision_view(self.store.get("revision", id))
