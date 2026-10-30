"""Derive a compact engineering record from an AIRunReport (unlock.ai_run.v1).

Everything is copied from the report; nothing is recomputed except the list-price
cost estimate, which is labelled as such. Private model reasoning is never part
of a report, so it cannot appear here.

    python scripts/summarize_ai_run.py RUN.json --selectors A.json B.json --output OUT.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from unlock_engine.ai.config import list_prices_for
from unlock_engine.ai.controller import estimate_cost
from unlock_engine.ai.toolbox import Counters
from unlock_engine.contracts import digest


def checks(report: dict, candidate_id: str | None) -> list[dict]:
    verified = report["engineering_evidence"].get("verified", {}).get(candidate_id)
    if not verified:
        return []
    return [
        dict(
            id=c["constraint_id"],
            mandatory=c["mandatory"],
            result=c["result"],
            measured=c["measured_value"],
        )
        for c in verified["static_report"]["checks"]
    ]


def candidate(report: dict, c: dict) -> dict:
    plan = c.get("revised_plan") or {}
    return dict(
        handle=c["handle"],
        attempt=c["attempt"],
        origin=c["origin"],
        template=c["proposal"].get("template_id"),
        parameters=c["proposal"].get("parameters"),
        evidence_cited=c["proposal"].get("evidence_ids"),
        final_stage=c["final_stage"],
        stages=[(s["stage"], s["at_s"]) for s in c["stages"]],
        candidate_revision_id=c["candidate_id"],
        construction=c["construction"],
        static_checks=checks(report, c["candidate_id"]),
        verification=c["verification"],
        revised_plan=dict(
            status=plan.get("status"),
            complete=plan.get("complete"),
            steps=plan.get("steps"),
            metrics=plan.get("metrics"),
            replay=plan.get("replay"),
            reverse=plan.get("reverse"),
            constraint_checks=plan.get("constraint_checks"),
        ),
        comparison=c["comparison"],
        feedback=c["feedback"],
    )


def cost_estimate(report: dict) -> dict:
    """The run's configured price, else the exact provider/model list price."""
    if not report["live_model"]:
        return dict(estimated_usd=None, reason="no live model usage in this run")
    configured = report["usage"].get("cost") or {}
    if configured.get("estimated_usd") is not None:
        return dict(configured, basis="price table configured for the run")
    model = report.get("model") or {}
    provider, model_id = model.get("provider"), model.get("model_id")
    prices = list_prices_for(provider, model_id)
    if prices is None:
        return dict(
            estimated_usd=None, reason=f"no price table for {provider}/{model_id}"
        )
    u = report["usage"]
    estimate = estimate_cost(
        Counters(
            provider_requests=u["provider_requests"],
            usage_reported_turns=u["usage_reported_turns"],
            input_tokens=u["input_tokens"],
            output_tokens=u["output_tokens"],
            cached_input_tokens=u["cached_input_tokens"],
        ),
        prices,
    )
    return dict(estimate, basis=f"public list price for {provider}/{model_id}")


def summarize(report: dict) -> dict:
    results = {r["call_id"]: r for r in report["engineering_evidence"]["tool_results"]}
    turns, calls = [], []
    for e in report["events"]:
        if e["kind"] == "model_turn":
            u = e.get("usage") or {}
            turns.append(
                dict(
                    finish_reason=e["status"],
                    tool_calls=e["tool_calls"],
                    latency_s=round((e["duration_ms"] or 0) / 1000, 2),
                    input_tokens=u.get("prompt_tokens"),
                    output_tokens=u.get("completion_tokens"),
                    reasoning_tokens=(u.get("completion_tokens_details") or {}).get(
                        "reasoning_tokens"
                    ),
                    visible_note=e.get("note"),
                )
            )
        elif e["kind"] == "tool_call":
            r = results.get(e.get("tool_call_id"), {})
            calls.append(
                dict(
                    tool=e["tool"],
                    tool_call_id=e.get("tool_call_id"),
                    arguments=e.get("arguments"),
                    status=e["status"],
                    failure=e.get("failure"),
                    feedback=(r.get("feedback") or {}).get("message"),
                    evidence_ids=e.get("evidence_ids"),
                    duration_ms=e.get("duration_ms"),
                    payload=r.get("payload"),
                )
            )
    u = report["usage"]
    identity = report["identity"]
    return dict(
        run_id=report["run_id"],
        generated_at=report["generated_at"],
        provenance=report["provenance"],
        model=report["model"],
        fixture=dict(
            project_id=identity["project_id"],
            target_id=identity["target_id"],
            note="synthetic repository fixture; not a validated product",
        ),
        original_revision_id=identity["revision_id"],
        geometry_hash=identity["geometry_hash"],
        constraint_hash=identity["constraint_hash"],
        policy_version=identity["policy_version"],
        search_policy=identity["search_policy"],
        search_policy_hash=digest(identity["search_policy"]),
        baseline={
            k: report["baseline"][k]
            for k in ("plan_id", "status", "complete", "rejections")
        },
        model_turns=turns,
        tool_calls=calls,
        candidates=[candidate(report, c) for c in report["candidates"]],
        outcome=report["outcome"],
        explanation=report["explanation"],
        stop_reason=report["stop_reason"],
        model_final_message=report["final_model_message"],
        usage={
            k: u[k]
            for k in (
                "provider_requests",
                "turns",
                "tool_calls",
                "rejected_calls",
                "retries",
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "total_tokens",
                "model_latency_ms",
                "geometry_ms",
                "source",
            )
        },
        cost_estimate=cost_estimate(report),
        timings=report["timings"],
        budget=report["budget"],
        limitations=report["limitations"],
    )


def selector(report: dict) -> dict:
    return dict(
        provenance=report["provenance"],
        outcome=report["outcome"],
        stop_reason=report["stop_reason"],
        total_s=report["timings"]["total_s"],
        tool_calls=report["usage"]["tool_calls"],
        candidates=[
            dict(
                parameters=c["proposal"].get("parameters"),
                final_stage=c["final_stage"],
                failure=(c.get("feedback") or {}).get("category"),
            )
            for c in report["candidates"]
        ],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--selectors", type=Path, nargs="*", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = summarize(json.loads(args.run.read_text()))
    out["deterministic_selectors"] = [
        selector(json.loads(p.read_text())) for p in args.selectors
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
