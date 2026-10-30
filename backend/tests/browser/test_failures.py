"""Failure, refusal and recovery behaviour on real services.

Faults are real: a bundle pointed at a closed port, a backend configured for Meta
without credentials (no request can leave the machine), user cancellation, and a
bounded interval in which the browser's requests to the coordinator are aborted.
"""

from __future__ import annotations

import time

import pytest
from browser_harness import new_page, report, shot, start_stack

pytestmark = pytest.mark.browser
TARGET = "target"


def open_b02(page, stack):
    page.goto(f"{stack.web}/projects/{stack.project('B02')['id']}")
    page.locator(f'[role="treeitem"][data-id="{TARGET}"]').click()
    page.get_by_role("button", name="Set as repair target").click()
    page.get_by_role("button", name=f"Analyze removal of {TARGET}").click()


def run_baseline(page):
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/runs")
    ) as started:
        page.get_by_role("button", name="Run baseline analysis").click()
    page.get_by_role("button", name="Explore a redesign").wait_for(timeout=180_000)
    return started.value.json()["run_id"]


def request_redesign(page, run_id):
    page.get_by_role("button", name="Explore a redesign").click()
    with page.expect_response(
        lambda r: r.request.method == "POST"
        and r.url.endswith(f"/runs/{run_id}/redesign")
    ) as requested:
        page.get_by_role("button", name="Request redesign").click()
    return requested.value.json()["job_id"]


def wait_job(stack, job_id, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = stack.get(f"/v1/jobs/{job_id}")
        if job["state"] in ("completed", "failed", "cancelled", "interrupted"):
            return job
        time.sleep(0.5)
    raise TimeoutError(job_id)


def test_missing_backend_is_reported_and_never_replaced_by_examples(
    browser, tmp_path_factory
):
    offline = start_stack(
        "missing-backend", 8199, 5196, tmp_path_factory.mktemp("missing"), backend=False
    )
    try:
        context, page, monitor = new_page(browser, offline.api)
        page.goto(offline.web + "/projects")
        alert = page.get_by_test_id("connection-error")
        alert.wait_for(timeout=30_000)
        assert "Cannot reach the UNLOCK engineering service" in alert.inner_text()
        assert offline.api in alert.inner_text()
        assert page.locator('[data-connection="unreachable"]').count() == 1
        assert (
            page.get_by_text(
                "No projects: the engineering service is not reachable."
            ).count()
            == 1
        )
        assert page.get_by_role("link", name="Open", exact=True).count() == 0
        assert page.get_by_text("Illustrative").count() == 0
        shot(page, "failure-missing-backend-projects")
        page.goto(offline.web + "/projects/fixture_B02")
        page.get_by_role("heading", name="Project unavailable").wait_for()
        assert (
            "Cannot reach the UNLOCK engineering service"
            in page.locator("main").inner_text()
        )
        shot(page, "failure-missing-backend-workspace")
        assert monitor.page_errors == []
        assert all("8199" in f for f in monitor.failed_requests)
        context.close()
    finally:
        offline.stop()


def test_unavailable_model_is_reported_honestly(browser, tmp_path_factory):
    """AI_PROVIDER=meta with no credentials: the adapter refuses before sending."""
    meta = start_stack(
        "meta-no-key", 8102, 5195, tmp_path_factory.mktemp("meta"), provider="meta"
    )
    try:
        health = meta.get("/health")["provider"]
        assert health["provider"] == "meta" and health["credentials"] == "missing"
        context, page, monitor = new_page(browser, meta.api)
        open_b02(page, meta)
        run_id = run_baseline(page)
        page.get_by_role("button", name="Explore a redesign").click()
        policy = page.get_by_test_id("decision-policy")
        assert policy.get_attribute("data-policy") == "unavailable"
        assert "credentials missing" in policy.inner_text()
        job_id = request_redesign_without_explore(page, run_id)
        job = wait_job(meta, job_id)
        run = meta.get(f"/v1/runs/{run_id}")
        assert run["outcome"] == "MODEL_UNAVAILABLE", (job["state"], run["outcome"])
        assert not run["candidates"]
        page.get_by_test_id("run-outcome").wait_for(timeout=60_000)
        assert (
            page.get_by_test_id("run-outcome").get_attribute("data-outcome")
            == "MODEL_UNAVAILABLE"
        )
        text = policy.inner_text()
        assert "unavailable" in text and "live inference" not in text.replace(
            "credentials", ""
        )
        assert page.get_by_role("button", name="4 Compare").is_disabled()
        assert page.get_by_text("VERIFIED IMPROVEMENT FOUND").count() == 0
        shot(page, "failure-model-unavailable")
        report["correlation"]["model_unavailable"] = dict(
            run_id=run_id, job_state=job["state"], outcome=run["outcome"]
        )
        context.close()
    finally:
        meta.stop()


def request_redesign_without_explore(page, run_id):
    with page.expect_response(
        lambda r: r.request.method == "POST"
        and r.url.endswith(f"/runs/{run_id}/redesign")
    ) as requested:
        page.get_by_role("button", name="Request redesign").click()
    return requested.value.json()["job_id"]


def test_cancelled_redesign_leaves_nothing_accepted(browser, stack):
    context, page, monitor = new_page(browser, stack.api)
    open_b02(page, stack)
    run_id = run_baseline(page)
    job_id = request_redesign(page, run_id)
    page.get_by_role("button", name="Cancel job").click()
    page.get_by_text("Cancellation requested.", exact=False).wait_for()
    job = wait_job(stack, job_id)
    assert job["state"] == "cancelled", job["state"]
    run = stack.get(f"/v1/runs/{run_id}")
    assert all(c.get("review_decision") != "accept" for c in run["candidates"])
    assert page.get_by_test_id("run-outcome").count() == 0
    assert page.get_by_role("button", name="Request redesign").is_enabled()
    assert page.get_by_role("button", name="5 Export").is_disabled()
    shot(page, "failure-cancelled-redesign")
    report["correlation"]["cancelled"] = dict(
        run_id=run_id, job_id=job_id, state=job["state"]
    )
    context.close()


def test_offline_interval_mid_job_completes_without_duplicate_work(browser, stack):
    context, page, monitor = new_page(browser, stack.api)
    open_b02(page, stack)
    run_id = run_baseline(page)
    job_id = request_redesign(page, run_id)
    page.wait_for_timeout(1500)
    # The browser goes offline for 4 s mid-job; a request made meanwhile must fail.
    # Chromium keeps an already-open loopback event stream alive, so severing the
    # stream itself is not exercised here (SSE resume is covered in test_api).
    context.set_offline(True)
    during = page.evaluate(
        f"() => fetch('{stack.api}/health').then(() => 'reached', () => 'failed')"
    )
    page.wait_for_timeout(4000)
    context.set_offline(False)
    assert during == "failed", "the outage must be real"
    page.get_by_test_id("run-outcome").wait_for(timeout=300_000)
    run = stack.get(f"/v1/runs/{run_id}")
    assert stack.get(f"/v1/jobs/{job_id}")["state"] == "completed"
    assert (
        page.get_by_test_id("run-outcome").get_attribute("data-outcome")
        == run["outcome"]
    )
    redesigns = [
        c
        for c in monitor.api_calls
        if c["method"] == "POST" and c["path"].endswith("/redesign")
    ]
    assert len(redesigns) == 1, "an interruption must not resubmit engineering work"
    report["correlation"]["interrupted"] = dict(
        run_id=run_id,
        outcome=run["outcome"],
        aborted_requests=len(monitor.failed_requests),
    )
    context.close()


def test_reload_restores_the_persisted_run_and_export_needs_acceptance(browser, stack):
    context, page, monitor = new_page(browser, stack.api)
    open_b02(page, stack)
    run_id = run_baseline(page)
    request_redesign(page, run_id)
    page.get_by_test_id("run-outcome").wait_for(timeout=300_000)
    run = stack.get(f"/v1/runs/{run_id}")
    verified = next(c for c in run["candidates"] if c["verified_improvement"])

    # Not yet accepted: the UI offers no export and the API refuses one.
    page.get_by_role("button", name="5 Export").click()
    assert page.get_by_role("button", name="Create checked package").is_disabled()
    assert (
        "Accept the checked candidate first" in page.locator("#export-why").inner_text()
    )
    status, body = stack.post(
        f"/v1/candidates/{verified['id']}/exports",
        headers={"Idempotency-Key": f"e2e-{run_id}"},
    )
    assert status >= 400, body

    calls_before = len(monitor.api_calls)
    page.reload()
    page.get_by_test_id("run-outcome").wait_for(timeout=30_000)
    after_reload = monitor.api_calls[calls_before:]
    assert not [c for c in after_reload if c["method"] == "POST"], (
        "a reload re-executes nothing"
    )
    assert page.get_by_test_id("run-outcome").get_attribute("data-run-id") == run_id
    assert TARGET in page.locator(".topbar__target").inner_text()
    assert page.locator(".cands button.cand").count() == len(run["candidates"])
    shot(page, "recovery-after-reload")

    # A run that belongs to another revision is never applied to this workspace.
    b01 = stack.latest_revision(stack.project("B01")["id"])
    foreign = stack.post(
        f"/v1/revisions/{b01['id']}/runs",
        dict(
            target_id="target",
            policy_id="planner_v1",
            constraint_hash=b01["constraint_hash"],
        ),
        headers={"Idempotency-Key": f"e2e-foreign-{run_id}"},
    )
    assert foreign[0] == 202, foreign
    page.goto(
        f"{stack.web}/projects/{stack.project('B02')['id']}?run={foreign[1]['run_id']}"
    )
    page.locator(f'[role="treeitem"][data-id="{TARGET}"]').wait_for()
    page.wait_for_timeout(1500)
    assert page.locator(".topbar__target").inner_text().strip() == "No target"
    assert page.get_by_test_id("run-outcome").count() == 0
    context.close()
