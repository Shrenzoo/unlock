"""Typed coordinator interface: search, independent replay, inverse checks, metrics."""

from ..contracts import EngineError, POLICY, Status, digest
from ..geometry import bounds, collision
from .actions import ActionValidator
from .contracts import PlanResult, SearchPolicy
from .problem import Problem
from .replay import replay_plan, validate_reverse
from .search import search
from .state import metrics


def result_record(**data):
    # Runtime measurements are evidence, but are not semantic analysis identity.
    result = PlanResult(id="pending", **data)
    identity = result.model_dump(
        mode="json", exclude={"id", "elapsed_ms", "stats", "provenance"}
    )
    for name in ("replay", "reverse"):
        identity[name].pop("elapsed_ms")
    return result.model_copy(update={"id": digest(identity)})


def empty_result(
    target_id,
    policy=SearchPolicy(),
    *,
    revision_id="unavailable",
    status="invalid_input",
    error=None,
):
    identity = digest([revision_id, target_id, policy, POLICY])
    return result_record(
        status=status,
        revision_id=revision_id,
        target_id=target_id,
        input_hash=identity,
        geometry_hash="unavailable",
        constraint_hash="unavailable",
        comparison_hash="unavailable",
        search_policy=policy,
        limits=policy,
        complete=False,
        optimal_within_scope=False,
        error=error,
    )


def base_fields(problem):
    return dict(
        revision_id=problem.revision_id,
        original_revision_id=problem.revision.input_hash,
        modified_occurrence_ids=(problem.candidate.bracket_id,)
        if problem.candidate
        else (),
        target_id=problem.target_id,
        input_hash=problem.input_hash,
        geometry_hash=problem.geometry_hash,
        constraint_hash=problem.constraint_hash,
        comparison_hash=problem.comparison_hash,
        search_policy=problem.policy,
        limits=problem.policy,
        static_verification_id=problem.static_report.id
        if problem.static_report
        else None,
        static_checks=problem.static_report.checks if problem.static_report else (),
    )


def partial_record(problem, outcome):
    return result_record(
        **base_fields(problem),
        status="cancelled" if outcome.cancelled else "incomplete",
        complete=False,
        optimal_within_scope=False,
        expanded_states=outcome.expanded,
        elapsed_ms=outcome.elapsed_ms,
        unresolved_transition_count=outcome.unresolved,
        stats=outcome.stats,
        rejections=outcome.rejections,
        certificates=outcome.certificates,
    )


def mandatory_checks(problem, steps):
    if problem.static_report:
        checks = [
            (c.constraint_id, c.result)
            for c in problem.static_report.checks
            if c.mandatory
        ]
    else:
        checks = [("source_readiness", "pass")]
        keepout_findings = [
            collision(s, ko, problem.policy.clearance_mm)
            for s in problem.shapes.values()
            for ko in problem.keepouts.values()
        ]
        checks.append(
            (
                "keep_outs",
                "fail"
                if any(f.status == Status.BLOCKED for f in keepout_findings)
                else "unknown"
                if any(f.status != Status.CLEAR for f in keepout_findings)
                else "pass",
            )
        )
        # The original BRep is the reference for geometry/interface invariants.
        # Pair clearance and keep-outs still require actual geometry evidence.
        for c in problem.manifest.constraints:
            if not c.mandatory or (c.kind == "clearance" and c.scope == "path"):
                continue
            status = "pass"
            if c.kind == "clearance" and c.scope == "pair":
                if len(c.component_ids) != 2:
                    status = "unknown"
                else:
                    a, b = c.component_ids
                    f = collision(
                        problem.shapes[a], problem.shapes[b], c.threshold_mm, (a, b)
                    )
                    status = (
                        "pass"
                        if f.status == Status.CLEAR
                        else "fail"
                        if f.status == Status.BLOCKED
                        else "unknown"
                    )
            elif c.kind == "envelope":
                status = (
                    "pass"
                    if all(
                        problem.manifest.envelope_mm.contains(bounds(problem.shapes[k]))
                        for k in (c.component_ids or tuple(problem.shapes))
                    )
                    else "fail"
                )
            elif c.kind == "keep_out":
                findings = [
                    collision(problem.shapes[k], ko, problem.policy.clearance_mm)
                    for k in (c.component_ids or tuple(problem.shapes))
                    for ko in problem.keepouts.values()
                ]
                status = (
                    "fail"
                    if any(f.status == Status.BLOCKED for f in findings)
                    else "unknown"
                    if any(f.status != Status.CLEAR for f in findings)
                    else "pass"
                )
            checks.append((c.id, status))
    for c in problem.manifest.constraints:
        if c.mandatory and c.kind == "clearance" and c.scope == "path":
            matched = any(
                (s.component_id,) == c.component_ids
                and s.axis == c.axis
                and s.distance_mm >= c.distance_mm
                for s in steps
            )
            checks.append((c.id, "pass" if matched else "unknown"))
    return tuple(checks)


def plan_problem(problem, *, cancel=None, progress=None, phase=None):
    phase = phase or (lambda _: None)
    if cancel is not None and cancel.is_set():
        return empty_result(
            problem.target_id,
            problem.policy,
            revision_id=problem.revision_id,
            status="cancelled",
        )
    phase("search")
    validator = ActionValidator(problem)
    outcome = search(
        problem,
        validator,
        cancel=cancel,
        progress=(lambda o: progress(partial_record(problem, o))) if progress else None,
    )
    fields = dict(
        **base_fields(problem),
        expanded_states=outcome.expanded,
        elapsed_ms=outcome.elapsed_ms,
        unresolved_transition_count=outcome.unresolved,
        stats=outcome.stats,
        rejections=outcome.rejections,
        certificates=outcome.certificates,
    )
    if outcome.cancelled:
        return result_record(
            **fields, status="cancelled", complete=False, optimal_within_scope=False
        )
    if not outcome.steps:
        return result_record(
            **fields,
            status="no_path_supported" if outcome.complete else "incomplete",
            complete=outcome.complete,
            optimal_within_scope=False,
        )
    phase("replay")
    replay = replay_plan(problem, outcome.steps, outcome.certificates, cancel=cancel)
    if cancel is not None and cancel.is_set():
        return result_record(
            **fields, status="cancelled", complete=False, optimal_within_scope=False
        )
    if replay.status != "passed":
        return result_record(
            **fields,
            status="incomplete",
            complete=False,
            optimal_within_scope=False,
            replay=replay,
            error=EngineError("VERIFICATION_UNKNOWN", replay.explanation).envelope(),
        )
    phase("reverse")
    reverse = validate_reverse(problem, outcome.steps, cancel=cancel)
    if cancel is not None and cancel.is_set():
        return result_record(
            **fields, status="cancelled", complete=False, optimal_within_scope=False
        )
    phase("constraints")
    checks = mandatory_checks(problem, outcome.steps)
    return result_record(
        **fields,
        status="feasible",
        complete=outcome.complete,
        optimal_within_scope=outcome.optimal,
        steps=outcome.steps,
        replay=replay,
        reverse=reverse,
        metrics=metrics(outcome.steps, replay.certificates, problem.target_id),
        constraint_checks=checks,
        replacement_verified=reverse.status == "passed"
        and all(v == "pass" for _, v in checks),
    )


def plan_revision(
    revision,
    target_id,
    policy=SearchPolicy(),
    *,
    candidate=None,
    expected_revision_id=None,
    cancel=None,
    progress=None,
    phase=None,
):
    """In-process native entry point. Coordinators should use isolated_plan instead."""
    try:
        problem = Problem(
            revision,
            target_id,
            policy,
            candidate=candidate,
            expected_revision_id=expected_revision_id,
        )
        return plan_problem(problem, cancel=cancel, progress=progress, phase=phase)
    except EngineError as exc:
        return empty_result(
            target_id,
            policy,
            revision_id=expected_revision_id
            or (candidate.id if candidate else revision.input_hash),
            error=exc.envelope(),
        )


def compare_plans(original, revised):
    """Compare service-produced records under identical frozen semantics. No percentages."""
    for plan in (original, revised):
        validate_saved_result(plan)
    if (original.target_id, original.comparison_hash, original.search_policy) != (
        revised.target_id,
        revised.comparison_hash,
        revised.search_policy,
    ) or original.comparison_hash == "unavailable":
        raise EngineError(
            "STALE_REVISION",
            "comparison requires identical target, constraints, staging, tool configuration and search policy",
        )
    if revised.original_revision_id != original.revision_id:
        raise EngineError(
            "STALE_REVISION",
            "revised plan does not descend from this original revision",
        )
    eligible = revised.status == "feasible" and revised.replacement_verified
    improved = False
    reason = "No verified improvement"
    if (
        eligible
        and original.status == "no_path_supported"
        and original.complete
        and not original.unresolved_transition_count
    ):
        improved, reason = (
            True,
            "Original: No feasible route under supported operations. Revised: Feasible supported route.",
        )
    elif eligible and original.status == "feasible":
        a, b = original.metrics.cost, revised.metrics.cost
        counts_ok = b < a and all(y <= x for x, y in zip(a, b))
        if counts_ok and original.optimal_within_scope and revised.optimal_within_scope:
            improved, reason = (
                True,
                "Verified improvement of optimal supported plan cost; no listed count increased",
            )
        elif counts_ok:
            reason = "Best-found route has lower counts; global improvement is unproven because a search is incomplete"
    return dict(
        original_plan_id=original.id,
        revised_plan_id=revised.id,
        original_status=original.status,
        revised_status=revised.status,
        original_metrics=original.metrics.model_dump(mode="json")
        if original.metrics
        else None,
        revised_metrics=revised.metrics.model_dump(mode="json")
        if revised.metrics
        else None,
        verified_improvement=improved,
        explanation=reason,
        comparison_scope="proven_supported_optima"
        if original.complete and revised.complete
        else "best_found_only",
        original_complete=original.complete,
        revised_complete=revised.complete,
        revised_replacement_verified=revised.replacement_verified,
    )


def validate_saved_result(plan):
    PlanResult.model_validate(plan.model_dump(mode="json"))
    if result_record(**plan.model_dump(exclude={"id"})).id != plan.id:
        raise EngineError("STALE_REVISION", "plan record identity is corrupt")
    if plan.status == "feasible":
        if (
            metrics(plan.steps, plan.replay.certificates, plan.target_id)
            != plan.metrics
        ):
            raise EngineError(
                "STALE_REVISION", "metrics differ from saved actions and certificates"
            )
        for certificate in (
            *plan.certificates,
            *plan.replay.certificates,
            *plan.reverse.certificates,
        ):
            if (
                certificate.id != digest(certificate.model_dump(exclude={"id"}))
                or certificate.input_hash != plan.input_hash
            ):
                raise EngineError(
                    "STALE_REVISION", "certificate identity or revision mismatch"
                )


def compare_revisions(
    revision, target_id, candidate, policy=SearchPolicy(), *, cancel=None
):
    original = plan_revision(revision, target_id, policy, cancel=cancel)
    revised = plan_revision(
        revision, target_id, policy, candidate=candidate, cancel=cancel
    )
    return original, revised, compare_plans(original, revised)
