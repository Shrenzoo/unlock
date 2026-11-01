"""Access-code gateway. Public demo routes never read this private namespace."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from ..artifacts import atomic_write
from ..contracts import EngineError
from .snapshot import (
    MAX_JOB_BYTES,
    MAX_STORAGE_BYTES,
    SnapshotCoordinator,
    RequestLimiter,
    storage_size,
)

SESSION_SECONDS = 7200
MAX_UPLOAD = 10 * 1024**2
MAX_JOBS = 6
MAX_SESSION_JOBS = 2


def create_judge_app(
    root,
    *,
    code_hash,
    origins,
    submit,
    refresh=lambda: None,
    commit=lambda: None,
    clock=time.time,
):
    """One container owns the durable ledger; reservations survive restarts/errors.

    submit must dispatch the existing private, bounded offline worker. Failure
    never refunds a reservation. No arbitrary function, path or live-model flag
    can be supplied by a client.
    """
    if not re.fullmatch(r"[a-f0-9]{64}", code_hash):
        raise ValueError("judge access-code hash is required")
    root = Path(root)
    ledger_path = root / "judge-ledger.json"
    lock = threading.RLock()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    allowed = set(origins)
    limiter = RequestLimiter(per_minute=120, per_hour=1200)

    def load():
        refresh()
        if not ledger_path.exists():
            return dict(sessions={}, jobs={}, attempts=[])
        return json.loads(ledger_path.read_bytes())

    def save(data):
        atomic_write(ledger_path, json.dumps(data).encode())
        commit()

    def fail(message, status=403):
        return JSONResponse(
            dict(message=message),
            status,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    def identity(request, ledger):
        bearer = request.headers.get("authorization", "")
        if not bearer.startswith("Bearer ") or len(bearer) > 200:
            return None
        key = hashlib.sha256(bearer[7:].encode()).hexdigest()
        session = ledger["sessions"].get(key)
        return key if session and session["expires"] > clock() else None

    @app.middleware("http")
    async def boundary(request, call_next):
        route_path = request.url.path.removeprefix(request.scope.get("root_path", ""))
        origin = request.headers.get("origin")
        if origin and origin not in allowed:
            return fail("Origin is not allowed")
        if request.method == "OPTIONS":
            return await call_next(request)
        if not limiter.allow():
            return fail("Judge request limit reached. Retry later.", 429)
        if route_path != "/sessions":
            if not request.headers.get("authorization", "").startswith("Bearer "):
                return fail("A judge session is required", 401)
            with lock:
                data = load()
                owner = identity(request, data)
                if owner is None:
                    return fail(
                        "Judge session expired. Enter your access code again.", 401
                    )
                request.state.owner = owner
        # Bound the actual body, including a chunked request, before parsing it.
        if request.method == "POST":
            limit = MAX_UPLOAD + 65536 if route_path == "/jobs" else 1024
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > limit:
                    return fail("Upload exceeds the judge limit", 413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    @app.post("/sessions")
    async def login(request: Request):
        with lock:
            data = load()
            now = clock()
            attempts = [t for t in data["attempts"] if t > now - 3600]
            if len(attempts) >= 60:
                return fail("Access-code attempt limit reached. Try again later.", 429)
            data["attempts"] = attempts + [now]
            save(data)
            try:
                body = await request.json()
                code = body.get("code", "")
                valid = isinstance(code, str) and hmac.compare_digest(
                    hashlib.sha256(code.encode()).hexdigest(), code_hash
                )
            except (ValueError, AttributeError):
                valid = False
            if not valid:
                return fail("Access code is not valid", 401)
            token = secrets.token_urlsafe(32)
            key = hashlib.sha256(token.encode()).hexdigest()
            # Expired sessions are no longer authentication entries; job ownership
            # remains in the permanent, bounded job ledger.
            data["sessions"] = {
                k: v for k, v in data["sessions"].items() if v["expires"] > now
            }
            data["sessions"][key] = dict(expires=now + SESSION_SECONDS)
            save(data)
            return dict(token=token, expires=now + SESSION_SECONDS)

    def owned(data, owner, job):
        record = data["jobs"].get(job)
        return record if record and record["owner"] == owner else None

    def status(job):
        path = root / job / "status.json"
        if not path.exists():
            return dict(state="queued")
        result = json.loads(path.read_bytes())
        if (
            result["state"] not in ("completed", "failed")
            and clock() - result.get("updated_at", 0) > 600
        ):
            result["state"] = "interrupted"
        return result

    @app.get("/session")
    def session(request: Request):
        with lock:
            data = load()
            jobs = [
                {"id": k, "state": status(k)["state"]}
                for k, v in data["jobs"].items()
                if v["owner"] == request.state.owner
            ]
            return dict(
                jobs=jobs,
                remaining=max(
                    0, min(MAX_SESSION_JOBS - len(jobs), MAX_JOBS - len(data["jobs"]))
                ),
                max_upload_bytes=MAX_UPLOAD,
                offline=True,
            )

    @app.delete("/session")
    def logout(request: Request):
        with lock:
            data = load()
            data["sessions"].pop(request.state.owner, None)
            save(data)
        return dict(logged_out=True)

    @app.post("/jobs", status_code=202)
    async def start(request: Request):
        # Authenticate before the multipart parser or any compute. The middleware
        # has already bounded the actual incoming bytes.
        form = await request.form(max_files=3, max_fields=1, max_part_size=MAX_UPLOAD)
        parts = form.getlist("package")
        files = {}
        for part in parts:
            if not hasattr(part, "filename"):
                return fail("Invalid package", 422)
            name = part.filename or ""
            if (
                not name
                or len(name) > 128
                or "/" in name
                or "\\" in name
                or name in files
                or not re.search(r"\.(zip|step|stp|json)$", name, re.I)
            ):
                return fail("Unsupported or duplicate package filename", 422)
            files[name] = await part.read(MAX_UPLOAD + 1)
            await part.close()
        if not 1 <= len(files) <= 3 or sum(map(len, files.values())) > MAX_UPLOAD:
            return fail("Choose a package of at most 10 MiB", 413)
        if not (
            len(files) == 1 and next(iter(files)).lower().endswith(".zip")
        ) and not (
            "manifest.json" in files
            and any(re.search(r"\.st[ep]+$", n, re.I) for n in files)
        ):
            return fail("Choose one ZIP or STEP plus manifest.json", 422)
        target = form.get("target_id", "target")
        if not isinstance(target, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,128}", target
        ):
            return fail("Invalid target occurrence ID", 422)
        idem = request.headers.get("idempotency-key", "")
        if not re.fullmatch(r"[A-Za-z0-9-]{16,128}", idem):
            return fail("An idempotency key is required", 422)
        digest = hashlib.sha256(
            json.dumps(
                {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())},
                sort_keys=True,
            ).encode()
            + target.encode()
        ).hexdigest()
        with lock:
            data = load()
            owner = request.state.owner
            previous = next(
                (
                    k
                    for k, v in data["jobs"].items()
                    if v["owner"] == owner and v["idem"] == idem
                ),
                None,
            )
            if previous:
                if data["jobs"][previous]["digest"] != digest:
                    return fail("Idempotency key already used for another package", 409)
                return dict(job_id=previous)
            if (
                len(data["jobs"]) >= MAX_JOBS
                or sum(v["owner"] == owner for v in data["jobs"].values())
                >= MAX_SESSION_JOBS
            ):
                return fail("Judge job allowance exhausted", 429)
            for key, entry in data["jobs"].items():
                state = status(key)["state"]
                if (
                    state not in ("completed", "failed", "interrupted")
                    and clock() - entry["created"] < 600
                ):
                    return fail(
                        "Another analysis is running. Please try again shortly.", 409
                    )
            if storage_size(root) + MAX_JOB_BYTES > MAX_STORAGE_BYTES:
                return fail("Engineering storage allowance exhausted", 429)
            job = secrets.token_hex(16)
            data["jobs"][job] = dict(
                owner=owner, idem=idem, digest=digest, created=clock()
            )
            save(data)  # Reserve durably BEFORE dispatch; no crash/retry refunds.
            try:
                submit(job, files, target)
            except Exception:
                atomic_write(
                    root / job / "status.json",
                    json.dumps(dict(state="failed", error="DISPATCH_FAILED")).encode(),
                )
                commit()
                return fail(
                    "Could not start analysis; the attempt remains reserved", 503
                )
            return dict(job_id=job)

    @app.get("/jobs/{job}")
    def poll(job: str, request: Request):
        with lock:
            data = load()
            if not owned(data, request.state.owner, job):
                return fail("Job not found", 404)
            result = status(job)
            if (
                result["state"] == "queued"
                and clock() - data["jobs"][job]["created"] > 600
            ):
                result["state"] = "interrupted"
            response = dict(
                job_id=job,
                state=result["state"],
                phase=result.get("phase"),
                error=result.get("error"),
            )
            if result["state"] == "completed":
                c = SnapshotCoordinator(root / job)
                response.update(
                    project_id=c.store.list("project")[-1]["id"], run_id=c.demo_run_id
                )
            return response

    @app.get("/jobs/{job}/view/{path:path}")
    def view(job: str, path: str, request: Request):
        with lock:
            data = load()
            if (
                not owned(data, request.state.owner, job)
                or status(job)["state"] != "completed"
            ):
                return fail("Job not found or not complete", 404)
            c = SnapshotCoordinator(root / job)
            try:
                if path == "health":
                    return dict(
                        provider=dict(
                            c.config.public(),
                            access="read_only",
                            demo_run_id=c.demo_run_id,
                        )
                    )
                if path == "v1/projects":
                    return c.store.list("project")
                match = re.fullmatch(
                    r"v1/(projects|revisions|runs|artifacts)/([A-Za-z0-9_.-]+)", path
                )
                if not match:
                    return fail("Not found", 404)
                kind, id = match.groups()
                if kind == "artifacts":
                    if not re.fullmatch(r"[a-f0-9]{64}", id):
                        return fail("Not found", 404)
                    payload = c.store.artifacts.get(id)
                    return Response(payload, media_type="application/octet-stream")
                if kind == "projects":
                    return dict(
                        c.store.get("project", id),
                        revisions=[
                            dict(id=r["id"])
                            for r in c.store.list("revision")
                            if r["project_id"] == id
                        ],
                    )
                return c.revision_view(id) if kind == "revisions" else c.run_view(id)
            except (EngineError, FileNotFoundError):
                return fail("Not found", 404)

    return app
