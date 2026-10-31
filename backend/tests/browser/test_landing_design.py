"""Opt-in acceptance for the reference design; no backend or CAD job is started."""

import io
import os
from urllib.parse import urlsplit

from PIL import Image, ImageChops
import pytest
from playwright.sync_api import expect

from browser_harness import report, shot

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        not os.environ.get("UNLOCK_LANDING_WEB"),
        reason="an explicit local or production landing URL is required",
    ),
]
SIZES = [(1774, 887), (1440, 1000), (1024, 768), (390, 844), (360, 640)]
NAMES = ["reference", "desktop", "laptop", "mobile", "small-mobile"]


def changed_pixels(before, after):
    a, b = (Image.open(io.BytesIO(data)).convert("RGB") for data in (before, after))
    histogram = ImageChops.difference(a, b).convert("L").histogram()
    return sum(histogram[8:]) / (a.width * a.height)


def frame_sample(page, scroll=False):
    return page.evaluate(
        """async (scroll) => {
          const gaps = []; let last;
          for (let i = 0; i < 90; i++) {
            const now = await new Promise(requestAnimationFrame);
            if (last) gaps.push(now-last); last=now;
            if (scroll) window.scrollBy(0, 3);
          }
          gaps.sort((a,b)=>a-b);
          return {samples:gaps.length, median_ms:gaps[Math.floor(gaps.length*.5)],
            p95_ms:gaps[Math.floor(gaps.length*.95)],
            over_50ms:gaps.filter(n=>n>50).length};
        }""",
        scroll,
    )


@pytest.fixture(scope="module")
def landing_url():
    url = os.environ["UNLOCK_LANDING_WEB"].rstrip("/")
    parsed = urlsplit(url)
    assert not parsed.username and not parsed.password
    assert parsed.scheme == "https" or (
        parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")
    )
    report["landing_origin"] = url
    return url


@pytest.mark.parametrize("size,name", zip(SIZES, NAMES, strict=True), ids=NAMES)
def test_spacious_reference_motion_and_navigation(browser, landing_url, size, name):
    w, h = size
    context = browser.new_context(
        viewport=dict(width=w, height=h), reduced_motion="no-preference"
    )
    page = context.new_page()
    page.set_default_timeout(60_000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(landing_url, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(2200)
        assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth + 1")
        hero = page.locator(".hero").bounding_box()
        copy = page.locator(".hero__copy").bounding_box()
        model = page.locator(".hero__stage").bounding_box()
        caption = page.get_by_role(
            "complementary", name="Drawing title block"
        ).bounding_box()
        assert all((hero, copy, model, caption))
        assert caption["x"] >= 0 and caption["x"] + caption["width"] <= w + 1
        assert caption["y"] + caption["height"] <= hero["height"] + 1
        if w > 900:
            assert hero["height"] >= max(820, h) - 1
            assert copy["x"] + copy["width"] <= model["x"] + 1
        else:
            assert copy["y"] + copy["height"] <= model["y"] + 1
        shot(page, name + "-spacious-hero")

        # No cursor event precedes this check. It measures visible idle movement.
        before = page.screenshot()
        idle_frames = frame_sample(page)
        after = page.screenshot()
        fraction = changed_pixels(before, after)
        assert fraction > 0.002, "the gradient must visibly move without hovering"
        page.mouse.move(w * 0.8, h * 0.3)
        page.wait_for_timeout(350)
        x1 = page.locator(".noise-field").evaluate(
            "e => parseFloat(e.style.getPropertyValue('--field-x'))"
        )
        page.mouse.move(w * 0.2, h * 0.7, steps=8)
        page.wait_for_timeout(600)
        x2 = page.locator(".noise-field").evaluate(
            "e => parseFloat(e.style.getPropertyValue('--field-x'))"
        )
        assert x1 > x2
        page.get_by_role("button", name="Fan module", exact=True).click()
        expect(
            page.get_by_role("button", name="Fan module", exact=True)
        ).to_have_attribute("aria-pressed", "true")
        page.get_by_role("button", name="Fan module", exact=True).click()
        if w > 900:
            page.evaluate(
                "() => scrollTo(0, document.querySelector('#story').offsetTop-innerHeight*.55)"
            )
            page.wait_for_timeout(500)
            seam = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
            assert sum(seam.getpixel((12, 100))) > 600
            assert sum(seam.getpixel((12, h - 12))) < 180
            shot(page, name + "-continuous-section-transition")
        scenes = []
        scroll_frames = None
        for i, progress in enumerate((0.04, 0.23, 0.48, 0.70, 0.93)):
            page.evaluate(
                "p => { const e=document.querySelector('#story'); scrollTo(0,e.offsetTop+(e.offsetHeight-innerHeight)*p) }",
                progress,
            )
            page.wait_for_timeout(1050)
            view = page.locator(".story__canvas").bounding_box()
            text = page.locator(".story__copy").bounding_box()
            rail = page.get_by_role("navigation", name="Story steps").bounding_box()
            assert all((view, text, rail))
            assert rail["y"] >= 63 and rail["y"] + rail["height"] <= h + 1
            if w > 900:
                assert text["x"] + text["width"] <= view["x"] + 1
            else:
                assert view["y"] + view["height"] <= text["y"] + 1
            assert page.evaluate(
                "document.scrollingElement.scrollWidth <= innerWidth+1"
            )
            scenes.append(page.locator(".story__panel.is-active h2").inner_text())
            shot(page, name + f"-story-{i + 1}")
            if name == "desktop" and i == 0:
                scroll_frames = frame_sample(page, scroll=True)
        assert len(set(scenes)) == 5
        page.get_by_role("button", name="2 Failed part", exact=True).click()
        expect(page.locator(".story__panel.is-active h2")).to_have_text(
            "One failed part. An entire product in the way."
        )
        assert not errors
        report.setdefault("landing_design", {})[name] = dict(
            viewport=list(size),
            hero_height=hero["height"],
            idle_changed_fraction=fraction,
            idle_frame_sample=idle_frames,
            scroll_frame_sample=scroll_frames,
            scenes=scenes,
            part_and_step_controls=True,
            page_errors=errors,
        )
    finally:
        context.close()


def test_live_reduced_motion_and_webgl_fallback(browser, landing_url):
    context = browser.new_context(reduced_motion="no-preference")
    page = context.new_page()
    try:
        page.goto(landing_url, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(2200)
        page.emulate_media(reduced_motion="reduce")
        page.wait_for_timeout(400)
        assert (
            page.locator(".noise-field__cloud").first.evaluate(
                "e => getComputedStyle(e).animationName"
            )
            == "none"
        )
        before = page.screenshot()
        page.wait_for_timeout(750)
        assert changed_pixels(before, page.screenshot()) < 0.001
        page.emulate_media(reduced_motion="no-preference")
        page.wait_for_timeout(250)
        assert (
            page.locator(".noise-field__cloud").first.evaluate(
                "e => getComputedStyle(e).animationName"
            )
            == "field-circulation"
        )
    finally:
        context.close()
    context = browser.new_context()
    page = context.new_page()
    try:
        page.add_init_script(
            "const original=HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext=function(type,...args){ return /webgl/.test(type)?null:original.call(this,type,...args) }"
        )
        page.goto(landing_url, wait_until="networkidle", timeout=90_000)
        expect(
            page.get_by_text(
                "3D preview unavailable in this browser. The drawing shows the same module."
            )
        ).to_be_visible()
        report["landing_accessibility"] = dict(
            live_reduced_motion=True, webgl_fallback=True
        )
    finally:
        context.close()
