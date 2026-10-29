"""Straight screwdriver shaft/handle volumes and separately checked screw extraction."""

import cadquery as cq

from .contracts import (
    EngineError,
    POLICY,
    Region,
    Screw,
    Seat,
    Status,
    Tool,
    axis_vector,
)
from .geometry import boolean, bounds, validate_solid
from .motion import Contact, validate_translation


def tool_solid(tool: Tool, head_origin_mm):
    direction = cq.Vector(*axis_vector(tool.permitted_axis))
    origin = cq.Vector(*head_origin_mm)
    shaft = cq.Solid.makeCylinder(
        tool.shaft_radius_mm, tool.shaft_length_mm, origin, direction
    )
    handle = cq.Solid.makeCylinder(
        tool.handle_radius_mm,
        tool.handle_length_mm,
        origin + direction * tool.shaft_length_mm,
        direction,
    )
    shape = boolean("fuse", shaft, handle)
    validate_solid(shape)
    return shape


def tool_approach(
    tool: Tool,
    screw: Screw,
    obstacles: dict,
    engagement: Region,
    *,
    clearance_mm=POLICY.clearance_mm,
    obstacle_boxes=None,
):
    if (
        engagement.id != screw.engagement_region_id
        or engagement.component_id != screw.fastener_id
        or engagement.kind != "engagement"
    ):
        raise EngineError(
            "UNSUPPORTED_SEMANTICS", "named engagement must belong to this fastener"
        )
    v = axis_vector(tool.permitted_axis)
    k = "XYZ".index(tool.permitted_axis[0])
    if (
        tuple(screw.axis_world) != v
        or engagement.plane_axis != tool.permitted_axis[0]
        or engagement.plane_coordinate_mm != screw.head_origin_mm[k]
    ):
        raise EngineError(
            "UNSUPPORTED_SEMANTICS",
            "tool, head and engagement plane must share the declared world axis",
        )
    if screw.fastener_id not in obstacles:
        raise EngineError("INVALID_MANIFEST", "engaged fastener is absent")
    shape = tool_solid(tool, screw.head_origin_mm)
    # Reverse the complete approach segment. Occupied volumes are identical in either
    # traversal direction; half spaces establish only the declared terminal contact.
    tr = Region(
        id="tool_tip_volume",
        component_id="tool",
        kind="contact",
        bounds_mm=bounds(shape).inflate(POLICY.tolerance_mm),
        plane_axis=engagement.plane_axis,
        plane_coordinate_mm=engagement.plane_coordinate_mm,
    )
    er = engagement.model_copy(update={"kind": "contact"})
    seat = Seat(
        id=screw.engagement_region_id,
        kind="planar_seat",
        component_a_id="tool",
        component_b_id=screw.fastener_id,
        region_a_id=tr.id,
        region_b_id=er.id,
        outward_normal_world=v,
    )
    return validate_translation(
        "tool",
        shape,
        obstacles,
        tool.permitted_axis,
        tool.approach_distance_mm,
        clearance_mm,
        contacts={screw.fastener_id: Contact(seat, tr, er)},
        obstacle_boxes=obstacle_boxes,
    )


def evaluate_fastener(
    tool: Tool,
    screw: Screw,
    fastener: cq.Shape,
    obstacles: dict,
    engagement: Region,
    *,
    clearance_mm=POLICY.clearance_mm,
    obstacle_boxes=None,
    on_geometry_call=None,
):
    if on_geometry_call:
        on_geometry_call()
    access = tool_approach(
        tool,
        screw,
        {**obstacles, screw.fastener_id: fastener},
        engagement,
        clearance_mm=clearance_mm,
        obstacle_boxes=obstacle_boxes,
    )
    if on_geometry_call:
        on_geometry_call()
    extraction = validate_translation(
        screw.fastener_id,
        fastener,
        obstacles,
        tool.permitted_axis,
        screw.extraction_distance_mm,
        clearance_mm,
        obstacle_boxes=obstacle_boxes,
    )
    status = (
        Status.BLOCKED
        if Status.BLOCKED in (access.status, extraction.status)
        else Status.CLEAR
        if access.status == extraction.status == Status.CLEAR
        else Status.UNKNOWN
    )
    return dict(
        status=status,
        tool_access=access,
        extraction=extraction,
        assumptions="Reusable screw; rotation, torque, threads and host release are semantic abstractions, not physical simulations",
    )
