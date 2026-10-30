"""Explicit paid Meta acceptance tests. Never selected by ordinary pytest."""

import json
from pathlib import Path
import pytest

from unlock_engine.ai.config import load_config, live_tests_enabled
from unlock_engine.ai.controller import run_with_model
from unlock_engine.ai.provider import build_provider
from unlock_engine.ai.smoke import run_smoke
from unlock_engine.artifacts import atomic_write
from unlock_engine.fixtures import generate_fixture

pytestmark = pytest.mark.meta_live


@pytest.fixture(scope="module")
def live_config():
    config = load_config()
    if (
        config.provider != "meta"
        or not config.has_credentials
        or not live_tests_enabled()
    ):
        pytest.skip(
            "Live Meta verification requires AI_PROVIDER=meta, MODEL_API_KEY and RUN_META_LIVE_TESTS=1"
        )
    return config


def save(name, report):
    path = Path(".work/meta-live") / name
    atomic_write(path, json.dumps(report, indent=2, allow_nan=False).encode())


def test_live_meta_connectivity_native_tools_and_correlated_continuation(live_config):
    report = run_smoke(live_config)
    save("smoke.json", report)
    assert report["status"] == "passed", report
    assert all(r["model"] == "muse-spark-1.3" for r in report["requests"])


def test_live_meta_engineering_tool_call_cycle(live_config):
    """Two requests at most: Muse calls read-only inspect_assembly on B01."""
    from unlock_engine.ai.smoke import run_tool_smoke

    report = run_tool_smoke(live_config)
    save("tool-smoke.json", report)
    assert report["usage"]["requests_sent"] <= 2
    assert report["status"] == "passed", report["checks"]


def test_live_meta_real_engineering_fixture(live_config, tmp_path):
    source = generate_fixture(tmp_path / "B02", "B02")
    report = run_with_model(
        (source / "assembly.step").read_bytes(),
        json.loads((source / "manifest.json").read_text()),
        "target",
        build_provider(live_config),
        request_timeout_s=live_config.request_timeout_s,
        max_retries=live_config.max_retries,
        prices=live_config.prices,
        artifact_root=Path(".work/meta-live/artifacts"),
    )
    save("B02-run.json", report)
    assert report["live_model"] and report["model"]["model_id"] == "muse-spark-1.3"
    assert report["engineering_evidence"]["baseline"]["status"] == "no_path_supported"
    assert any(
        e.get("tool") == "construct_candidate" and e.get("status") == "ok"
        for e in report["events"]
    )
    assert report["engineering_evidence"]["verified"], (
        "Live model did not complete an independent engineering check"
    )
    assert report["outcome"] in (
        "VERIFIED_IMPROVEMENT_FOUND",
        "NO_VERIFIED_IMPROVEMENT",
    ), report["outcome"]
    # Negative outcomes are valid engineering results; the report preserves the actual evidence.
