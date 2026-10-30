"""Local UNLOCK HTTP API. Start with python -m unlock_engine.api."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..ai.config import BACKEND_ROOT, load_environment
from ..contracts import POLICY, EngineError
from .contracts import (
    DecisionInput,
    JobResponse,
    ProjectInput,
    ProjectSummary,
    RevisionView,
    RunView,
    StartRun,
)

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}

IDEM = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def create_app(
    *,
    root=None,
    config=None,
    seed=True,
    coordinator_factory=None,
    read_only=False,
    allowed_hosts=None,
):
    env = load_environment()
    path = Path(root) if root else Path(env.get("UNLOCK_DATA_DIR", ".data"))
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    origins = [
        x.strip()
        for x in env.get(
            "UNLOCK_CORS_ORIGINS", "http://localhost:5183,http://127.0.0.1:5183"
        ).split(",")
        if x.strip()
    ]

    @asynccontextmanager
    async def lifespan(app):
        if coordinator_factory:
            coordinator = coordinator_factory(path)
        else:
            from .coordinator import Coordinator

            coordinator = Coordinator(path, config=config)
        app.state.coordinator = coordinator
        if seed:
            coordinator.seed()
        yield
        await asyncio.to_thread(coordinator.close)

    app = FastAPI(title="UNLOCK engineering API", version="1.0", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts
        or ["localhost", "127.0.0.1", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def local_boundary(request, call_next):
        if read_only:
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                return JSONResponse(
                    EngineError(
                        "FORBIDDEN",
                        "This is a read-only recorded engineering demonstration. Compute requires authenticated Modal access.",
                    ).envelope(),
                    403,
                )
            if not request.app.state.coordinator.limiter.allow():
                return JSONResponse(
                    EngineError(
                        "LIMIT_EXCEEDED", "Demo request limit reached; retry later."
                    ).envelope(),
                    429,
                    headers={"Retry-After": "60"},
                )
        # This coordinator is a local tool. No implicit unauthenticated public upload/API mode.
        if (
            not read_only
            and request.client
            and request.client.host
            not in (
                "127.0.0.1",
                "::1",
                "testclient",
            )
        ):
            return JSONResponse(
                EngineError(
                    "FORBIDDEN", "local coordinator accepts loopback clients only"
                ).envelope(),
                403,
            )
        origin = request.headers.get("origin")
        if origin and origin not in origins:
            return JSONResponse(
                EngineError("FORBIDDEN", "request origin is not configured").envelope(),
                403,
            )
        length = request.headers.get("content-length")
        try:
            size = int(length) if length is not None else 0
        except ValueError:
            size = -1
        if size < 0 or size > POLICY.max_compressed_bytes + 1024 * 1024:
            return JSONResponse(
                EngineError(
                    "LIMIT_EXCEEDED", "request exceeds the supported upload size"
                ).envelope(),
                413,
            )
        if (
            request.method == "POST"
            and "multipart/" in request.headers.get("content-type", "")
            and length is None
        ):
            return JSONResponse(
                EngineError(
                    "INVALID_PACKAGE",
                    "multipart upload requires a bounded Content-Length",
                ).envelope(),
                411,
            )
        return await call_next(request)

    # Wrap boundary errors too, so authorized frontends can read a 403/429 envelope.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID"],
    )

    @app.exception_handler(EngineError)
    async def engine_error(request, exc):
        status = {
            "NOT_FOUND": 404,
            "FORBIDDEN": 403,
            "STALE_REVISION": 409,
            "VERIFICATION_UNKNOWN": 409,
            "LIMIT_EXCEEDED": 413,
        }.get(exc.code, 422)
        return JSONResponse(exc.envelope(), status)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        # Pydantic's default error payload echoes input; omit it at this boundary.
        envelope = EngineError(
            "INVALID_MANIFEST", "request schema validation failed"
        ).envelope()
        envelope["field_errors"] = [
            dict(field=".".join(map(str, e["loc"])), message=e["msg"])
            for e in exc.errors()
        ]
        return JSONResponse(envelope, 422)

    def coord(request):
        return request.app.state.coordinator

    @app.get("/health")
    def health(request: Request):
        c = coord(request)
        return dict(
            status="ok",
            mode="read_only" if read_only else "local",
            provider=dict(
                c.config.public(),
                **(
                    dict(access="read_only", demo_run_id=c.demo_run_id)
                    if read_only
                    else {}
                ),
            ),
        )

    @app.get("/v1/projects", response_model=list[ProjectSummary])
    def projects(request: Request):
        return coord(request).store.list("project")

    @app.post("/v1/projects", status_code=201)
    def create_project(body: ProjectInput, request: Request):
        from .coordinator import uid

        p = coord(request).project(uid("project"), body.name)
        return dict(project_id=p["id"], revisions=[])

    @app.get("/v1/projects/{id}")
    def project(id: str, request: Request):
        c = coord(request)
        p = c.store.get("project", id)
        return dict(
            p,
            revisions=[
                dict(id=r["id"])
                for r in c.store.list("revision")
                if r["project_id"] == id
            ],
        )

    @app.post("/v1/projects/{id}/imports", status_code=202, response_model=JobResponse)
    async def import_package(
        id: str,
        request: Request,
        idempotency_key: IDEM,
        package: list[UploadFile] = File(...),
    ):
        if len(package) not in (1, 2, 3):
            raise EngineError(
                "INVALID_PACKAGE",
                "upload one ZIP or STEP plus manifest and optional attribution",
            )
        files = {}
        total = 0
        for part in package:
            name = part.filename or ""
            if name in files:
                raise EngineError("INVALID_PACKAGE", "duplicate package filename")
            data = await part.read(POLICY.max_compressed_bytes + 1)
            await part.close()
            total += len(data)
            if total > POLICY.max_compressed_bytes:
                raise EngineError("LIMIT_EXCEEDED", "package exceeds 25 MB compressed")
            files[name] = data
        # ZIP validation is bounded byte processing; STEP parsing stays in a native worker.
        return coord(request).import_files(id, idempotency_key, files)

    @app.get("/v1/revisions/{id}", response_model=RevisionView)
    def revision(id: str, request: Request):
        return coord(request).revision_view(id)

    @app.post("/v1/revisions/{id}/runs", status_code=202, response_model=JobResponse)
    def start_run(id: str, body: StartRun, request: Request, idempotency_key: IDEM):
        return coord(request).start_run(id, body, idempotency_key)

    @app.get("/v1/runs/{id}", response_model=RunView)
    def run(id: str, request: Request):
        return coord(request).run_view(id)

    @app.post("/v1/runs/{id}/redesign", status_code=202, response_model=JobResponse)
    def redesign(id: str, request: Request, idempotency_key: IDEM):
        return coord(request).redesign(id, idempotency_key)

    @app.get("/v1/jobs/{id}")
    def job(id: str, request: Request):
        return {
            k: v
            for k, v in coord(request).store.get("job", id).items()
            if not k.startswith("_")
        }

    @app.get("/v1/jobs/{id}/events")
    async def events(
        id: str, request: Request, last_event_id: Annotated[str | None, Header()] = None
    ):
        c = coord(request)
        c.store.get("job", id)
        try:
            cursor = int(last_event_id or 0)
        except ValueError:
            raise EngineError(
                "INVALID_MANIFEST", "Last-Event-ID must be an integer"
            ) from None

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                batch = c.store.events(id, cursor)
                for event in batch:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                    if event.get("terminal"):
                        return
                if c.store.get("job", id)["state"] in TERMINAL:
                    return
                if not batch:
                    yield ": waiting for engineering worker\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/jobs/{id}/cancel", status_code=202)
    def cancel(id: str, request: Request, idempotency_key: IDEM):
        return coord(request).cancel(id)

    @app.get("/v1/candidates/{id}")
    def candidate(id: str, request: Request):
        return coord(request).store.get("candidate", id)

    @app.post("/v1/candidates/{id}/decision")
    def decide(id: str, body: DecisionInput, request: Request):
        return coord(request).decide(id, body)

    @app.post(
        "/v1/candidates/{id}/exports", status_code=202, response_model=JobResponse
    )
    def export(id: str, request: Request, idempotency_key: IDEM):
        return coord(request).export(id, idempotency_key)

    @app.get("/v1/artifacts/{id}")
    def artifact(id: str, request: Request):
        try:
            data = coord(request).store.artifacts.get(id)
        except FileNotFoundError:
            raise EngineError("NOT_FOUND", "artifact not found") from None
        media = (
            "application/zip"
            if data.startswith(b"PK\x03\x04")
            else "application/json"
            if data[:1] in (b"{", b"[")
            else "application/octet-stream"
        )
        return Response(
            data,
            media_type=media,
            headers={
                "ETag": '"' + id + '"',
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="{id}.zip"'
                if media == "application/zip"
                else "inline",
            },
        )

    return app


app = create_app()
