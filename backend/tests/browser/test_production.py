"""Opt-in acceptance against real public read-only endpoints, with no local servers."""

import hashlib
import io
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile

import pytest
from playwright.sync_api import expect

from browser_harness import (
    _get,
    canvas_image,
    image_difference,
    new_page,
    report,
    shot,
)
from test_journey import rendered, drag

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        not os.environ.get("UNLOCK_PRODUCTION_WEB"),
        reason="production URLs must be explicitly selected",
    ),
]


@pytest.fixture(scope="module")
def production():
    web, api = (
        os.environ[k].rstrip("/")
        for k in ("UNLOCK_PRODUCTION_WEB", "UNLOCK_PRODUCTION_API")
    )
    for url in (web, api):
        parsed = urlsplit(url)
        assert parsed.scheme == "https" and not parsed.username and not parsed.password
        assert parsed.hostname not in ("localhost", "127.0.0.1", "::1")
    health = json.loads(_get(api + "/health", timeout=60)[1])
    assert health["mode"] == "read_only"
    run = json.loads(
        _get(api + "/v1/runs/" + health["provider"]["demo_run_id"], timeout=60)[1]
    )
    revision = json.loads(
        _get(api + "/v1/revisions/" + run["revision_id"], timeout=60)[1]
    )
    assert run["model"]["live"] is False
    assert revision["manifest"]["provenance"]["license"] == "CC-BY-4.0"
    assert run["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
    assert run["export"]["roundtrip_status"] == "passed"
    report["production"] = dict(
        web=web,
        api=api,
        run_id=run["id"],
        export_sha256=run["export"]["artifact_id"],
        live_model=False,
    )
    return web, api, run, revision


@pytest.mark.parametrize("size", [(1600, 1000), (390, 844)], ids=["desktop", "mobile"])
def test_public_recorded_demo_in_real_browser(browser, production, evidence_dir, size):
    web, api, run, revision = production
    label = "desktop" if size[0] > 1000 else "mobile"
    context, page, monitor = new_page(browser, api, size=size)
    page.set_default_timeout(60_000)
    page.set_default_navigation_timeout(90_000)
    local_requests = []
    context.on(
        "request",
        lambda r: local_requests.append(r.url)
        if urlsplit(r.url).hostname in ("localhost", "127.0.0.1", "::1")
        else None,
    )
    try:
        page.goto(web + "/")
        page.get_by_role("heading", level=1).wait_for()
        page.wait_for_load_state("networkidle", timeout=90_000)
        assert page.get_by_text("Presentation geometry, not analysis output").count()
        assert page.evaluate(
            "() => document.scrollingElement.scrollWidth <= innerWidth + 1"
        )
        shot(page, "production-" + label + "-home")
        page.get_by_role("link", name="Explore UNLOCK", exact=True).click()
        page.wait_for_url("**/projects/fixture_B02*")
        expect(
            page.get_by_text("Read-only B02 demonstration.", exact=False)
        ).to_be_visible()

        page.get_by_role("button", name="1 Inspect", exact=True).click()
        page.locator("canvas").first.wait_for()
        original = rendered(page)
        expect(page.locator('[data-geometry-source="backend-brep"]')).to_have_attribute(
            "data-preview-id", revision["preview_artifact_id"]
        )
        assert page.locator('[role="treeitem"]').count() == 8
        drag(page, 0, 50, 20)
        page.wait_for_timeout(200)
        assert image_difference(original, canvas_image(page)) > 0.005
        page.get_by_role("button", name="Reset", exact=True).click()
        shot(page, "production-" + label + "-original")

        page.get_by_role("button", name="2 Analyze", exact=True).click()
        expect(
            page.get_by_text("No path within supported operations", exact=True)
        ).to_be_visible()
        page.get_by_role("button", name="3 Redesign", exact=True).click()
        expect(page.get_by_test_id("run-outcome")).to_have_attribute(
            "data-outcome", "VERIFIED_IMPROVEMENT_FOUND"
        )
        assert "offline" in page.get_by_test_id("run-provenance").inner_text().lower()

        page.get_by_role("button", name="4 Compare", exact=True).click()
        page.locator("canvas").nth(1).wait_for()
        left, right = rendered(page, 0), rendered(page, 1)
        assert image_difference(left, right) > 0.003
        # R3F's intrinsic canvas height must not stretch a narrow grid row into
        # the other model or the evidence panel, even if pixels still render.
        viewport = page.get_by_role("main", name="Assembly viewport").bounding_box()
        assert viewport
        canvases = [page.locator("canvas").nth(i).bounding_box() for i in (0, 1)]
        for canvas in canvases:
            assert canvas
            assert canvas["y"] >= viewport["y"] - 1
            assert (
                canvas["y"] + canvas["height"] <= viewport["y"] + viewport["height"] + 1
            )
        if label == "mobile":
            assert canvases[0]["y"] + canvases[0]["height"] <= canvases[1]["y"] + 1
            panel = page.get_by_role("complementary", name="Evidence").bounding_box()
            assert panel and panel["y"] >= viewport["y"] + viewport["height"] - 1
        evidence = page.get_by_role("complementary", name="Evidence").inner_text()
        assert "no_path_supported" in evidence and "feasible" in evidence
        assert "manufacturing" in evidence.lower()
        expect(
            page.get_by_role("button", name="Accept for export", exact=True)
        ).to_be_disabled()
        slider = page.get_by_role("slider", name="Checked route position")
        slider.fill("0")
        page.wait_for_timeout(250)
        before = canvas_image(page, 1)
        slider.fill("1")
        page.wait_for_timeout(250)
        assert image_difference(before, canvas_image(page, 1)) > 0.002
        assert page.evaluate(
            "() => document.scrollingElement.scrollWidth <= innerWidth + 1"
        )
        shot(page, "production-" + label + "-comparison")
        if label == "mobile":
            page.screenshot(
                path=evidence_dir / "production-mobile-full-comparison.png",
                full_page=True,
            )

        page.get_by_role("button", name="5 Export", exact=True).click()
        expect(
            page.get_by_role("button", name="Create the package again")
        ).to_be_disabled()
        with page.expect_download() as downloaded:
            page.get_by_test_id("export-download").click()
        data = Path(downloaded.value.path()).read_bytes()
        assert hashlib.sha256(data).hexdigest() == run["export"]["artifact_id"]
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            bundle = json.loads(archive.read("bundle.json"))
            assert bundle["status"] == "full_assembly"
            assert set(archive.namelist()) == set(bundle["files"]) | {"bundle.json"}
            for name, metadata in bundle["files"].items():
                expected = (
                    metadata["sha256"] if isinstance(metadata, dict) else metadata
                )
                assert hashlib.sha256(archive.read(name)).hexdigest() == expected
            assert (
                "creativecommons.org/licenses/by/4.0/"
                in archive.read("LICENSE-B02.txt").decode()
            )
            assert (
                json.loads(archive.read("manifest.json"))["provenance"]["license"]
                == "CC-BY-4.0"
            )
            assert json.loads(archive.read("roundtrip.json"))["status"] == "passed"
        shot(page, "production-" + label + "-export")

        # Reload the deep link through Cloudflare, then navigate using real UI links.
        page.reload()
        expect(
            page.get_by_text("Read-only B02 demonstration.", exact=False)
        ).to_be_visible()
        page.get_by_role("link", name="Back to projects").click()
        page.wait_for_url("**/projects")
        expect(page.get_by_role("button", name="Choose files")).to_be_disabled()
        assert page.locator("tbody tr").count() == 1
        assert page.evaluate(
            "() => document.scrollingElement.scrollWidth <= innerWidth + 1"
        )
        shot(page, "production-" + label + "-projects")
        assert not local_requests
        assert all(call["method"] == "GET" for call in monitor.api_calls)
        assert not any(monitor.problems(allow_failed=("net::ERR_ABORTED",)).values())
        report.setdefault("production_browser", {})[label] = dict(
            viewport=list(size),
            api_reads=len(monitor.api_calls),
            local_requests=local_requests,
            artifact_sha256=hashlib.sha256(data).hexdigest(),
            download_members=len(bundle["files"]),
            original_and_revised_rendered=True,
            comparison_and_route_playback=True,
            navigation_and_reload=True,
            uploads_and_compute_disabled=True,
            console_and_network_errors=monitor.problems(
                allow_failed=("net::ERR_ABORTED",)
            ),
        )
    finally:
        context.close()


def test_public_compute_refused_and_private_paths_hidden(production):
    web, api, _, _ = production
    for path in (
        "/v1/projects",
        "/v1/projects/fixture_B02/imports",
        "/v1/revisions/unknown/runs",
        "/v1/runs/unknown/redesign",
        "/v1/jobs/unknown/cancel",
        "/v1/candidates/unknown/decision",
        "/v1/candidates/unknown/exports",
    ):
        request = Request(api + path, data=b"", method="POST", headers={"Origin": web})
        with pytest.raises(HTTPError) as denied:
            urlopen(request, timeout=60)
        assert denied.value.code == 403
    for origin in (web, api):
        for path in ("/.env", "/.modal.toml", "/backend/.work/private.step"):
            try:
                with urlopen(origin + path, timeout=60) as response:
                    # SPA fallback can return index.html for a navigation-like URL.
                    assert response.headers.get_content_type() == "text/html"
                    assert b"<!doctype html>" in response.read().lower()
            except HTTPError as exc:
                assert exc.code in (403, 404)
