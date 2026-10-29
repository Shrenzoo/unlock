"""Semantic pruning, authoritative CAD calls, geometry-aware certificate caching."""

from dataclasses import dataclass

from ..contracts import Status, axis_vector, digest
from ..motion import validate_translation
from ..tools import evaluate_fastener, tool_approach
from .contracts import Certificate, Rejection


@dataclass(frozen=True)
class Evaluation:
    status: str
    certificate: Certificate | None = None
    rejection: Rejection | None = None


class ActionValidator:
    def __init__(self, problem, cache=None):
        self.problem = problem
        self.cache = {} if cache is None else cache
        self.hits = self.misses = self.geometry_calls = 0

    def geometry_call(self):
        self.geometry_calls += 1

    def reject(self, state, action, reason, category, certificate=None):
        p = self.problem
        data = dict(
            revision_id=p.revision_id,
            state_hash=state.identity(p.input_hash),
            removed_ids=tuple(sorted(state.removed)),
            action=action,
            remaining_obstacle_ids=tuple(
                sorted(p.obstacles(state, action.component_id))
            ),
            constraint_ids=tuple(sorted(c.id for c in p.manifest.constraints)),
            reason=reason,
            category=category,
            geometry_evidence_level="semantic"
            if certificate is None
            else "actual_brep_witness"
            if category
            in (
                "CONFIRMED_GEOMETRIC_OBSTRUCTION",
                "INSUFFICIENT_CLEARANCE",
                "TOOL_ACCESS_BLOCKED",
            )
            else "unresolved",
            witness_certificate_ids=(certificate.id,) if certificate else (),
        )
        rejection = Rejection(id=digest(data), **data)
        return Evaluation(
            "unknown" if category == "UNKNOWN_GEOMETRY" else "rejected",
            certificate,
            rejection,
        )

    def evaluate(self, state, action, *, insertion=False):
        p = self.problem
        # State here is the removal-side state (before removal / after insertion).
        # Reverse validation additionally checks currently absent/present IDs.
        reason = p.semantic_reason(state, action)
        if reason:
            return self.reject(state, action, *reason)
        p.check_integrity()
        mode = "insertion" if insertion else "removal"
        key = digest(
            [
                p.input_hash,
                p.geometry_hash,
                p.constraint_hash,
                p.tool_hash,
                p.policy_hash,
                sorted(state.removed),
                state.last_tool,
                action,
                mode,
            ]
        )
        if key in self.cache:
            cached = self.cache[key]
            # The cache only contains certificates constructed here; guard
            # accidental corruption or cross-context injection as well.
            if cached.id != digest(cached.model_dump(exclude={"id"})):
                raise ValueError("corrupt transition cache")
            self.hits += 1
            return self.classify(state, action, cached)
        self.misses += 1
        obstacles = p.obstacles(state, action.component_id)
        paths, checks = (), ()
        try:
            moving = p.shapes[action.component_id]
            boxes = {k: v for k, v in p.proxies.items() if k in obstacles}
            contacts = {
                k: v
                for k, v in p.contacts[action.component_id].items()
                if k in obstacles
            }
            if action.kind == "REMOVE_FASTENER":
                screw = p.screws[action.component_id]
                tool, engagement = (
                    p.tools[screw.tool_id],
                    p.regions[screw.engagement_region_id],
                )
                if insertion:
                    self.geometry_call()
                    access = tool_approach(
                        tool,
                        screw,
                        {**obstacles, action.component_id: moving},
                        engagement,
                        clearance_mm=p.clearance(action.component_id),
                        obstacle_boxes=boxes,
                    )
                    delta = tuple(
                        x * action.distance_mm for x in axis_vector(action.axis)
                    )
                    self.geometry_call()
                    path = validate_translation(
                        action.component_id,
                        moving.translate(delta),
                        obstacles,
                        opposite(action.axis),
                        action.distance_mm,
                        p.clearance(action.component_id),
                        obstacle_boxes=boxes,
                    )
                    paths, checks = (
                        (access, path),
                        ("tool_access", "fastener_reinsertion"),
                    )
                else:
                    result = evaluate_fastener(
                        tool,
                        screw,
                        moving,
                        obstacles,
                        engagement,
                        clearance_mm=p.clearance(action.component_id),
                        obstacle_boxes=boxes,
                        on_geometry_call=self.geometry_call,
                    )
                    paths = (result["tool_access"], result["extraction"])
                    checks = ("tool_access", "fastener_extraction")
            else:
                delta = tuple(x * action.distance_mm for x in axis_vector(action.axis))
                self.geometry_call()
                path = validate_translation(
                    action.component_id,
                    moving.translate(delta) if insertion else moving,
                    obstacles,
                    opposite(action.axis) if insertion else action.axis,
                    action.distance_mm,
                    p.clearance(action.component_id),
                    obstacle_boxes=boxes,
                    moving_boxes=tuple(
                        b.translated(delta) for b in p.proxies[action.component_id]
                    )
                    if insertion and action.component_id in p.proxies
                    else p.proxies.get(action.component_id),
                    contacts=None if insertion else contacts,
                    terminal_contacts=contacts if insertion else None,
                )
                paths, checks = (
                    (path,),
                    ("geometric_insertion" if insertion else "continuous_translation",),
                )
            status = (
                "blocked"
                if any(x.status == Status.BLOCKED for x in paths)
                else "clear"
                if paths and all(x.status == Status.CLEAR for x in paths)
                else "unknown"
            )
        except Exception as exc:
            # Native failures are unresolved evidence, never empty space.
            return self.reject(
                state,
                action,
                f"geometry failure: {type(exc).__name__}: {exc}",
                "UNKNOWN_GEOMETRY",
            )
        data = dict(
            revision_id=p.revision_id,
            input_hash=p.input_hash,
            geometry_hash=p.geometry_hash,
            constraint_hash=p.constraint_hash,
            tool_hash=p.tool_hash,
            policy_hash=p.policy_hash,
            before_state_hash=state.identity(p.input_hash),
            action=action,
            mode=mode,
            status=status,
            paths=paths,
            subchecks=checks,
            assumptions=Certificate.model_fields["assumptions"].default,
        )
        certificate = Certificate(id=digest(data), **data)
        self.cache[key] = certificate
        return self.classify(state, action, certificate)

    def classify(self, state, action, certificate):
        if certificate.status == "clear":
            return Evaluation("clear", certificate)
        blocked = [
            (label, path)
            for label, path in zip(certificate.subchecks, certificate.paths)
            if path.status == Status.BLOCKED
        ]
        if not blocked:
            return self.reject(
                state,
                action,
                "; ".join(x.explanation for x in certificate.paths),
                "UNKNOWN_GEOMETRY",
                certificate,
            )
        findings = [
            f
            for _, path in blocked
            for f in path.findings
            if f.status == Status.BLOCKED
        ]
        category = (
            "TOOL_ACCESS_BLOCKED"
            if any(label == "tool_access" for label, _ in blocked)
            else "CONFIRMED_GEOMETRIC_OBSTRUCTION"
            if any(f.kind == "positive_volume_intersection" for f in findings)
            else "INSUFFICIENT_CLEARANCE"
        )
        return self.reject(
            state,
            action,
            "; ".join(f.explanation for f in findings),
            category,
            certificate,
        )


def opposite(axis):
    return axis[0] + ("-" if axis[1] == "+" else "+")
