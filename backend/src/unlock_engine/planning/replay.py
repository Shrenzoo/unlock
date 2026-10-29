"""Fresh semantic/CAD replay and explicit inverse restoration, independent of UCS."""

import time

from ..contracts import EngineError, digest
from .actions import ActionValidator
from .contracts import State, ValidationReport
from .state import advance, connections, make_step, translated_placement


def replay_plan(problem, steps, certificates, *, cancel=None):
    started = time.monotonic()
    state = State()
    validator = ActionValidator(problem)  # Deliberately no search cache.
    checked = []
    by_id = {c.id: c for c in certificates}
    try:
        problem.check_integrity()
        if len(by_id) != len(certificates):
            raise ValueError("duplicate certificate IDs")
        for step in steps:
            if cancel is not None and cancel.is_set():
                raise EngineError("CANCELLED", "replay cancelled")
            if problem.target_id in state.removed:
                raise ValueError("route continues after target extraction")
            if len(step.certificate_ids) != 1 or step.certificate_ids[0] not in by_id:
                raise ValueError("missing operation certificate")
            stored = by_id[step.certificate_ids[0]]
            if stored.id != digest(stored.model_dump(exclude={"id"})):
                raise ValueError("corrupt certificate")
            result = validator.evaluate(state, step.action())
            if result.certificate:
                checked.append(result.certificate)
            if result.status != "clear":
                return ValidationReport(
                    status="unknown" if result.status == "unknown" else "failed",
                    explanation=result.rejection.reason,
                    checked_steps=len(checked),
                    certificates=tuple(checked),
                    final_removed_ids=tuple(sorted(state.removed)),
                    elapsed_ms=(time.monotonic() - started) * 1000,
                )
            if result.certificate != stored or step != make_step(
                problem, state, step.action(), result.certificate
            ):
                raise ValueError(
                    "stale certificate, movement, prerequisite, action ID or state hash"
                )
            state = advance(state, step.action())
        if problem.target_id not in state.removed:
            raise ValueError("target did not complete a certified staged translation")
        problem.check_integrity()
        return ValidationReport(
            status="passed",
            explanation="Every saved transition independently recomputed against the frozen revision; target staged",
            checked_steps=len(steps),
            certificates=tuple(checked),
            final_removed_ids=tuple(sorted(state.removed)),
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
    except Exception as exc:
        return ValidationReport(
            status="failed",
            explanation=f"{type(exc).__name__}: {exc}",
            checked_steps=len(checked),
            certificates=tuple(checked),
            final_removed_ids=tuple(sorted(state.removed)),
            elapsed_ms=(time.monotonic() - started) * 1000,
        )


def validate_reverse(problem, steps, *, cancel=None):
    started = time.monotonic()
    checked = []
    groups = {"geometric_insertion": [], "fastener_reinsertion": [], "tool_access": []}
    absent = set()
    try:
        # Reconstruct the state from saved operations, not a search-node object.
        forward = State()
        for step in steps:
            if problem.target_id in forward.removed or problem.semantic_reason(
                forward, step.action()
            ):
                raise ValueError("invalid forward action ordering")
            if (
                step.before_state_hash != forward.identity(problem.input_hash)
                or step.start_transform != problem.placements[step.component_id]
                or step.end_transform
                != translated_placement(
                    step.start_transform, step.axis, step.distance_mm
                )
            ):
                raise ValueError("stale reverse movement inputs")
            forward = advance(forward, step.action())
            if step.after_state_hash != forward.identity(problem.input_hash):
                raise ValueError("invalid after-state")
        absent = set(forward.removed)
        if problem.target_id not in absent:
            raise ValueError("no complete target-removal route to reverse")
        validator = ActionValidator(problem)
        last_tool = None
        for step in reversed(steps):
            if cancel is not None and cancel.is_set():
                raise EngineError("CANCELLED", "reverse validation cancelled")
            k = step.component_id
            if k not in absent:
                raise ValueError("duplicate or reordered inverse action")
            if step.kind == "REMOVE_FASTENER":
                screw = problem.screws[k]
                if absent.intersection(
                    (*screw.retained_component_ids, screw.host_component_id)
                ):
                    raise ValueError(
                        "fastener cannot be installed before its host and retained components"
                    )
            state = State(frozenset(absent - {k}), last_tool)
            result = validator.evaluate(state, step.action(), insertion=True)
            if result.certificate:
                checked.append(result.certificate)
                for group, path in zip(
                    result.certificate.subchecks, result.certificate.paths
                ):
                    groups[group].append(path.status.value)
            if result.status != "clear":
                return reverse_report(
                    "unknown" if result.status == "unknown" else "failed",
                    result.rejection.reason,
                    checked,
                    absent,
                    groups,
                    started,
                )
            absent.remove(k)
            if step.tool_id:
                last_tool = step.tool_id
        if absent or connections(problem.manifest, State()) != connections(
            problem.manifest, State(frozenset(absent))
        ):
            raise ValueError("assembled connection state not restored")
        problem.check_integrity()
        return reverse_report(
            "passed",
            "All inverse translations, screw insertion and modeled tool access rechecked; initial connections restored",
            checked,
            absent,
            groups,
            started,
        )
    except Exception as exc:
        return reverse_report(
            "failed", f"{type(exc).__name__}: {exc}", checked, absent, groups, started
        )


def reverse_report(status, explanation, checked, absent, groups, started):
    def aggregate(values):
        return (
            "not_applicable"
            if not values
            else "failed"
            if "blocked" in values
            else "passed"
            if all(x == "clear" for x in values)
            else "unknown"
        )

    return ValidationReport(
        status=status,
        explanation=explanation,
        checked_steps=len(checked),
        certificates=tuple(checked),
        final_removed_ids=tuple(sorted(absent)),
        connection_restoration="passed"
        if status == "passed" and not absent
        else "failed"
        if status == "failed"
        else "unknown",
        elapsed_ms=(time.monotonic() - started) * 1000,
        **{k: aggregate(v) for k, v in groups.items()},
    )
