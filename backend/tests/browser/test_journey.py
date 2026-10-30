"""First-time-user acceptance on the real B02 fixture: landing to checked export.

Every visible engineering result is correlated with the coordinator's own records
(`/v1/...`); pixels are read from real WebGL screenshots; the downloaded package is
validated against its manifest and its revised STEP is independently reimported.
The decision policy is the labelled offline scripted policy (AI_PROVIDER=mock).
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile

import pytest

from browser_harness import (
    BACKEND,
    canvas_image,
    distinct_colours,
    image_difference,
    new_page,
    report,
    sha256,
    shot,
)

pytestmark = pytest.mark.browser

REQUIRED_FILES = {
    "original.step",
    "revised.step",
    "changed_bracket.step",
    "manifest.json",
    "template_parameters.json",
    "metrics.json",
    "paths.json",
    "verification.json",
    "roundtrip.json",
    "geometry_difference.json",
    "limitations.txt",
    "ai_run.json",
    "attribution.txt",
    "preview.json",
}


class Steps:
    """Wall-clock timings of user-visible steps, recorded in the evidence report."""

    def __init__(self):
        self.timings: dict[str, float] = {}

    def __call__(self, name):
        steps = self

        class _Timer:
            def __enter__(self):
                self.started = time.monotonic()

            def __exit__(self, *exc):
                steps.timings[name] = round(time.monotonic() - self.started, 2)

        return _Timer()


def no_page_overflow(page):
    return page.evaluate(
        "() => document.scrollingElement.scrollWidth <= innerWidth + 1"
    )


def rendered(page, index=0, minimum=40):
    """A settled WebGL render of real geometry: sized to its view, many distinct
    colours (not a blank clear), and identical across two consecutive frames."""
    previous = None
    for _ in range(60):
        sized = (
            page.locator("canvas")
            .nth(index)
            .evaluate(
                "c => Math.abs(c.getBoundingClientRect().width"
                " - c.closest('.vp__view').getBoundingClientRect().width) < 2"
            )
        )
        image = canvas_image(page, index)
        if sized and distinct_colours(image) >= minimum:
            if previous is not None and previous.size == image.size:
                if image_difference(previous, image) < 0.002:
                    return image
            previous = image
        page.wait_for_timeout(250)
    raise AssertionError(f"canvas {index} never settled on rendered geometry")


def drag(page, index, dx, dy):
    box = page.locator("canvas").nth(index).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=12)
    page.mouse.up()


def check_count(text: str, label: str) -> int:
    match = re.search(rf"(\d+)\s*{label}\b", text)
    assert match, f"no {label} count shown"
    return int(match.group(1))


def test_b02_first_time_user_journey(browser, stack, evidence_dir):
    context, page, monitor = new_page(browser, stack.api)
    steps = Steps()
    project = stack.project("B02")
    revision = stack.latest_revision(project["id"])
    components = [c["id"] for c in revision["manifest"]["components"]]
    target = next(
        c["id"] for c in revision["manifest"]["components"] if c["replaceable"]
    )
    evidence = report["correlation"]
    evidence.update(project_id=project["id"], revision_id=revision["id"], target=target)

    # A. Landing: loads, labels its illustration honestly, primary CTA opens B02.
    with steps("landing_load_s"):
        page.goto(stack.web + "/")
        page.get_by_role("heading", level=1).wait_for()
        page.wait_for_load_state("networkidle")
    assert page.get_by_text("Presentation geometry, not analysis output").count() >= 1
    assert no_page_overflow(page)
    report["measurements"]["landing_navigation"] = page.evaluate(
        "() => { const n = performance.getEntriesByType('navigation')[0];"
        " return {dom_content_loaded_ms: Math.round(n.domContentLoadedEventEnd),"
        " load_ms: Math.round(n.loadEventEnd)} }"
    )
    shot(page, "01-landing")
    page.get_by_role("link", name="Explore UNLOCK").click()
    page.wait_for_url(f"**/projects/{project['id']}")
    page.locator(f'[role="treeitem"][data-id="{target}"]').wait_for()
    page.get_by_role("link", name="Back to projects").click()

    # B. Projects: every row is the backend's, no duplicates, truthful readiness.
    with steps("projects_load_s"):
        page.wait_for_url("**/projects")
        page.get_by_role("link", name="Open", exact=True).first.wait_for()
    api_projects = stack.get("/v1/projects")
    rows = page.locator("tbody tr")
    assert rows.count() == len(api_projects) == len({p["id"] for p in api_projects})
    for p in api_projects:
        row = rows.filter(has_text=p["name"])
        assert row.count() == 1, p["name"]
        text = row.inner_text()
        assert p["fixture_code"] in text and str(p["occurrences"]) in text
        assert p["revision"][:12] in text
        assert ("Computed CAD" in text) == (p["status"] == "ready")
    assert page.locator('[data-connection="connected"]').count() == 1
    assert no_page_overflow(page)
    shot(page, "02-projects")

    # C. Assembly: real revision and inventory, backend BRep tessellation, metres.
    with steps("open_assembly_to_render_s"):
        rows.filter(has_text=project["name"]).get_by_role("link", name="Open").click()
        page.locator(f'[role="treeitem"][data-id="{target}"]').wait_for()
        original = rendered(page)
    assert page.locator(".topbar__rev").inner_text() == revision["label"]
    tree_ids = page.locator('[role="treeitem"]').evaluate_all(
        "items => items.map(i => i.dataset.id)"
    )
    assert sorted(tree_ids) == sorted(components)
    viewer = page.locator('[data-geometry-source="backend-brep"]')
    assert viewer.get_attribute("data-preview-id") == revision["preview_artifact_id"]
    preview = json.loads(stack.raw(f"/v1/artifacts/{revision['preview_artifact_id']}"))
    assert preview["units"] == "m" and preview["scale_already_applied"] is True
    assert sorted(c["occurrence_id"] for c in preview["components"]) == sorted(
        components
    )
    frame = page.locator(".vp__frame").inner_text()
    assert f"{preview['triangle_count']} triangles" in frame
    assert any(
        c["path"] == f"/v1/artifacts/{revision['preview_artifact_id']}"
        and c["status"] == 200
        for c in monitor.api_calls
    ), "the viewport must load the backend tessellation"
    shot(page, "03-original-assembly")

    # Camera: orbit and zoom change the render; Reset restores the framing.
    drag(page, 0, 160, 60)
    page.wait_for_timeout(200)
    orbited = canvas_image(page)
    assert image_difference(original, orbited) > 0.05
    page.locator("canvas").first.hover()
    page.mouse.wheel(0, -400)
    page.wait_for_timeout(200)
    assert image_difference(orbited, canvas_image(page)) > 0.05
    page.get_by_role("button", name="Reset").click()
    page.mouse.move(2, 2)  # a hovered part is tinted; compare framing, not hover
    page.wait_for_timeout(300)
    assert image_difference(original, canvas_image(page)) < 0.02

    # D. Selection highlights; a different selection leaves no stale target.
    item = page.locator(f'[role="treeitem"][data-id="{target}"]')
    item.click()
    assert item.get_attribute("aria-selected") == "true"
    page.wait_for_timeout(200)
    selected = canvas_image(page)
    assert image_difference(original, selected) > 0.001, "selection must be highlighted"
    page.get_by_role("button", name="Set as repair target").click()
    assert target in page.locator(".topbar__target").inner_text()
    other = next(c for c in components if c != target)
    page.locator(f'[role="treeitem"][data-id="{other}"]').click()
    assert target in page.locator(".topbar__target").inner_text()
    item.click()
    shot(page, "04-selected-target")

    # E. Baseline: the request carries the intended occurrence; results are the backend's.
    page.get_by_role("button", name=f"Analyze removal of {target}").click()
    t0 = time.monotonic()
    with page.expect_response(
        lambda r: r.request.method == "POST"
        and re.search(r"/v1/revisions/[^/]+/runs$", r.url) is not None
    ) as started:
        page.get_by_role("button", name="Run baseline analysis").click()
    steps.timings["baseline_request_s"] = round(time.monotonic() - t0, 2)
    body = started.value.request.post_data_json
    assert body["target_id"] == target
    assert body["constraint_hash"] == revision["constraint_hash"]
    run_id = started.value.json()["run_id"]
    assert page.get_by_text("No path within supported operations").count() == 0
    page.get_by_role("button", name="Explore a redesign").wait_for(timeout=180_000)
    steps.timings["baseline_completion_s"] = round(time.monotonic() - t0, 2)
    assert f"run={run_id}" in page.url
    run = stack.get(f"/v1/runs/{run_id}")
    evidence["run_id"] = run_id
    assert run["target_id"] == target and run["revision_id"] == revision["id"]
    assert (
        run["baseline"]["status"] == "no_path_supported" and run["baseline"]["complete"]
    )
    assert page.get_by_text("No path within supported operations").count() == 1
    blocks = [r for r in run["baseline"]["rejections"] if not r.get("diagnostic")]
    geometric = [
        r for r in blocks if r["category"] == "CONFIRMED_GEOMETRIC_OBSTRUCTION"
    ]
    assert geometric, "B02 is blocked by a confirmed obstruction"
    for r in geometric:
        assert page.get_by_text(r["id"][:12], exact=True).count() == 1
    messages = page.locator(".events__msg").all_inner_texts()
    assert any("no_path_supported" in m for m in messages)
    page.get_by_text(geometric[0]["id"][:12], exact=True).click()
    page.wait_for_timeout(300)
    assert image_difference(selected, canvas_image(page)) > 0.001
    shot(page, "05-confirmed-obstruction")

    # F. Redesign with the labelled offline policy; nothing shown before checks finish.
    page.get_by_role("button", name="Explore a redesign").click()
    policy = page.get_by_test_id("decision-policy")
    assert policy.get_attribute("data-policy") == "offline"
    assert "Offline scripted policy, no model inference" in policy.inner_text()
    t0 = time.monotonic()
    with page.expect_response(
        lambda r: r.request.method == "POST"
        and r.url.endswith(f"/v1/runs/{run_id}/redesign")
    ) as requested:
        page.get_by_role("button", name="Request redesign").click()
    redesign_job = requested.value.json()["job_id"]
    assert page.get_by_test_id("run-outcome").count() == 0
    page.get_by_test_id("run-outcome").wait_for(timeout=300_000)
    steps.timings["redesign_completion_s"] = round(time.monotonic() - t0, 2)
    run = stack.get(f"/v1/runs/{run_id}")
    assert stack.get(f"/v1/jobs/{redesign_job}")["state"] == "completed"
    outcome = page.get_by_test_id("run-outcome")
    assert outcome.get_attribute("data-outcome") == run["outcome"]
    assert run["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
    assert outcome.get_attribute("data-run-id") == run_id
    assert run["model"]["live"] is False and run["model"]["provider"] == "fake"
    assert (
        "offline scripted inference"
        in page.get_by_test_id("run-provenance").inner_text()
    )
    assert "Offline scripted policy" in policy.inner_text()
    cards = page.locator(".cands button.cand")
    assert cards.count() == len(run["candidates"])
    for card, c in zip(cards.all(), run["candidates"]):
        assert f"cand--{c['state']}" in card.get_attribute("class")
        assert ("Passed" if c["state"] == "checked" else "Failed") in card.inner_text()
    verified = next(c for c in run["candidates"] if c["verified_improvement"])
    rejected = [c for c in run["candidates"] if c["state"] != "checked"]
    assert run["selected_candidate_id"] == verified["id"]
    checks = verified["verification"]["checks"]
    assert all(k["result"] == "pass" for k in checks if k.get("mandatory", True))
    evidence.update(
        candidates=[
            dict(id=c["id"], state=c["state"], parameters=c["proposal"]["parameters"])
            for c in run["candidates"]
        ],
        verified_candidate=verified["id"],
        outcome=run["outcome"],
    )
    shot(page, "06-redesign-result")

    # Rejected candidates cannot even reach review: Compare and Export stay closed.
    if rejected:
        cards.nth(run["candidates"].index(rejected[0])).click()
        assert page.get_by_role("button", name="Compare with the original").count() == 0
        for step in ("4 Compare", "5 Export"):
            gate = page.get_by_role("button", name=step)
            assert gate.is_disabled()
            assert (
                gate.get_attribute("title")
                == "Choose a candidate whose checks completed"
            )
        cards.nth(run["candidates"].index(verified)).click()

    # G. Comparison: both models render; the revised one is the constructed candidate.
    t0 = time.monotonic()
    page.get_by_role("button", name="Compare with the original").click()
    page.locator("canvas").nth(1).wait_for()
    left, right = rendered(page, 0), rendered(page, 1)
    steps.timings["compare_render_s"] = round(time.monotonic() - t0, 2)
    assert page.locator("canvas").count() == 2
    assert image_difference(left, right) > 0.003, "the modified bracket must be visible"
    assert any(
        c["path"] == f"/v1/artifacts/{verified['preview_artifact_id']}"
        and c["status"] == 200
        for c in monitor.api_calls
    )
    text = page.get_by_role("complementary", name="Evidence").inner_text()
    assert check_count(text, "pass") == sum(k["result"] == "pass" for k in checks)
    assert check_count(text, "fail") == 0 and check_count(text, "unknown") == 0
    assert "no_path_supported" in text and "feasible" in text
    assert "manufacturing" in text.lower(), "release scope must stay explicit"
    drag(page, 0, 120, 0)
    page.wait_for_timeout(250)
    assert image_difference(right, canvas_image(page, 1)) > 0.05, (
        "views are synchronised"
    )
    page.get_by_role("button", name="Reset").click()
    page.wait_for_timeout(300)
    shot(page, "07-comparison")

    # H. Playback along the verified route: bounds, motion, reset.
    slider = page.get_by_role("slider", name="Checked route position")
    planned = verified["revised_plan"]["steps"]
    assert float(slider.get_attribute("max")) == len(planned) == 1
    assert planned[0]["component_id"] == target and planned[0]["axis"] == "Z+"
    frames = []
    for position in ("0", "0.5", "1"):
        slider.fill(position)
        page.wait_for_timeout(250)
        frames.append(canvas_image(page, 1))
    assert image_difference(frames[0], frames[1]) > 0.002
    assert image_difference(frames[1], frames[2]) > 0.002
    # Keyboard bounds: the slider stops at the planned route's start and end.
    slider.focus()
    page.keyboard.press("Home")
    page.keyboard.press("ArrowLeft")
    assert float(slider.input_value()) == 0.0, "the route cannot start before 0"
    page.keyboard.press("End")
    for _ in range(5):
        page.keyboard.press("ArrowRight")
    assert float(slider.input_value()) == 1.0, "the route cannot be overrun"
    page.mouse.move(2, 2)
    page.wait_for_timeout(250)
    assert image_difference(frames[2], canvas_image(page, 1)) < 0.02, (
        "end pose is stable"
    )
    shot(page, "08-verified-route")
    page.get_by_role("button", name="Reset").click()
    assert float(slider.input_value()) == 0.0
    assert verified["revised_plan"]["replay"]["status"] == "passed"
    assert verified["revised_plan"]["reverse"]["status"] == "passed"

    # I. Acceptance records a real backend decision for the eligible candidate only.
    accept = page.get_by_role("button", name="Accept for export", exact=True)
    assert accept.is_enabled()
    with page.expect_response(
        lambda r: r.request.method == "POST"
        and r.url.endswith(f"/v1/candidates/{verified['id']}/decision")
    ) as decided:
        accept.click()
    assert decided.value.status == 200
    decision = decided.value.request.post_data_json
    assert decision["decision"] == "accept"
    assert decision["input_hash"] == verified["input_hash"]
    assert decided.value.json()["review_event_id"]
    page.get_by_text("Accepted for checked export.", exact=False).wait_for()
    reviewed = {c["id"]: c for c in stack.get(f"/v1/runs/{run_id}")["candidates"]}
    assert reviewed[verified["id"]].get("review_decision") == "accept"
    assert all(reviewed[c["id"]].get("review_decision") != "accept" for c in rejected)
    if rejected:
        status, _ = stack.post(f"/v1/candidates/{rejected[0]['id']}/exports")
        assert status >= 400, "a rejected candidate must not export"

    # J. Checked export: built by the backend, downloaded by the browser, validated.
    page.get_by_role("button", name="5 Export").click()
    t0 = time.monotonic()
    page.get_by_role("button", name="Create checked package").click()
    link = page.get_by_test_id("export-download")
    link.wait_for(timeout=300_000)
    steps.timings["export_completion_s"] = round(time.monotonic() - t0, 2)
    run = stack.get(f"/v1/runs/{run_id}")
    assert run["export"]["review_candidate_id"] == verified["id"]
    assert run["export"]["status"] == "full_assembly"
    assert run["export"]["roundtrip_status"] == "passed"
    assert link.get_attribute("data-artifact-id") == run["export"]["artifact_id"]
    with page.expect_download() as downloading:
        link.click()
    saved = evidence_dir / "checked_export.zip"
    downloading.value.save_as(saved)
    data = saved.read_bytes()
    assert sha256(data) == run["export"]["artifact_id"]
    assert data == stack.raw(f"/v1/artifacts/{run['export']['artifact_id']}")
    shot(page, "09-checked-export")
    evidence["package"] = validate_package(data, run, verified, revision)

    # Whole journey: no console errors, failed requests or HTTP errors; one redesign.
    # The download link's navigation ends as ERR_ABORTED once it becomes a download;
    # its bytes were verified above, so it is the one named exception.
    download_url = (
        f"{stack.api}/v1/artifacts/{run['export']['artifact_id']} net::ERR_ABORTED"
    )
    problems = monitor.problems(allow_failed=(download_url,))
    assert problems == dict(console=[], page=[], failed=[], http=[]), problems
    report["measurements"]["superseded_fetches"] = monitor.superseded
    assert sum(1 for c in monitor.api_calls if c["path"].endswith("/redesign")) == 1
    report["measurements"]["journey_steps_s"] = steps.timings
    ai = json.loads(stack.raw(f"/v1/artifacts/{run['ai_report_artifact_id']}"))
    report["measurements"]["redesign_breakdown"] = dict(
        run_total_s=ai["timings"]["total_s"],
        stage_a_ms=ai["timings"]["stage_a"],
        native_geometry_ms=round(ai["usage"]["geometry_ms"], 1),
        decision_policy_ms=round(ai["usage"]["model_latency_ms"], 1),
        policy="offline scripted: no model inference, no network",
    )
    report["measurements"]["api_calls"] = len(monitor.api_calls)
    context.close()


def validate_package(data: bytes, run: dict, candidate: dict, revision: dict) -> dict:
    """The ZIP is complete, self-consistent, matches the candidate and reimports."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.testzip() is None
    bundle = json.loads(archive.read("bundle.json"))
    names = set(archive.namelist())
    assert names == set(bundle["files"]) | {"bundle.json"}, "no unlisted files"
    assert REQUIRED_FILES <= names
    for name, digest in bundle["files"].items():
        assert sha256(archive.read(name)) == digest, name
    assert (
        bundle["status"] == "full_assembly" and bundle["roundtrip_status"] == "passed"
    )
    assert bundle["candidate_id"] == run["export"]["candidate_id"]

    # One candidate identity across every record; original and revised revisions named.
    verification = json.loads(archive.read("verification.json"))
    parameters = json.loads(archive.read("template_parameters.json"))
    paths = json.loads(archive.read("paths.json"))
    assert verification["status"] == "passed"
    assert verification["candidate_id"] == bundle["candidate_id"] == parameters["id"]
    assert paths["revision_id"] == bundle["candidate_id"]
    assert verification["candidate_revision_id"] == parameters["geometry_hash"]
    assert verification["original_revision_id"] == revision["id"]
    assert verification["constraint_hash"] == revision["constraint_hash"]
    assert paths["status"] == "feasible" and paths["replacement_verified"]

    def route(steps):
        return [(s["component_id"], s["axis"], s["distance_mm"]) for s in steps]

    assert route(paths["steps"]) == route(candidate["revised_plan"]["steps"])
    flat = json.dumps(parameters)
    for name, value in candidate["proposal"]["parameters"].items():
        assert re.search(rf'"{name}": {float(value)}\b|"{name}": {value}\b', flat), name
    ai_run = json.loads(archive.read("ai_run.json"))
    assert ai_run["live_model"] is False
    assert ai_run["provenance"] == "offline_fake_provider"
    assert json.loads(archive.read("roundtrip.json"))["status"] == "passed"
    assert "not assessed" in archive.read("limitations.txt").decode().lower()

    # No credentials, local paths or unrelated files travel with the package.
    from dotenv import dotenv_values

    key = (dotenv_values(BACKEND / ".env").get("MODEL_API_KEY") or "").strip()
    for name in names:
        blob = archive.read(name)
        for needle in filter(
            None, [key.encode(), b"MODEL_API_KEY", b"/Users/", b"Bearer "]
        ):
            assert needle not in blob, f"{needle[:12]!r} found in {name}"

    # Independent STEP round trip through the production import worker.
    from unlock_engine.package import load_files
    from unlock_engine.worker import isolated_import

    original_manifest = json.loads(json.dumps(revision["manifest"]))
    for c in original_manifest["components"]:
        c.pop("bounds_mm", None)
    revised = isolated_import(
        load_files(
            {
                "assembly.step": archive.read("revised.step"),
                "manifest.json": archive.read("manifest.json"),
            }
        )
    )
    before = isolated_import(
        load_files(
            {
                "assembly.step": archive.read("original.step"),
                "manifest.json": json.dumps(original_manifest).encode(),
            }
        )
    )
    assert all(r["ok"] for r in revised["readiness"])
    assert all(r["ok"] for r in before["readiness"])
    assert sorted(c["id"] for c in revised["components"]) == sorted(
        c["id"] for c in before["components"]
    )
    changed = candidate["diff"]["changed_component_id"]

    def volume(inventory, component):
        return next(
            c["volume_mm3"] for c in inventory["components"] if c["id"] == component
        )

    removed = json.loads(archive.read("geometry_difference.json"))["removed_volume_mm3"]
    measured = volume(before, changed) - volume(revised, changed)
    assert abs(measured - removed) < 1e-3 * max(1.0, removed)
    for c in before["components"]:
        if c["id"] != changed:
            assert abs(c["volume_mm3"] - volume(revised, c["id"])) < 1e-6 * max(
                1.0, c["volume_mm3"]
            ), c["id"]
    return dict(
        sha256=sha256(data),
        files=sorted(names),
        status=bundle["status"],
        roundtrip=bundle["roundtrip_status"],
        candidate_revision=bundle["candidate_id"],
        independent_reimport=dict(
            occurrences=len(revised["components"]),
            changed_component=changed,
            removed_volume_mm3=round(removed, 3),
            measured_volume_change_mm3=round(measured, 3),
        ),
    )
