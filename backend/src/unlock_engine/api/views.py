"""Explicit adapters from authoritative engine records to the existing React contract."""

from __future__ import annotations

from ..contracts import digest


def provenance(input_hash, at, note):
    return dict(
        kind="computed_earlier",
        input_hash=input_hash,
        computed_at=at,
        engine_versions={"cadquery": "2.6.1", "cadquery-ocp": "7.8.1.1.post1"},
        note=note,
    )


def revision_view(record):
    inventory = record["inventory"]
    manifest = dict(record["manifest"])
    measured = {c["id"]: c for c in inventory["components"]}
    manifest["components"] = [
        dict(c, bounds_mm=measured[c["id"]]["bounds_mm"])
        for c in manifest["components"]
    ]
    return dict(
        id=record["id"],
        project_id=record["project_id"],
        label=record["id"][:12],
        input_hash=record["id"],
        constraint_hash=record["constraint_hash"],
        manifest=manifest,
        readiness=list(inventory["readiness"]),
        preview_artifact_id=record["preview"],
        provenance=provenance(
            record["id"],
            record["created_at"],
            "Real CAD import; synthetic bundled input"
            if record["synthetic"]
            else "Real CAD import; locally supplied input",
        ),
    )


def plan_view(plan):
    if plan is None:
        return None
    steps = []
    for s in plan["steps"]:
        a, b = s["start_transform"]["matrix"], s["end_transform"]["matrix"]
        steps.append(
            dict(s, start_mm=[0, 0, 0], end_mm=[b[i] - a[i] for i in (3, 7, 11)])
        )
    certs = {c["id"]: c for c in plan["certificates"]}
    rejections = []
    for r in plan["rejections"]:
        if r["category"] in ("SEMANTICALLY_BLOCKED", "UNSUPPORTED_OPERATION"):
            continue  # Semantic refusals stay in the full report, not geometric witness cards.
        findings = [
            f
            for cid in r["witness_certificate_ids"]
            for p in certs.get(cid, {}).get("paths", [])
            for f in p["findings"]
        ]
        witness = next(
            (f for f in findings if f.get("witness_travel_mm") is not None), {}
        )
        blocked = [f for f in findings if f.get("status") == "blocked"]
        level = (
            "confirmed_witness"
            if any(f.get("kind") == "positive_volume_intersection" for f in blocked)
            else "insufficient_clearance"
            if any(f.get("distance_mm") is not None for f in blocked)
            else "proxy_unknown"
        )
        a = r["action"]
        rejections.append(
            dict(
                id=r["id"],
                action_kind="TOOL_APPROACH"
                if r["category"] == "TOOL_ACCESS_BLOCKED"
                else a["kind"],
                component_id=a["component_id"],
                axis=a["axis"],
                obstacle_ids=sorted(
                    {
                        id
                        for f in blocked or findings
                        for id in f.get("component_ids", [])
                        if id != a["component_id"] and id in r["remaining_obstacle_ids"]
                    }
                ),
                evidence_level=level,
                witness_travel_mm=witness.get("witness_travel_mm"),
                explanation=r["reason"],
                diagnostic=False,
                removed_ids=r["removed_ids"],
                category=r["category"],
            )
        )
    return dict(plan, steps=steps, rejections=rejections)


def apply_ai(run, report, store):
    evidence = report["engineering_evidence"]
    verified = evidence.get("verified", {})
    constructed = {
        r["candidate"]["id"]: r
        for r in evidence.get("constructed", {}).values()
        if r.get("ok")
    }
    candidates = []
    selected = None
    for c in report["candidates"]:
        geometry_id = c["candidate_id"]
        api_id = "candidate_" + digest([run["id"], c["handle"]])[:32]
        raw = verified.get(geometry_id, {})
        static = raw.get("static_report")
        plan = raw.get("plan")
        built = constructed.get(geometry_id, {})
        eligible = (
            report["outcome"] != "CANCELLED"
            and c["final_stage"] in ("CHECKED", "VERIFIED_IMPROVEMENT")
            and static
            and static["status"] == "passed"
            and plan
            and plan["replacement_verified"]
        )
        checks = []
        if static:
            checks = [
                dict(
                    constraint_id=k["constraint_id"],
                    label=k["constraint_id"],
                    mandatory=k["mandatory"],
                    result=k["result"],
                    measured=str(k["measured_value"])
                    if k.get("measured_value") is not None
                    else None,
                    limit=str(k.get("limit")),
                    evidence_ids=list(k.get("evidence_ids", [])),
                    explanation=k["explanation"],
                )
                for k in static["checks"]
            ]
        if plan:
            for name in ("replay", "reverse"):
                result = plan[name]
                checks.append(
                    dict(
                        constraint_id=name,
                        label="Forward replay"
                        if name == "replay"
                        else "Reverse insertion and tool restoration",
                        result="pass"
                        if result["status"] == "passed"
                        else "fail"
                        if result["status"] == "failed"
                        else "unknown",
                        measured=result["status"],
                        limit="passed",
                        evidence_ids=[x["id"] for x in result["certificates"]],
                        explanation=result["explanation"],
                    )
                )
            checks.extend(
                dict(
                    constraint_id="route:" + k,
                    label="Route constraint " + k,
                    result=v,
                    measured=v,
                    limit="pass",
                    evidence_ids=[plan["id"]],
                    explanation="Mandatory route constraint from deterministic planner",
                )
                for k, v in plan["constraint_checks"]
            )
        check_status = (
            "passed"
            if eligible
            else "failed"
            if any(k["result"] == "fail" for k in checks)
            else "unknown"
        )
        diff = built.get("geometry_diff")
        if diff:
            diff = dict(
                diff,
                protected_unchanged=["feet", "posts", "hole regions"]
                if static and static["status"] == "passed"
                else [],
            )
        candidate = dict(
            id=api_id,
            proposal=c["proposal"],
            state="checked"
            if eligible
            else "failed"
            if c["final_stage"] == "REJECTED" or report["outcome"] == "CANCELLED"
            else "constructing",
            diff=diff,
            verification=dict(
                id=static["id"],
                candidate_id=api_id,
                status=check_status,
                constraint_hash=static["constraint_hash"],
                checks=checks,
                unverified_properties=static.get("unverified_properties", []),
            )
            if static
            else None,
            revised_plan=plan_view(plan),
            failure_summary=(c.get("feedback") or {}).get("message"),
            preview_artifact_id=built.get("artifacts", {}).get("preview.json"),
            input_hash=digest([run["id"], geometry_id, static, plan]),
            verified_improvement=bool(
                c.get("comparison", {}).get("verified_improvement")
            )
            if c.get("comparison")
            else False,
        )
        candidate["metrics"] = metric_rows(evidence["baseline"], plan) if plan else []
        candidates.append(candidate)
        store.put(
            "candidate",
            api_id,
            dict(
                candidate,
                run_id=run["id"],
                geometry_candidate_id=geometry_id,
                template=dict(
                    bracket_id=c["proposal"]["bracket_id"],
                    template_id=c["proposal"]["template_id"],
                    parameters=c["proposal"]["parameters"],
                ),
                comparison=c["comparison"],
            ),
            run["id"],
        )
        if c["handle"] == report["selected_candidate"] and eligible:
            selected = api_id
    run.update(
        candidates=candidates,
        selected_candidate_id=selected,
        outcome=report["outcome"],
        explanation=report["explanation"],
        model=dict(id=report["model"]["model_id"], provider=report["model"]["provider"])
        if report["live_model"] or report["usage"]["turns"]
        else None,
        provenance=provenance(
            run["revision_id"],
            report["generated_at"],
            "Real CAD and planner; "
            + (
                "live Meta inference"
                if report["live_model"] and report["model"]["provider"] == "meta"
                else "live " + report["model"]["provider"] + " inference"
                if report["live_model"]
                else "offline scripted inference"
                if report["provenance"] == "offline_fake_provider"
                else "no model inference"
            ),
        ),
        ai_report_artifact_id=store.artifacts.put_json(report),
        evidence_refs={
            handle: ref["id"]
            for handle, ref in evidence.get("handle_index", {}).items()
        },
    )
    run["metrics"] = next((c["metrics"] for c in candidates if c["id"] == selected), [])
    return run


def metric_rows(base, revised):
    rows = [
        dict(
            id="status",
            label="Supported route",
            definition="Deterministic search status",
            original=base["status"],
            revised=revised["status"],
            note="Counts and percentages are undefined for an infeasible route.",
        )
    ]
    for field, label in [
        ("unrelated_parts_removed", "Unrelated parts"),
        ("fasteners_removed", "Fasteners"),
        ("tool_changes", "Tool changes"),
        ("operations", "Operations"),
    ]:
        rows.append(
            dict(
                id=field,
                label=label,
                definition="Count in this candidate's checked removal route",
                original=str(base["metrics"][field]) if base.get("metrics") else None,
                revised=str(revised["metrics"][field])
                if revised.get("metrics")
                else None,
            )
        )
    return rows
