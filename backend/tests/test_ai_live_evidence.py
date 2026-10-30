"""Recorded live B02 report (muse-spark-1.3, 2026-10-29) used as a fixture; no API calls.

These checks validate the saved evidence and the summary script. Passing them is
not new live inference.
"""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from unlock_engine.ai.report_schema import AIRunReport

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "live-b02"


@pytest.fixture(scope="module")
def report():
    return json.loads((EVIDENCE / "live_run.json").read_text())


@pytest.fixture(scope="module")
def summarize():
    path = Path(__file__).resolve().parents[1] / "scripts" / "summarize_ai_run.py"
    spec = importlib.util.spec_from_file_location("summarize_ai_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.summarize


@pytest.fixture(scope="module")
def summary(report, summarize):
    return summarize(report)


def test_recorded_report_matches_the_published_contract(report):
    assert AIRunReport.model_validate(report).model_dump(mode="json") == report
    assert report["live_model"] and report["provenance"] == "live_model"
    assert report["model"]["model_id"] == "muse-spark-1.3"


def test_verified_outcome_is_backed_by_complete_engineering_evidence(summary):
    assert summary["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
    (c,) = summary["candidates"]
    assert c["final_stage"] == "VERIFIED_IMPROVEMENT"
    mandatory = [x for x in c["static_checks"] if x["mandatory"]]
    assert len(mandatory) == 12 and all(x["result"] == "pass" for x in mandatory)
    assert [x["result"] for x in c["static_checks"] if not x["mandatory"]] == [
        "not_applicable"
    ]
    plan = c["revised_plan"]
    assert plan["status"] == "feasible" and plan["complete"]
    assert plan["replay"] == "passed" and plan["reverse"] == "passed"
    assert all(x["result"] == "pass" for x in plan["constraint_checks"])
    assert c["comparison"]["original_status"] == "no_path_supported"
    assert c["comparison"]["original_metrics"] is None  # no invented baseline count
    assert c["comparison"]["verified_improvement"] is True
    assert summary["model_final_message"]["authority"].startswith("none")


def test_recorded_tool_sequence_and_refusal_are_preserved(summary):
    assert [(t["tool"], t["status"]) for t in summary["tool_calls"]] == [
        ("inspect_blocker", "ok"),
        ("list_interventions", "ok"),
        ("construct_candidate", "rejected"),
        ("construct_candidate", "ok"),
        ("verify_candidate", "ok"),
        ("compare_candidates", "ok"),
    ]
    refused = summary["tool_calls"][2]
    assert refused["failure"] == "INVALID_PROPOSAL"
    assert all(
        e.startswith("ev_") for e in refused["arguments"]["proposal"]["evidence_ids"]
    )
    usage = summary["usage"]
    assert usage["provider_requests"] == len(summary["model_turns"]) == 6
    assert usage["source"] == "provider_reported" and usage["retries"] == 0
    assert "not account-verified" in summary["cost_estimate"]["price_source"]


def variant(report, **model):
    data = copy.deepcopy(report)
    data["model"] = dict(data["model"], **model)
    return data


@pytest.mark.parametrize(
    "model",
    [
        dict(
            provider="fireworks", model_id="accounts/fireworks/models/muse-spark-open"
        ),
        dict(provider="together", model_id="some-other-model"),
        dict(provider="meta", model_id="muse-spark-1.3-contributor"),
    ],
)
def test_cost_is_unavailable_without_a_matching_price(report, summarize, model):
    estimate = summarize(variant(report, **model))["cost_estimate"]
    assert estimate["estimated_usd"] is None
    assert model["model_id"] in estimate["reason"]


def test_cost_prefers_the_runs_configured_price_then_exact_list_price(
    report, summarize
):
    listed = summarize(report)["cost_estimate"]
    assert listed["estimated_usd"] == pytest.approx(0.029778)
    assert listed["basis"] == "public list price for meta/muse-spark-1.3"
    configured = copy.deepcopy(report)
    configured["model"]["provider"] = "fireworks"
    configured["usage"]["cost"] = dict(
        estimated_usd=0.5, price_source="operator tariff", price_retrieved_at="x"
    )
    estimate = summarize(configured)["cost_estimate"]
    assert estimate["estimated_usd"] == 0.5
    assert estimate["basis"] == "price table configured for the run"
    offline = dict(copy.deepcopy(report), live_model=False)
    assert summarize(offline)["cost_estimate"]["estimated_usd"] is None


def test_list_prices_match_only_the_exact_provider_and_model():
    from unlock_engine.ai.config import META_LIST_PRICES, list_prices_for

    assert list_prices_for("meta", "muse-spark-1.3") is META_LIST_PRICES
    assert list_prices_for("fireworks", "muse-spark-1.3") is None
    assert list_prices_for("meta", "muse-spark-1.3-contributor") is None
    assert list_prices_for(None, None) is None
