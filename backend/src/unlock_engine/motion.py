"""Continuous axis translation: only analytic, validated coverage can admit a path."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq

from .contracts import (
    Axis,
    Box,
    Finding,
    Model,
    POLICY,
    Region,
    Seat,
    Status,
    axis_vector,
    digest,
)
from .geometry import (
    boolean,
    bounds,
    box_shape,
    collision,
    fingerprint,
    material_boxes,
    validate_solid,
    volume,
)


class PathResult(Model):
    id: str
    moving_occurrence: str
    axis: Axis
    distance_mm: float
    status: Status
    policy_version: str = POLICY.version
    geometry_hash: str
    input_hash: str
    clearance_mm: float
    representation: str = "server_validated_world_aabb_union"
    coverage_established: bool
    findings: tuple[Finding, ...]
    contact_exemptions: tuple[str, ...] = ()
    clearance_lower_bound_mm: float | None = None
    explanation: str


@dataclass(frozen=True)
class Contact:
    declaration: Seat
    moving_region: Region
    obstacle_region: Region


def overlap_interval(
    a: Box, b: Box, axis: Axis, length: float, gap: float
) -> tuple[float, float] | None:
    """Travel interval for box overlap, including threshold boundaries; never samples."""
    index = "XYZ".index(axis[0])
    sign = axis_vector(axis)[index]
    b = b.inflate(gap)
    for k in range(3):
        if k != index and (a.max[k] < b.min[k] or b.max[k] < a.min[k]):
            return None
    low = (b.min[index] - a.max[index]) / sign
    high = (b.max[index] - a.min[index]) / sign
    if sign < 0:
        low, high = high, low
    low = max(0.0, low)
    high = min(length, high)
    return (low, high) if low <= high else None


def split_contact(moving: cq.Shape, obstacle: cq.Shape, c: Contact, axis: Axis):
    """Narrow supported contact: named, axis-planar, independently isolated material."""
    from .contracts import EngineError

    d = c.declaration
    a = c.moving_region
    b = c.obstacle_region
    if a.kind != "contact" or b.kind != "contact":
        raise EngineError(
            "UNSUPPORTED_SEMANTICS", "contact regions must be declared contact volumes"
        )
    normal = axis_vector(axis)
    if tuple(d.outward_normal_world) != normal:
        raise EngineError(
            "CONSTRAINT_VIOLATION", "motion is not the declared separating normal"
        )
    k = "XYZ".index(axis[0])
    sign = normal[k]
    if (
        a.plane_axis != axis[0]
        or b.plane_axis != axis[0]
        or a.plane_coordinate_mm is None
        or a.plane_coordinate_mm != b.plane_coordinate_mm
    ):
        raise EngineError(
            "UNSUPPORTED_SEMANTICS",
            "matching axis-aligned named contact planes required",
        )
    p = a.plane_coordinate_mm
    ma = boolean("common", moving, box_shape(a.bounds_mm))
    ob = boolean("common", obstacle, box_shape(b.bounds_mm))
    if not ma.Solids() or not ob.Solids():
        raise EngineError("UNSUPPORTED_SEMANTICS", "empty contact material")
    ba = bounds(ma)
    bb = bounds(ob)
    # No tolerance-wide penetrations are exempted. Actual common is checked too.
    e = POLICY.contact_plane_noise_mm
    if (sign > 0 and (ba.min[k] < p - e or bb.max[k] > p + e)) or (
        sign < 0 and (ba.max[k] > p + e or bb.min[k] < p - e)
    ):
        raise EngineError(
            "UNSUPPORTED_SEMANTICS",
            "contact material is not isolated into opposing closed half spaces",
        )
    if volume(boolean("common", moving, obstacle)) > POLICY.volume_noise_mm3:
        raise EngineError(
            "CONSTRAINT_VIOLATION", "undeclared initial penetration cannot be exempted"
        )

    # Solid/solid Common deliberately returns no material for a tangent pair.
    # Check matching planar boundary faces directly instead of interpreting that
    # empty solid common as either contact or separation.
    def plane_faces(shape):
        return [
            f
            for f in shape.Faces()
            if f.geomType() == "PLANE"
            and abs(f.Center().toTuple()[k] - p) <= e
            and abs(abs(f.normalAt().toTuple()[k]) - 1) <= e
        ]

    contact_area = sum(
        f.Area()
        for fa in plane_faces(ma)
        for fb in plane_faces(ob)
        for f in boolean("common", fa, fb).Faces()
    )
    if contact_area <= POLICY.contact_area_noise_mm2:
        raise EngineError(
            "UNSUPPORTED_SEMANTICS",
            "named regions do not share a planar material contact",
        )
    # Half-space proof applies ONLY to ma versus ob. Every other material pair remains active.
    mr = boolean("cut", moving, box_shape(a.bounds_mm))
    br = boolean("cut", obstacle, box_shape(b.bounds_mm))
    return ma, mr, ob, br


def validate_translation(
    moving_id: str,
    moving: cq.Shape,
    obstacles: dict[str, cq.Shape],
    axis: Axis,
    distance_mm: float,
    clearance_mm: float = POLICY.clearance_mm,
    *,
    moving_boxes=None,
    obstacle_boxes=None,
    contacts: dict[str, Contact] | None = None,
    terminal_contacts: dict[str, Contact] | None = None,
) -> PathResult:
    axis_vector(axis)
    contacts = contacts or {}
    terminal_contacts = terminal_contacts or {}
    obstacle_boxes = obstacle_boxes or {}
    input_data = dict(
        moving=moving_id,
        geometry=fingerprint(moving),
        obstacles={k: fingerprint(v) for k, v in sorted(obstacles.items())},
        axis=axis,
        distance=distance_mm if math.isfinite(distance_mm) else str(distance_mm),
        clearance=clearance_mm if math.isfinite(clearance_mm) else str(clearance_mm),
        policy=POLICY.model_dump(),
        contacts={
            k: dict(
                declaration=v.declaration.model_dump(),
                a=v.moving_region.model_dump(),
                b=v.obstacle_region.model_dump(),
            )
            for k, v in sorted(contacts.items())
        },
        terminal_contacts={
            k: dict(
                declaration=v.declaration.model_dump(),
                a=v.moving_region.model_dump(),
                b=v.obstacle_region.model_dump(),
            )
            for k, v in sorted(terminal_contacts.items())
        },
        moving_boxes=[x.model_dump() for x in moving_boxes] if moving_boxes else None,
        obstacle_boxes={
            k: [x.model_dump() for x in v] for k, v in obstacle_boxes.items()
        },
    )
    ih = digest(input_data)
    findings = []
    exemptions = []
    coverage = False

    def result(status, explanation):
        data = dict(
            moving_occurrence=moving_id,
            axis=axis,
            distance_mm=distance_mm if math.isfinite(distance_mm) else 0.0,
            status=status,
            geometry_hash=input_data["geometry"],
            input_hash=ih,
            clearance_mm=clearance_mm if math.isfinite(clearance_mm) else 0.0,
            coverage_established=coverage,
            findings=tuple(findings),
            contact_exemptions=tuple(exemptions),
            explanation=explanation,
            clearance_lower_bound_mm=clearance_mm
            if status == Status.CLEAR and not exemptions
            else None,
        )
        return PathResult(id=digest(data), **data)

    if (
        not math.isfinite(distance_mm)
        or distance_mm <= 0
        or not math.isfinite(clearance_mm)
        or clearance_mm < 0
    ):
        return result(
            Status.INVALID,
            "positive finite travel and nonnegative finite clearance required",
        )
    try:
        validate_solid(moving)
        moving_proxy = material_boxes(moving, moving_boxes)
        for oid, obstacle in sorted(obstacles.items()):
            validate_solid(obstacle)
            pairs = []
            if oid in contacts or oid in terminal_contacts:
                try:
                    if oid in contacts and oid in terminal_contacts:
                        raise ValueError(
                            "a pair cannot declare both start and terminal contact"
                        )
                    terminal = oid in terminal_contacts
                    contact = terminal_contacts[oid] if terminal else contacts[oid]
                    delta = tuple(x * distance_mm for x in axis_vector(axis))
                    split_shape = moving.translate(delta) if terminal else moving
                    separating_axis = (
                        axis[0] + ("-" if axis[1] == "+" else "+") if terminal else axis
                    )
                    ma, mr, ob, br = split_contact(
                        split_shape, obstacle, contact, separating_axis
                    )
                    if terminal:
                        # Prove opposing half spaces at the assembled END pose.
                        # The isolated contact pair closes without penetration;
                        # all other material pairs still sweep from their actual
                        # insertion-start placements below.
                        ma = ma.translate(tuple(-x for x in delta))
                        mr = mr.translate(tuple(-x for x in delta))
                except Exception as exc:
                    # A real collision witness remains decisive even with invalid contact metadata.
                    f = collision(moving, obstacle, clearance_mm, (moving_id, oid))
                    if f.kind == "positive_volume_intersection":
                        findings.append(f)
                    else:
                        findings.append(
                            Finding(
                                status=Status.UNKNOWN,
                                kind="unsupported_contact",
                                component_ids=(moving_id, oid),
                                explanation=str(exc),
                            )
                        )
                    continue
                exemptions.append(contact.declaration.id)
                for a, b in ((ma, br), (mr, ob), (mr, br)):
                    for sa in a.Solids():
                        for sb in b.Solids():
                            pairs.append(
                                (sa, sb, material_boxes(sa), material_boxes(sb))
                            )
            else:
                pairs.append(
                    (
                        moving,
                        obstacle,
                        moving_proxy,
                        material_boxes(obstacle, obstacle_boxes.get(oid)),
                    )
                )
            for a, b, pa, pb in pairs:
                intervals = [
                    interval
                    for ba in pa
                    for bb in pb
                    if (
                        interval := overlap_interval(
                            ba,
                            bb,
                            axis,
                            distance_mm,
                            clearance_mm + POLICY.tolerance_mm,
                        )
                    )
                    is not None
                ]
                if not intervals:
                    continue
                poses = {0.0, distance_mm}
                for lo, hi in intervals:
                    poses.update((lo, hi, (lo + hi) / 2))
                # Extra BRep witness candidates help with thin features inside a
                # coarse union box. These bounded queries can only reject a move;
                # they never contribute to a clear certificate.
                k = "XYZ".index(axis[0])
                sign = axis_vector(axis)[k]
                moving_center = (bounds(a).min[k] + bounds(a).max[k]) / 2
                for face in b.Faces()[:64]:
                    travel = (face.Center().toTuple()[k] - moving_center) / sign
                    if 0 <= travel <= distance_mm:
                        poses.add(travel)
                witness = None
                for travel in sorted(poses):
                    v = tuple(x * travel for x in axis_vector(axis))
                    f = collision(a.translate(v), b, clearance_mm, (moving_id, oid))
                    if f.status == Status.BLOCKED:
                        witness = f.model_copy(update={"witness_travel_mm": travel})
                        break
                findings.append(
                    witness
                    or Finding(
                        status=Status.UNKNOWN,
                        kind="conservative_proxy_overlap",
                        component_ids=(moving_id, oid),
                        explanation="Continuous proxy intervals overlap; tested BRep poses provide no decisive obstruction witness",
                    )
                )
        coverage = True
    except Exception as exc:
        findings.append(
            Finding(
                status=Status.UNKNOWN,
                kind="coverage_or_kernel_failure",
                component_ids=(moving_id,),
                explanation=str(exc),
            )
        )
        return result(Status.UNKNOWN, "Coverage or native geometry operation failed")
    if any(f.status == Status.BLOCKED for f in findings):
        return result(
            Status.BLOCKED,
            "A BRep obstruction or insufficient-clearance witness rejects this segment",
        )
    if findings:
        return result(
            Status.UNKNOWN,
            "Conservative representation or contact evidence could not establish a clear segment",
        )
    return result(
        Status.CLEAR,
        "All nonexempt material proxy pairs remain separated for the entire analytic segment; named terminal contacts close without penetration in opposing half spaces"
        if terminal_contacts
        else "All nonexempt material proxy pairs remain separated for the entire analytic segment; contact pairs separate in opposing half spaces",
    )
