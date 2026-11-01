"""Real precomputed engineering evidence through the public read-only UI."""

import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from playwright.sync_api import expect

from browser_harness import (
    BACKEND,
    FRONTEND,
    EVIDENCE,
    _wait,
    _get,
    build_frontend,
    new_page,
)

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def readonly_web(tmp_path_factory):
    from unlock_engine.deployment.jobs import run_job

    root = tmp_path_factory.mktemp("readonly-browser")
    supplied = os.environ.get("UNLOCK_READONLY_TEST_ROOT")
    if supplied:
        snapshot = Path(supplied)
    else:
        id = uuid.uuid4().hex
        run_job(root / "jobs", id)
        snapshot = root / "jobs" / id
    api, web = "http://127.0.0.1:8110", "http://127.0.0.1:5198"
    env = dict(
        os.environ,
        PYTHONPATH=str(BACKEND / "src"),
        UNLOCK_CORS_ORIGINS=web,
        UNLOCK_SNAPSHOT=str(snapshot),
        MODEL_API_KEY="",
        AI_PROVIDER="mock",
    )
    bundle = build_frontend(api, root / "dist")
    code = "import os,uvicorn; from unlock_engine.deployment.snapshot import create_snapshot_app; uvicorn.run(create_snapshot_app(os.environ['UNLOCK_SNAPSHOT']),host='127.0.0.1',port=8110)"
    with (root / "servers.log").open("w") as log:
        servers = [
            subprocess.Popen(
                [sys.executable, "-c", code], env=env, stdout=log, stderr=log
            ),
            subprocess.Popen(
                [
                    str(FRONTEND / "node_modules/.bin/vite"),
                    "preview",
                    "--outDir",
                    str(bundle),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5198",
                    "--strictPort",
                ],
                cwd=FRONTEND,
                env=env,
                stdout=log,
                stderr=log,
            ),
        ]
        try:
            _wait(lambda: _get(api + "/health")[0] == 200, 30, "snapshot API")
            _wait(lambda: _get(web)[0] == 200, 30, "snapshot frontend")
            yield api, web
        finally:
            for server in servers:
                server.terminate()
                server.wait(timeout=10)


def test_readonly_recorded_cad_download_without_compute(browser, readonly_web):
    api, web = readonly_web
    context, page, monitor = new_page(browser, api)
    try:
        page.goto(web + "/projects")
        page.wait_for_load_state("networkidle")
        expect(
            page.get_by_text("Read-only engineering demonstration", exact=True)
        ).to_be_visible()
        expect(page.get_by_role("button", name="Choose files")).to_be_disabled()
        page.get_by_role("link", name="Open", exact=True).click()
        expect(
            page.get_by_text("Read-only demonstration.", exact=False)
        ).to_be_visible()
        page.get_by_role("button", name="4 Compare", exact=True).click()
        expect(
            page.get_by_role("button", name="Accept for export", exact=True)
        ).to_be_disabled()
        page.get_by_role("button", name="5 Export", exact=True).click()
        expect(
            page.get_by_role("button", name="Create the package again")
        ).to_be_disabled()
        with page.expect_download() as download:
            page.get_by_test_id("export-download").click()
        data = Path(download.value.path()).read_bytes()
        from unlock_engine.deployment.jobs import validate_export

        assert validate_export(data)
        assert all(call["method"] == "GET" for call in monitor.api_calls)
        assert not any(monitor.problems(allow_failed=("net::ERR_ABORTED",)).values())
        page.screenshot(path=str(EVIDENCE / "readonly-cloud-b02.png"))
    finally:
        context.close()
