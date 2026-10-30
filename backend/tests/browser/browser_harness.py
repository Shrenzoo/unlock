"""Real-service browser acceptance harness.

Every stack is the actual FastAPI coordinator with its native CAD workers and a
production frontend bundle built against it, driven by installed Chrome through
Playwright. Responses are never stubbed; failure scenarios inject faults only by
starting a backend in a different configuration, pointing a bundle at a closed
port or aborting requests for a bounded interval.

Paid inference is impossible here: every backend starts with MODEL_API_KEY
blanked and RUN_META_LIVE_TESTS=0. Select with `pytest -m browser tests/browser`.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"
RUN_STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVIDENCE = (
    Path(
        os.environ.get("UNLOCK_BROWSER_EVIDENCE", BACKEND / ".work/browser-acceptance")
    )
    / RUN_STAMP
)
VIEWPORTS = dict(desktop=(1600, 1000), laptop=(1366, 768), mobile=(390, 844))


def _get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def _wait(predicate, timeout, what):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (urllib.error.URLError, ConnectionError, OSError, ValueError) as exc:
            last = exc
        time.sleep(0.25)
    raise TimeoutError(f"{what} not ready after {timeout}s ({last})")


@dataclass
class Stack:
    """One backend (possibly absent) plus a frontend bundle pointed at it."""

    name: str
    api: str
    web: str
    data: Path | None
    processes: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)

    def get(self, path: str):
        return json.loads(_get(self.api + path, timeout=30)[1])

    def raw(self, path: str) -> bytes:
        return _get(self.api + path, timeout=60)[1]

    def post(self, path: str, body=None, headers=None):
        request = urllib.request.Request(
            self.api + path,
            data=json.dumps(body).encode() if body is not None else b"",
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"null")

    def project(self, fixture_code: str) -> dict:
        return next(
            p for p in self.get("/v1/projects") if p["fixture_code"] == fixture_code
        )

    def latest_revision(self, project_id: str) -> dict:
        detail = self.get(f"/v1/projects/{project_id}")
        return self.get(f"/v1/revisions/{detail['revisions'][-1]['id']}")

    def stop(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)


def _spawn(args, cwd, env, log):
    return subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


_bundles: dict[str, Path] = {}


def build_frontend(api: str, out: Path) -> Path:
    """Production bundle for one API origin (Vite bakes the origin in at build time)."""
    if api in _bundles:
        return _bundles[api]
    env = dict(os.environ, VITE_UNLOCK_API=api)
    env.pop("VITE_UNLOCK_MODE", None)
    subprocess.run(
        [
            str(FRONTEND / "node_modules/.bin/vite"),
            "build",
            "--outDir",
            str(out),
            "--emptyOutDir",
        ],
        cwd=FRONTEND,
        env=env,
        check=True,
        capture_output=True,
    )
    _bundles[api] = out
    return out


def start_stack(name, api_port, web_port, root, *, provider="mock", backend=True):
    api = f"http://127.0.0.1:{api_port}"
    web = f"http://127.0.0.1:{web_port}"
    stack = Stack(name, api, web, root / "data" if backend else None)
    logs = EVIDENCE / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    try:
        if backend:
            env = {
                k: v
                for k, v in os.environ.items()
                if not k.endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD"))
            }
            env.update(
                AI_PROVIDER=provider,
                MODEL_API_KEY="",
                RUN_META_LIVE_TESTS="0",
                UNLOCK_DATA_DIR=str(stack.data),
                UNLOCK_CORS_ORIGINS=f"{web},http://localhost:{web_port}",
                PYTHONPATH=str(BACKEND / "src"),
            )
            started = time.monotonic()
            stack.processes.append(
                _spawn(
                    [
                        sys.executable,
                        "-m",
                        "unlock_engine.api",
                        "--port",
                        str(api_port),
                    ],
                    BACKEND,
                    env,
                    (logs / f"{name}-backend.log").open("wb"),
                )
            )
            _wait(lambda: _get(api + "/health")[0] == 200, 120, f"{name} backend")
            _wait(
                lambda: (
                    sum(p["status"] == "ready" for p in stack.get("/v1/projects")) >= 3
                ),
                300,
                f"{name} bundled fixtures",
            )
            stack.timings["backend_ready_s"] = round(time.monotonic() - started, 2)
        started = time.monotonic()
        bundle = build_frontend(api, root / f"bundle-{api_port}")
        stack.timings["frontend_build_s"] = round(time.monotonic() - started, 2)
        stack.processes.append(
            _spawn(
                [
                    str(FRONTEND / "node_modules/.bin/vite"),
                    "preview",
                    "--outDir",
                    str(bundle),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                    "--strictPort",
                ],
                FRONTEND,
                dict(os.environ),
                (logs / f"{name}-frontend.log").open("wb"),
            )
        )
        _wait(lambda: _get(web + "/")[0] == 200, 60, f"{name} frontend")
    except BaseException:
        stack.stop()
        raise
    return stack


report: dict = dict(
    started_at=RUN_STAMP,
    environment={},
    stacks={},
    tests={},
    measurements={},
    correlation={},
)


@pytest.fixture(scope="session")
def evidence_dir():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    return EVIDENCE


@pytest.fixture(scope="session")
def stack(tmp_path_factory, evidence_dir):
    """The main stack: offline scripted decision policy, real CAD services.

    UNLOCK_E2E_API/UNLOCK_E2E_WEB reuse an already running stack while iterating
    on tests; evidence runs always start fresh servers and a production bundle.
    """
    if os.environ.get("UNLOCK_E2E_API"):
        s = Stack(
            "reused", os.environ["UNLOCK_E2E_API"], os.environ["UNLOCK_E2E_WEB"], None
        )
        report["stacks"]["mock"] = dict(api=s.api, web=s.web, reused=True)
        yield s
        return
    s = start_stack("mock", 8100, 5193, tmp_path_factory.mktemp("stack-mock"))
    report["stacks"]["mock"] = dict(
        api=s.api, web=s.web, provider=s.get("/health")["provider"], **s.timings
    )
    yield s
    s.stop()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        report["environment"]["browser"] = (
            f"{b.browser_type.name} {b.version} (installed Chrome, headless)"
        )
        yield b
        b.close()


class Monitor:
    """Everything the pages of one context report: console, page and network errors."""

    def __init__(self, context, api: str):
        self.api = api
        self.console_errors: list[str] = []
        self.page_errors: list[str] = []
        self.failed_requests: list[str] = []
        self.http_errors: list[str] = []
        self.api_calls: list[dict] = []
        self.succeeded: set[str] = set()
        self.superseded: list[str] = []
        context.on("page", self.attach)

    def attach(self, page):
        page.on(
            "console",
            lambda m: self.console_errors.append(m.text) if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: self.page_errors.append(str(e)))
        page.on(
            "requestfailed",
            lambda r: self.failed_requests.append(f"{r.method} {r.url} {r.failure}"),
        )
        page.on("response", self._response)

    def _response(self, r):
        if r.url.startswith(self.api):
            self.api_calls.append(
                dict(
                    method=r.request.method,
                    path=r.url[len(self.api) :],
                    status=r.status,
                )
            )
        if r.status >= 400:
            self.http_errors.append(f"{r.status} {r.request.method} {r.url}")
        elif r.status < 300:
            self.succeeded.add(f"{r.request.method} {r.url}")

    def problems(self, *, allow_failed=(), allow_console=(), allow_http=()):
        """Errors that matter. An aborted request is excused only when the same
        request later succeeded (a superseded fetch, e.g. a selection change or a
        dev-mode remount) or when the caller names it (a link that became a download)."""

        def keep(items, allowed):
            return [i for i in items if not any(a in i for a in allowed)]

        failed = []
        for f in self.failed_requests:
            request = f.rsplit(" ", 1)[0]
            if f.endswith("net::ERR_ABORTED") and request in self.succeeded:
                self.superseded.append(f)
            else:
                failed.append(f)
        return dict(
            console=keep(self.console_errors, allow_console),
            page=self.page_errors,
            failed=keep(failed, allow_failed),
            http=keep(self.http_errors, allow_http),
        )


def new_page(browser, api, *, size=VIEWPORTS["desktop"], **context_options):
    context = browser.new_context(
        viewport=dict(width=size[0], height=size[1]),
        reduced_motion="reduce",
        accept_downloads=True,
        **context_options,
    )
    monitor = Monitor(context, api)
    page = context.new_page()
    return context, page, monitor


def shot(page, name: str, **options):
    path = EVIDENCE / f"{name}.png"
    page.screenshot(path=str(path), **options)
    return path


def canvas_image(page, index=0):
    """One WebGL canvas exactly as composited on screen (not a DOM assertion)."""
    from PIL import Image

    return Image.open(
        io.BytesIO(page.locator("canvas").nth(index).screenshot())
    ).convert("RGB")


def distinct_colours(image) -> int:
    pixels = list(image.getdata())
    return len(set(pixels[:: max(1, len(pixels) // 20000)]))


def colour_centroid(image, rgb, tolerance=36):
    """Centroid and count of pixels close to a material colour; None when absent."""
    xs = ys = n = 0
    width = image.size[0]
    for i, p in enumerate(image.getdata()):
        if (
            abs(p[0] - rgb[0]) <= tolerance
            and abs(p[1] - rgb[1]) <= tolerance
            and abs(p[2] - rgb[2]) <= tolerance
        ):
            xs += i % width
            ys += i // width
            n += 1
    return (xs / n, ys / n, n) if n else None


def image_difference(a, b) -> float:
    """Fraction of sampled pixels that differ noticeably between two renders."""
    pa, pb = list(a.getdata()), list(b.getdata())
    step = max(1, len(pa) // 40000)
    sample = range(0, min(len(pa), len(pb)), step)
    changed = sum(
        1 for i in sample if sum(abs(pa[i][k] - pb[i][k]) for k in range(3)) > 30
    )
    return changed / max(1, len(sample))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    result = outcome.get_result()
    if result.when == "call" or (result.when == "setup" and result.outcome != "passed"):
        report["tests"][item.nodeid] = dict(
            outcome=result.outcome,
            duration_s=round(result.duration, 2),
            detail=str(result.longrepr)[-1500:] if result.failed else None,
        )


def pytest_sessionfinish(session, exitstatus):
    if not report["tests"]:
        return

    def run(*args):
        try:
            return subprocess.run(
                args, capture_output=True, text=True, cwd=ROOT
            ).stdout.strip()
        except OSError:
            return None

    report["environment"].update(
        git_commit=run("git", "rev-parse", "HEAD"),
        git_branch=run("git", "rev-parse", "--abbrev-ref", "HEAD"),
        python=sys.version.split()[0],
        node=run("node", "--version"),
        platform=sys.platform,
    )
    report["finished_at"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report["exit_status"] = int(exitstatus)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "report.json").write_text(json.dumps(report, indent=2, default=str))
