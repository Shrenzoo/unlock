"""Layout, accessibility and rendering checks at desktop, laptop and phone sizes.

Screenshots are written for human review; the assertions cover what pixels and
the DOM can prove: no horizontal overflow, a workspace that fits its viewport,
named controls, visible keyboard focus and a WebGL scene that actually drew.
"""

from __future__ import annotations

import time

import pytest
from browser_harness import (
    VIEWPORTS,
    canvas_image,
    distinct_colours,
    new_page,
    report,
    shot,
)

pytestmark = pytest.mark.browser

UNNAMED = """() => [...document.querySelectorAll('button, a[href], [role="slider"], input')]
  .filter(e => e.offsetParent !== null && e.type !== 'file')
  .filter(e => !(e.getAttribute('aria-label') || e.textContent.trim() || e.labels?.[0]?.textContent.trim() || e.title))
  .map(e => e.outerHTML.slice(0, 120))"""
OVERFLOW = "() => document.scrollingElement.scrollWidth - innerWidth"
FOCUS = """() => { const e = document.activeElement; if (!e || e === document.body) return null;
  const s = getComputedStyle(e); return {tag: e.tagName, outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0, shadow: s.boxShadow !== 'none'} }"""


@pytest.fixture(scope="module")
def completed_run(stack):
    """One verified B02 redesign prepared through the API (the journey covers the UI path)."""
    revision = stack.latest_revision(stack.project("B02")["id"])
    status, started = stack.post(
        f"/v1/revisions/{revision['id']}/runs",
        dict(
            target_id="target",
            policy_id="planner_v1",
            constraint_hash=revision["constraint_hash"],
        ),
        headers={"Idempotency-Key": f"visual-baseline-{time.time()}"},
    )
    assert status == 202, started
    wait(stack, started["job_id"])
    status, redesign = stack.post(
        f"/v1/runs/{started['run_id']}/redesign",
        headers={"Idempotency-Key": f"visual-redesign-{time.time()}"},
    )
    assert status == 202, redesign
    wait(stack, redesign["job_id"])
    run = stack.get(f"/v1/runs/{started['run_id']}")
    assert run["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
    return run


def wait(stack, job_id, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stack.get(f"/v1/jobs/{job_id}")["state"] in (
            "completed",
            "failed",
            "cancelled",
        ):
            return
        time.sleep(0.5)
    raise TimeoutError(job_id)


@pytest.mark.parametrize("size", list(VIEWPORTS))
def test_pages_fit_and_name_their_controls(browser, stack, completed_run, size):
    context, page, monitor = new_page(browser, stack.api, size=VIEWPORTS[size])
    findings = {}

    page.goto(stack.web + "/")
    page.get_by_role("heading", level=1).wait_for()
    page.wait_for_load_state("networkidle")
    findings["landing_overflow_px"] = page.evaluate(OVERFLOW)
    findings["landing_unnamed"] = page.evaluate(UNNAMED)
    shot(page, f"visual-{size}-landing")

    page.goto(stack.web + "/projects")
    page.get_by_role("link", name="Open", exact=True).first.wait_for()
    findings["projects_overflow_px"] = page.evaluate(OVERFLOW)
    findings["projects_unnamed"] = page.evaluate(UNNAMED)
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    findings["projects_focus"] = page.evaluate(FOCUS)
    shot(page, f"visual-{size}-projects")

    pid = stack.project("B02")["id"]
    page.goto(f"{stack.web}/projects/{pid}?run={completed_run['id']}")
    page.get_by_test_id("run-outcome").wait_for(timeout=60_000)
    page.wait_for_timeout(1200)
    findings["workspace_overflow_px"] = page.evaluate(OVERFLOW)
    findings["workspace_document_height"] = page.evaluate(
        "() => [document.scrollingElement.scrollHeight, innerHeight]"
    )
    findings["workspace_unnamed"] = page.evaluate(UNNAMED)
    canvas = page.locator("canvas").first
    canvas.scroll_into_view_if_needed()
    findings["canvas_distinct_colours"] = distinct_colours(canvas_image(page))
    shot(page, f"visual-{size}-workspace-redesign")
    page.get_by_role("button", name="4 Compare").click()
    page.wait_for_timeout(1200)
    findings["compare_overflow_px"] = page.evaluate(OVERFLOW)
    shot(page, f"visual-{size}-workspace-compare")
    report.setdefault("visual", {})[size] = findings

    for key in ("landing", "projects", "workspace", "compare"):
        assert findings[f"{key}_overflow_px"] <= 1, (key, findings)
    for key in ("landing", "projects", "workspace"):
        assert findings[f"{key}_unnamed"] == [], (key, findings[f"{key}_unnamed"])
    focus = findings["projects_focus"]
    assert focus and (focus["outline"] or focus["shadow"]), (
        "keyboard focus must be visible"
    )
    assert findings["canvas_distinct_colours"] >= 40, "the CAD scene must render"
    if size != "mobile":
        height, viewport = findings["workspace_document_height"]
        assert height <= viewport + 1, "the desktop workspace fits its viewport"
    assert monitor.page_errors == []
    context.close()
