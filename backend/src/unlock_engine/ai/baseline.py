"""Deterministic, non-AI candidate selectors (PRD §21 comparator C2).

Both rules were fixed before any evaluation was run and use the same inputs,
template domains, candidate/tool/time budgets, constructor, verifier and
improvement rule as the model. They receive no information the model lacks:

stable_enumeration  Binding template order, then the server's declared value
                    order (itertools.product). This is the PRD's C2 definition.
geometry_ranked     A stronger rule baseline. T01 cuts whose world XY box covers
                    the target's measured XY bounds inflated by the policy
                    clearance + tolerance come first, smallest cut area first;
                    then T02 offsets whose shifted web band clears the target's
                    inflated Y range, smallest |offset| first; then everything
                    else in stable order. Template limits (minimum web, maximum
                    cut volume) declared in the manifest filter T01 cuts.
"""

from __future__ import annotations

import itertools
import json
import threading

from ..contracts import POLICY
from ..planning.contracts import SearchPolicy
from ..templates import SERVER_DOMAINS
from .controller import RedesignRun
from .provider import ToolCall
from .toolbox import Budget

RULES = ("stable_enumeration", "geometry_ranked")


def domain_order(session):
    out = []
    for binding in session.manifest.template_bindings:
        for t in binding.templates:
            if t.id not in SERVER_DOMAINS:
                continue
            keys = list(SERVER_DOMAINS[t.id])
            values = [
                [v for v in SERVER_DOMAINS[t.id][k] if v in t.domain.get(k, ())]
                for k in keys
            ]
            for combo in itertools.product(*values):
                out.append(
                    dict(
                        bracket_id=binding.bracket_id,
                        template_id=t.id,
                        parameters=dict(zip(keys, combo)),
                    )
                )
    return out


def _placement(session, bracket_id):
    comp = next(c for c in session.manifest.components if c.id == bracket_id)
    if comp.placement is None:
        return None
    m = comp.placement.matrix
    z = session.binding(bracket_id).parameters.web_underside_height_mm
    return lambda x, y: (
        m[0] * x + m[1] * y + m[2] * z + m[3],
        m[4] * x + m[5] * y + m[6] * z + m[7],
    )


def geometry_ranked(session, order):
    target = session.measured()[session.target_id]["bounds_mm"]
    guard = POLICY.clearance_mm + POLICY.tolerance_mm
    tx0, ty0 = target["min"][0] - guard, target["min"][1] - guard
    tx1, ty1 = target["max"][0] + guard, target["max"][1] + guard
    covering, clearing, rest = [], [], []
    for cand in order:
        binding = session.binding(cand["bracket_id"])
        to_world = _placement(session, cand["bracket_id"])
        p, b, v = cand["parameters"], binding.parameters, binding
        if to_world is None:
            rest.append(cand)
            continue
        if cand["template_id"] == "T01":
            x0, x1 = (
                p["center_x_mm"] - p["width_mm"] / 2,
                p["center_x_mm"] + p["width_mm"] / 2,
            )
            y0, y1 = (
                p["center_y_mm"] - p["depth_mm"] / 2,
                p["center_y_mm"] + p["depth_mm"] / 2,
            )
            web_ok = (
                min(
                    x0 + b.web_length_mm / 2,
                    b.web_length_mm / 2 - x1,
                    y0 + b.web_depth_mm / 2,
                    b.web_depth_mm / 2 - y1,
                )
                >= v.minimum_web_mm
            )
            vol_ok = (
                p["width_mm"] * p["depth_mm"] * b.web_thickness_mm
                <= v.maximum_cut_volume_mm3
            )
            corners = [to_world(x, y) for x in (x0, x1) for y in (y0, y1)]
            wx0, wx1 = min(c[0] for c in corners), max(c[0] for c in corners)
            wy0, wy1 = min(c[1] for c in corners), max(c[1] for c in corners)
            if (
                web_ok
                and vol_ok
                and wx0 <= tx0
                and wx1 >= tx1
                and wy0 <= ty0
                and wy1 >= ty1
            ):
                covering.append(((x1 - x0) * (y1 - y0), cand))
            else:
                rest.append(cand)
        else:
            lo, hi = (
                -b.web_depth_mm / 2 + p["offset_y_mm"],
                b.web_depth_mm / 2 + p["offset_y_mm"],
            )
            band = sorted(to_world(0, y)[1] for y in (lo, hi))
            if band[0] >= ty1 or band[1] <= ty0:
                clearing.append((abs(p["offset_y_mm"]), cand))
            else:
                rest.append(cand)
    covering.sort(key=lambda t: t[0])
    clearing.sort(key=lambda t: t[0])
    return [c for _, c in covering] + [c for _, c in clearing] + rest


def run_selector(
    step_bytes: bytes,
    manifest: dict,
    target_id: str,
    rule: str,
    *,
    budget: Budget = Budget(),
    search_policy: SearchPolicy = SearchPolicy(),
    cancel: threading.Event | None = None,
) -> dict:
    if rule not in RULES:
        raise ValueError(f"unknown selector rule {rule}")
    run = RedesignRun(
        step_bytes,
        manifest,
        target_id,
        budget=budget,
        search_policy=search_policy,
        cancel=cancel,
    )
    origin = f"deterministic:{rule}"
    early = run.open(
        model_identity=dict(
            model_id=None, provider=None, reasoning_effort=None, origin=origin
        )
    )
    if early:
        outcome, why = run.derive(early)
        return run.report(
            outcome,
            why,
            early,
            provenance="deterministic_selector:" + rule,
            model=None,
            final=None,
            prices=None,
        )
    s, tb, c = run.session, run.toolbox, run.counters
    order = domain_order(s)
    if rule == "geometry_ranked":
        order = geometry_ranked(s, order)
    ids = dict(
        project_id=s.project_id, revision_id=s.revision_handle, target_id=s.target_id
    )
    plan_handle = tb.issue("plan", s.baseline.id)
    stop = "candidates_exhausted"
    for i, cand in enumerate(order):
        if c.candidates_constructed >= budget.max_candidates:
            stop = "candidate_budget"
            break
        if run.deadline.cancelled:
            stop = "cancelled"
            break
        if run.deadline.remaining() < 8 or c.tool_calls + 2 > budget.max_tool_calls:
            stop = "time_budget" if run.deadline.remaining() < 8 else "tool_call_budget"
            break
        proposal = dict(
            candidate_request_id=f"det-{i}",
            evidence_ids=[plan_handle],
            rationale=f"{rule} order position {i}",
            **cand,
        )
        result = _call(
            run,
            f"det-{i}-construct",
            "construct_candidate",
            dict(ids, request_id=f"det-{i}-c", proposal=proposal),
        )
        handle = (result.payload or {}).get("candidate_id")
        if result.status != "ok" or not handle:
            continue
        result = _call(
            run,
            f"det-{i}-verify",
            "verify_candidate",
            dict(ids, request_id=f"det-{i}-v", candidate_id=handle),
        )
        record = tb.candidates[handle]
        if record.final_stage == "CHECKED":
            tb.assess(record)
            if record.final_stage == "VERIFIED_IMPROVEMENT":
                stop = "verified_improvement"
                break
    outcome, why = run.derive(stop)
    return run.report(
        outcome,
        why,
        stop,
        provenance="deterministic_selector:" + rule,
        model=None,
        final=None,
        prices=None,
    )


def _call(run, call_id, name, args):
    run.counters.tool_calls += 1
    result, _ = run.toolbox.execute(ToolCall(call_id, name, json.dumps(args)))
    run.log.emit(
        "tool_call",
        name,
        tool=name,
        tool_call_id=call_id,
        request_id=args.get("request_id"),
        arguments=args,
        status=result.status,
        evidence_ids=[
            e
            for e in (result.evidence_id, (result.payload or {}).get("candidate_id"))
            if e
        ],
        failure=result.feedback.category if result.feedback else None,
        cached=result.cached,
        duration_ms=result.duration_ms,
    )
    return result
