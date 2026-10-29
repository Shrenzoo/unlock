"""Browser acceptance over the actual local HTTP coordinator, never fixture responses.

Run with the webapp-testing with_server.py helper; writes local screenshots and
an execution report to backend/.work/meta-validation/browser/.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    output = Path(__file__).resolve().parents[1] / ".work/meta-validation/browser"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    responses = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=[
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
            ],
        )
        page = browser.new_page(
            viewport={"width": 1600, "height": 1000}, reduced_motion="reduce"
        )
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "response",
            lambda r: responses.append(dict(url=r.url, status=r.status))
            if "/v1/" in r.url
            else None,
        )
        page.goto("http://127.0.0.1:5183/projects")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(output / "projects.png"), full_page=True)
        # Inspect actual DOM before acting, following the testing skill.
        (output / "projects-dom.txt").write_text(page.locator("body").inner_text())
        row = page.get_by_role("row").filter(has_text="Trapped service component")
        row.get_by_role("link", name="Open", exact=True).wait_for(timeout=60000)
        row.get_by_role("link", name="Open", exact=True).click()
        page.get_by_role("treeitem").filter(has_text="target").first.wait_for(
            timeout=30000
        )
        page.get_by_role("treeitem").filter(has_text="target").first.click()
        page.get_by_role("button", name="Set as repair target").click()
        page.get_by_role("button", name="Analyze removal of target").click()
        page.get_by_role("button", name="Run baseline analysis").click()
        page.get_by_role("button", name="Explore a redesign").wait_for(timeout=120000)
        page.screenshot(path=str(output / "baseline.png"), full_page=True)
        assert page.locator('[data-geometry-source="backend-brep"]').count() == 1
        page.get_by_role("button", name="Explore a redesign").click()
        page.get_by_role("button", name="Request redesign").click()
        page.get_by_text("VERIFIED IMPROVEMENT FOUND", exact=True).wait_for(
            timeout=120000
        )
        page.screenshot(path=str(output / "redesign.png"), full_page=True)
        page.get_by_role("button", name="Compare with the original").click()
        page.get_by_role("button", name="Accept for export", exact=True).wait_for()
        assert page.get_by_role(
            "button", name="Accept for export", exact=True
        ).is_enabled()
        assert page.locator("canvas").count() == 2
        page.get_by_role("slider", name="Checked route position").fill("1")
        page.screenshot(path=str(output / "compare.png"), full_page=True)
        (output / "compare-dom.txt").write_text(page.locator("body").inner_text())
        page.get_by_role("button", name="Accept for export", exact=True).click()
        page.get_by_text(
            "Accepted for checked export. Engineering release remains unassessed.",
            exact=True,
        ).wait_for()
        page.get_by_role("button", name="Export", exact=True).click()
        page.get_by_role("button", name="Download checked package", exact=True).click()
        page.get_by_text(
            "Export full_assembly; round trip passed.", exact=False
        ).wait_for(timeout=120000)
        page.screenshot(path=str(output / "export.png"), full_page=True)
        (output / "export-dom.txt").write_text(page.locator("body").inner_text())
        # Every engineering request above went to the real local service.

        assert any(
            "/v1/artifacts/" in r["url"] and r["status"] == 200 for r in responses
        )
        assert not errors, errors
        (output / "report.json").write_text(
            json.dumps(
                dict(
                    status="passed",
                    provider="offline scripted; real CAD services",
                    errors=errors,
                    responses=responses,
                ),
                indent=2,
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
