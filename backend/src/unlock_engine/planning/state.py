"""Pure state transitions and sequence-derived metrics, independent of search."""

from ..contracts import Screw, Seat, axis_vector, digest
from .contracts import Action, Metrics, State, Step


def connections(manifest, state: State):
    result = []
    for c in sorted(manifest.connections, key=lambda x: x.id):
        if isinstance(c, Screw):
            value = "released" if c.fastener_id in state.removed else "engaged"
        elif isinstance(c, Seat):
            value = (
                "separated"
                if {c.component_a_id, c.component_b_id} & state.removed
                else "seated"
            )
        result.append((c.id, value))
    return tuple(result)


def advance(state: State, action: Action) -> State:
    if action.component_id in state.removed:
        raise ValueError("occurrence already removed")
    return State(
        state.removed | {action.component_id},
        action.tool_id if action.kind == "REMOVE_FASTENER" else state.last_tool,
    )


def add_cost(cost, state, action, target_id):
    fastener = action.kind == "REMOVE_FASTENER"
    return (
        cost[0] + int(not fastener and action.component_id != target_id),
        cost[1] + int(fastener),
        cost[2]
        + int(
            fastener
            and state.last_tool is not None
            and state.last_tool != action.tool_id
        ),
        cost[3] + 1,
    )


def translated_placement(placement, axis, distance):
    m = list(placement.matrix)
    for k, v in enumerate(axis_vector(axis)):
        m[4 * k + 3] += v * distance
    return placement.model_copy(update={"matrix": tuple(m)})


def make_step(problem, state, action, certificate):
    after = advance(state, action)
    data = dict(
        kind=action.kind,
        component_id=action.component_id,
        prerequisite_ids=problem.prerequisites(action.component_id),
        tool_id=action.tool_id,
        start_transform=problem.placements[action.component_id],
        end_transform=translated_placement(
            problem.placements[action.component_id], action.axis, action.distance_mm
        ),
        axis=action.axis,
        distance_mm=action.distance_mm,
        certificate_ids=(certificate.id,),
        before_state_hash=state.identity(problem.input_hash),
        after_state_hash=after.identity(problem.input_hash),
    )
    return Step(action_id=digest(data), **data)


def metrics(steps, certificates, target_id):
    state = State()
    cost = (0, 0, 0, 0)
    tools = set()
    for step in steps:
        a = step.action()
        cost = add_cost(cost, state, a, target_id)
        state = advance(state, a)
        if a.tool_id:
            tools.add(a.tool_id)
    paths = [p for c in certificates for p in c.paths]
    gaps = [p.clearance_lower_bound_mm for p in paths]
    return Metrics(
        unrelated_parts_removed=cost[0],
        fasteners_removed=cost[1],
        tool_changes=cost[2],
        operations=cost[3],
        unique_tools=len(tools),
        cost=cost,
        noncontact_clearance_lower_bound_mm=min(gaps)
        if gaps and all(g is not None for g in gaps)
        else None,
        has_contact_exemptions=any(p.contact_exemptions for p in paths),
    )
