"""Bounded controller with a scripted offline provider and the REAL geometry engine and planner.

The fake provider only chooses tool calls (reacting to actual tool results); every
construction, verification, plan and comparison is computed by the engine.
"""

import copy
import json
import threading

import pytest

from ai_helpers import (
    calls,
    context,
    final,
    geometric_rejection,
    ids,
    proposal,
    relief,
    reuse_stage_a,
    tool_results,
)
from unlock_engine.ai.config import load_config
from unlock_engine.ai.controller import run_with_model
from unlock_engine.ai.provider import (
    FakeProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from unlock_engine.ai.toolbox import Budget
from unlock_engine.fixtures import generate_fixture


@pytest.fixture(scope="module")
def b02(tmp_path_factory):
    d = generate_fixture(tmp_path_factory.mktemp("ai") / "B02", "B02")
    return (d / "assembly.step").read_bytes(), json.loads(
        (d / "manifest.json").read_text()
    )


@pytest.fixture(scope="module")
def b01(tmp_path_factory):
    d = generate_fixture(tmp_path_factory.mktemp("ai") / "B01", "B01")
    return (d / "assembly.step").read_bytes(), json.loads(
        (d / "manifest.json").read_text()
    )


@pytest.fixture(autouse=True)
def _stage_a(monkeypatch):
    reuse_stage_a(monkeypatch)


def correlated(messages):
    """Every tool message answers a call of the immediately preceding assistant turn, in order."""
    pending = []
    for m in messages:
        if m["role"] == "assistant":
            assert not pending, "assistant turn before all tool results were returned"
            pending = [c["id"] for c in m.get("tool_calls") or []]
        elif m["role"] == "tool":
            assert pending and m["tool_call_id"] == pending.pop(0)
    return True


def test_failed_candidate_feedback_then_revised_verified_improvement(b02):
    step, manifest = b02
    frozen = copy.deepcopy(manifest)
    state = {}

    def s1(m):
        state["rej"] = geometric_rejection(m)
        return calls(
            ("c1", "inspect_blocker", ids(m, "r1", rejection_id=state["rej"])),
            ("c2", "list_interventions", ids(m, "r2", bracket_id="bridge")),
        )

    def s2(m):
        blocker, interventions = tool_results(m)
        state["witness"] = blocker["payload"]["witnesses"][0]["witness_mm"]
        assert interventions["payload"]["templates"][0]["template_id"] == "T01"
        # deliberately off-witness first proposal
        return calls(
            (
                "c3",
                "construct_candidate",
                ids(
                    m,
                    "r3",
                    proposal=proposal("p1", relief(-4, -24, 24, 8), [state["rej"]]),
                ),
            )
        )

    def s3(m):
        (built,) = tool_results(m)
        assert built["status"] == "ok"
        state["first"] = built["payload"]["candidate_id"]
        return calls(
            ("c4", "verify_candidate", ids(m, "r4", candidate_id=state["first"]))
        )

    def s4(m):
        (checked,) = tool_results(m)
        assert (
            checked["status"] == "failed"
            and checked["feedback"]["category"] == "NO_REPAIR_PATH"
        )
        assert checked["feedback"]["retry_permitted"] is True
        state["fb"] = checked["evidence_id"] or checked["feedback"]["evidence_id"]
        x, y, _ = state["witness"]
        return calls(
            (
                "c5",
                "construct_candidate",
                ids(
                    m,
                    "r5",
                    proposal=proposal(
                        "p2",
                        relief(round(x), round(y), 24, 12),
                        [state["rej"], checked["feedback"]["evidence_id"]],
                    ),
                ),
            )
        )

    def s5(m):
        (built,) = tool_results(m)
        state["second"] = built["payload"]["candidate_id"]
        return calls(
            ("c6", "verify_candidate", ids(m, "r6", candidate_id=state["second"])),
            (
                "c7",
                "compare_candidates",
                ids(m, "r7", candidate_ids=[state["first"], state["second"]]),
            ),
        )

    def s6(m):
        verified, compared = tool_results(m)
        assert (
            verified["status"] == "ok"
            and verified["payload"]["final_stage"] == "CHECKED"
        )
        rows = {r["candidate_id"]: r for r in compared["payload"]["candidates"]}
        assert rows[state["second"]]["verified_improvement"] and not rows[
            state["first"]
        ].get("verified_improvement")
        return final(
            "candidate_proposed",
            [state["second"]],
            "relief at the witness clears the lift",
        )

    fake = FakeProvider([s1, s2, s3, s4, s5, s6])
    report = run_with_model(step, manifest, "target", fake)
    assert report["outcome"] == "VERIFIED_IMPROVEMENT_FOUND", report["explanation"]
    assert (
        report["provenance"] == "offline_fake_provider"
        and report["live_model"] is False
    )
    first, second = report["candidates"]
    assert (
        first["final_stage"] == "REJECTED"
        and first["feedback"]["category"] == "NO_REPAIR_PATH"
    )
    assert [s["stage"] for s in second["stages"]] == [
        "PROPOSED",
        "CONSTRUCTED",
        "CHECKED",
        "VERIFIED_IMPROVEMENT",
    ]
    assert (
        second["comparison"]["original_status"] == "no_path_supported"
        and second["revised_plan"]["status"] == "feasible"
    )
    assert (
        second["revised_plan"]["replacement_verified"]
        and second["verification"]["static_status"] == "passed"
    )
    assert report["selected_candidate"] == second["handle"]
    assert manifest == frozen  # constraints untouched by the run
    assert correlated(fake.calls[-1]["messages"])
    assert (
        report["usage"]["turns"] == 6 and report["usage"]["candidates_constructed"] == 2
    )
    labels = [e["stage_label"] for e in report["events"] if e["kind"] == "tool_call"]
    assert (
        "Constructing candidate geometry" in labels
        and "Comparing design revisions" in labels
    )


def test_all_candidates_fail_duplicate_and_budget_and_false_success_claim(b02):
    step, manifest = b02
    st = {}

    def s1(m):
        rej = st["rej"] = geometric_rejection(m)
        return calls(
            (
                "a",
                "construct_candidate",
                ids(m, "a", proposal=proposal("pa", relief(-4, -24, 24, 12), [rej])),
            ),
            (
                "b",
                "construct_candidate",
                ids(m, "b", proposal=proposal("pb", relief(-4, -24, 24, 16), [rej])),
            ),
            (
                "c",
                "construct_candidate",
                ids(m, "c", proposal=proposal("pc", relief(-4, -24, 24, 8), [rej])),
            ),
        )

    def s2(m):
        a, b, c = tool_results(m)
        assert (
            a["feedback"]["category"]
            == b["feedback"]["category"]
            == "CONSTRUCTION_FAILED"
        )
        assert a["feedback"]["constraint_id"] == "template_bound.minimum_web_mm"
        assert (
            a["feedback"]["measured"]["remaining_web_mm"]
            < a["feedback"]["allowed"]["minimum_web_mm"]
        )
        st["c"] = c["payload"]["candidate_id"]
        return calls(
            ("d", "verify_candidate", ids(m, "d", candidate_id=st["c"])),
            (
                "e",
                "construct_candidate",
                ids(
                    m,
                    "e",
                    proposal=proposal("pc2", relief(-4, -24, 24, 8), [st["rej"]]),
                ),
            ),
            (
                "f",
                "construct_candidate",
                ids(
                    m, "f", proposal=proposal("pd", relief(0, -20, 24, 12), [st["rej"]])
                ),
            ),
        )

    def s3(m):
        verify, dup, over = tool_results(m)
        assert verify["feedback"]["category"] == "NO_REPAIR_PATH"
        assert dup["feedback"]["category"] == "DUPLICATE_CANDIDATE"
        assert over["feedback"]["category"] == "BUDGET_EXHAUSTED"
        return final(
            "candidate_proposed",
            [st["c"]],
            "verified improvement achieved (false claim)",
        )

    report = run_with_model(step, manifest, "target", FakeProvider([s1, s2, s3]))
    assert report["outcome"] == "NO_VERIFIED_IMPROVEMENT"
    assert report["usage"]["candidates_constructed"] == 3
    assert {c["final_stage"] for c in report["candidates"]} == {"REJECTED"}
    assert report["selected_candidate"] is None
    assert report["final_model_message"]["authority"].startswith("none")


def test_invented_tools_end_the_ai_stage_after_one_repair(b02):
    step, manifest = b02

    def bad(name):
        return lambda m: calls(("x", name, ids(m, "x")))

    fake = FakeProvider(
        [bad("approve_candidate"), bad("run_shell"), bad("export_release")]
    )
    report = run_with_model(step, manifest, "target", fake)
    assert report["stop_reason"] == "schema_repair_exhausted"
    assert (
        report["outcome"] == "INCOMPLETE_ANALYSIS"
        and report["usage"]["schema_errors"] == 2
    )
    assert not report["candidates"] and len(fake.calls) == 2


def test_missing_credentials_reports_model_unavailable_and_preserves_baseline(b02):
    step, manifest = b02
    report = run_with_model(
        step, manifest, "target", OpenAICompatibleProvider(load_config({}))
    )
    assert (
        report["outcome"] == "MODEL_UNAVAILABLE"
        and report["stop_reason"] == "provider_error"
    )
    assert (
        report["baseline"]["status"] == "no_path_supported"
        and report["baseline"]["complete"]
    )
    assert report["live_model"] is False and report["usage"]["turns"] == 0
    assert report["provenance"] == "deterministic_only"
    assert any(
        e["kind"] == "provider_error" and e["status"] == "MISSING_CREDENTIALS"
        for e in report["events"]
    )


def test_provider_timeouts_are_retried_within_budget_then_reported(b02):
    step, manifest = b02

    def err(m):
        return ProviderError(
            "TIMEOUT", "simulated timeout", retryable=True, retry_after_s=0.05
        )

    report = run_with_model(step, manifest, "target", FakeProvider([err, err, err]))
    assert report["outcome"] == "MODEL_UNAVAILABLE"
    assert report["usage"]["retries"] == 2 and report["usage"]["provider_requests"] == 3


def test_cancellation_stops_before_executing_tools(b02):
    step, manifest = b02
    cancel = threading.Event()

    def s1(m):
        cancel.set()
        return calls(("c", "list_interventions", ids(m, "c", bracket_id="bridge")))

    report = run_with_model(step, manifest, "target", FakeProvider([s1]), cancel=cancel)
    assert report["outcome"] == "CANCELLED" and report["usage"]["tool_calls"] == 0


def test_tool_call_budget_is_enforced_inside_one_turn(b02):
    step, manifest = b02

    def s1(m):
        return calls(
            *[(f"k{i}", "inspect_constraints", ids(m, f"k{i}")) for i in range(13)]
        )

    fake = FakeProvider([s1])
    report = run_with_model(step, manifest, "target", fake, budget=Budget())
    assert (
        report["usage"]["tool_calls"] == 12
        and report["stop_reason"] == "tool_call_budget"
    )
    assert sum(e.get("status") == "not_executed" for e in report["events"]) == 1
    assert report["outcome"] == "INCOMPLETE_ANALYSIS"


def test_accessible_target_needs_no_model_call(b01):
    step, manifest = b01
    fake = FakeProvider([])
    report = run_with_model(step, manifest, "target", fake)
    assert (
        report["outcome"] == "NO_SUPPORTED_CANDIDATE"
        and report["stop_reason"] == "already_minimal"
    )
    assert fake.calls == [] and report["model"]["called"] is False


def test_turn_budget_and_context_shape(b02):
    step, manifest = b02
    seen = {}

    def look(m):
        seen.setdefault("ctx", context(m))
        return calls((f"t{len(seen)}", "inspect_constraints", ids(m, f"t{len(m)}")))

    report = run_with_model(
        step, manifest, "target", FakeProvider([look] * 7), budget=Budget(max_turns=2)
    )
    assert report["stop_reason"] == "turn_budget" and report["usage"]["turns"] == 2
    ctx = seen["ctx"]
    assert (
        ctx["run"]["revision_id"].startswith("rev_")
        and ctx["baseline"]["status"] == "no_path_supported"
    )
    assert ctx["brackets_with_constructor_binding"] == ["bridge"]
    assert all(
        r["category"] == "CONFIRMED_GEOMETRIC_OBSTRUCTION"
        for r in ctx["baseline"]["geometric_rejections"]
    )


def test_repeated_verification_reports_once_without_duplicating_stages(b02):
    step, manifest = b02
    st = {}

    def s1(m):
        st["rej"] = geometric_rejection(m)
        prop = proposal("p", relief(-4, -24, 24, 8), [st["rej"]])
        return calls(("c", "construct_candidate", ids(m, "c", proposal=prop)))

    def s2(m):
        st["cand"] = tool_results(m)[0]["payload"]["candidate_id"]
        return calls(
            ("v1", "verify_candidate", ids(m, "v1", candidate_id=st["cand"])),
            ("v2", "verify_candidate", ids(m, "v2", candidate_id=st["cand"])),
        )

    def s3(m):
        first, second = tool_results(m)
        assert first["feedback"]["category"] == second["feedback"]["category"]
        assert second.get("cached") is True and not first.get("cached")
        assert first["payload"]["final_stage"] == second["payload"]["final_stage"]
        return final("no_supported_candidate")

    report = run_with_model(step, manifest, "target", FakeProvider([s1, s2, s3]))
    (cand,) = report["candidates"]
    assert [s["stage"] for s in cand["stages"]] == [
        "PROPOSED",
        "CONSTRUCTED",
        "REJECTED",
    ]
    assert report["outcome"] == "NO_VERIFIED_IMPROVEMENT"


def test_deterministic_selectors_use_the_same_tools_and_report_contract(b02):
    from unlock_engine.ai.baseline import run_selector

    step, manifest = b02
    ranked = run_selector(step, manifest, "target", "geometry_ranked")
    stable = run_selector(step, manifest, "target", "stable_enumeration")
    assert ranked["outcome"] == "VERIFIED_IMPROVEMENT_FOUND" and ranked["model"] is None
    assert ranked["provenance"] == "deterministic_selector:geometry_ranked"
    assert stable["outcome"] == "NO_VERIFIED_IMPROVEMENT"
    assert (
        stable["usage"]["candidates_constructed"] == 3 and stable["usage"]["turns"] == 0
    )
    assert all(
        e.get("origin") == "deterministic:stable_enumeration" for e in stable["events"]
    )


def test_retry_reservations_count_unknown_billed_output(b02):
    step, manifest = b02

    def error(m):
        return ProviderError(
            "TIMEOUT", "uncertain billed response", retryable=True, retry_after_s=0
        )

    fake = FakeProvider([error] * 4)
    report = run_with_model(
        step,
        manifest,
        "target",
        fake,
        budget=Budget(max_output_tokens=3000, per_turn_output_tokens=2000),
    )
    assert report["stop_reason"] == "output_token_budget"
    assert report["outcome"] == "INCOMPLETE_ANALYSIS"
    assert report["usage"]["provider_requests"] == 2
    assert report["usage"]["output_budget_used"] == 3000
    assert report["usage"]["uncertain_output_tokens"] == 3000
    assert report["usage"]["cost"]["estimated_usd"] is None


def test_unstructured_text_gets_one_repair_without_inventing_tools(b02):
    step, manifest = b02
    fake = FakeProvider(
        [lambda m: dict(role="assistant", content="The design is verified!")] * 3
    )
    report = run_with_model(step, manifest, "target", fake)
    assert report["outcome"] == "INCOMPLETE_ANALYSIS"
    assert report["stop_reason"] == "schema_repair_exhausted"
    assert not report["candidates"] and report["usage"]["tool_calls"] == 0
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    "kw",
    [
        dict(max_candidates=4),
        dict(max_turns=7),
        dict(max_tool_calls=13),
        dict(max_output_tokens=16001),
        dict(max_seconds=121),
        dict(max_seconds=float("nan")),
    ],
)
def test_public_limits_cannot_be_raised(kw):
    with pytest.raises(ValueError):
        Budget(**kw)


def test_durable_evidence_contains_actual_geometry_and_full_verified_plans(
    b02, tmp_path
):
    from unlock_engine.ai.demo import scripted_agent
    from unlock_engine.artifacts import ArtifactStore

    step, manifest = b02
    report = run_with_model(
        step, manifest, "target", scripted_agent(), artifact_root=tmp_path
    )
    assert report["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
    evidence = report["engineering_evidence"]
    assert evidence["baseline"]["status"] == "no_path_supported"
    assert evidence["tool_results"] and evidence["input_artifacts"]
    store = ArtifactStore(tmp_path)
    assert store.get(evidence["input_artifacts"]["assembly.step"]) == step
    built = list(evidence["constructed"].values())[-1]
    assert store.get(built["artifacts"]["changed_bracket.step"]).startswith(
        b"ISO-10303-21;"
    )
    preview = json.loads(store.get(built["artifacts"]["preview.json"]))
    assert {c["occurrence_id"] for c in preview["components"]} == {
        c["id"] for c in manifest["components"]
    }
    revised = list(evidence["verified"].values())[-1]["plan"]
    assert revised["replacement_verified"] and revised["steps"][0]["certificate_ids"]
    assert len(revised["steps"][0]["start_transform"]["matrix"]) == 16
    assert (
        revised["replay"]["status"] == "passed"
        and revised["reverse"]["status"] == "passed"
    )
