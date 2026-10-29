import math

import cadquery as cq
import pytest

from unlock_engine.contracts import (
    Box,
    EngineError,
    POLICY,
    Region,
    Seat,
    Status,
    Transform,
)
from unlock_engine.geometry import (
    boolean,
    bounds,
    collision,
    cover,
    difference_volume,
    fingerprint,
    inverse,
    transform,
    validate_solid,
)
from unlock_engine.motion import Contact, validate_translation


def cube(x=0, y=0, z=0, size=2):
    return cq.Solid.makeBox(size, size, size).translate((x, y, z))


def test_real_solid_and_empty_topology():
    assert validate_solid(cube())["volume_mm3"] == pytest.approx(8)
    with pytest.raises(EngineError):
        validate_solid(cq.Compound.makeCompound([]))
    with pytest.raises(EngineError):
        validate_solid(cq.Face.makePlane(2, 2))
    with pytest.raises(EngineError):
        validate_solid(cq.Compound.makeCompound([cube(), cube(4)]))


@pytest.mark.parametrize(
    "x,status,kind",
    [
        (1, "blocked", "positive_volume_intersection"),
        (2, "blocked", "insufficient_clearance"),
        (2.2, "blocked", "insufficient_clearance"),
        (2.49, "unknown", "numerical_boundary"),
        (2.5, "unknown", "numerical_boundary"),
        (2.51, "unknown", "numerical_boundary"),
        (2.52, "clear", "separated"),
        (5, "clear", "separated"),
    ],
)
def test_analytic_gap_oracle(x, status, kind):
    f = collision(cube(), cube(x))
    assert f.status == status and f.kind == kind
    if x < 2:
        assert f.intersection_volume_mm3 == pytest.approx((2 - x) * 4)


def test_undeclared_tangency_unknown_at_zero_clearance():
    assert collision(cube(), cube(2), 0).status == Status.UNKNOWN


@pytest.mark.parametrize(
    "axis,obstacle",
    [
        ("X+", cube(5)),
        ("X-", cube(-5)),
        ("Y+", cube(y=5)),
        ("Y-", cube(y=-5)),
        ("Z+", cube(z=5)),
        ("Z-", cube(z=-5)),
    ],
)
def test_all_world_axes_intermediate_obstruction(axis, obstacle):
    p = validate_translation("m", cube(), {"hidden": obstacle}, axis, 10)
    assert p.status == Status.BLOCKED
    assert p.findings[0].witness_travel_mm is not None


def test_mandatory_thin_obstacle_between_clear_endpoints():
    m = cube()
    obstacle = cq.Solid.makeBox(0.001, 2, 2).translate((5.123, 0, 0))
    assert collision(m, obstacle).status == Status.CLEAR
    assert collision(m.translate((10, 0, 0)), obstacle).status == Status.CLEAR
    p = validate_translation("m", m, {"thin": obstacle}, "X+", 10)
    assert p.status == Status.BLOCKED
    assert p.findings[0].kind == "positive_volume_intersection"
    assert p.findings[0].intersection_volume_mm3 == pytest.approx(0.004, abs=1e-9)


@pytest.mark.parametrize("x", [0, 10])
def test_initial_and_final_collisions(x):
    assert (
        validate_translation("m", cube(), {"o": cube(x)}, "X+", 10).status
        == Status.BLOCKED
    )


def test_clear_full_segment_and_clearance():
    assert (
        validate_translation("m", cube(), {"o": cube(y=5)}, "X+", 10).status
        == Status.CLEAR
    )
    assert (
        validate_translation("m", cube(), {"o": cube(5, 2.2)}, "X+", 10).status
        == Status.BLOCKED
    )
    assert (
        validate_translation("m", cube(), {"o": cube(5, 2.5)}, "X+", 10).status
        == Status.UNKNOWN
    )


def test_conservative_overlap_is_not_confirmed_collision():
    # L-shaped actual material leaves an empty diagonal corner containing m.
    a = cq.Solid.makeBox(10, 1, 10)
    b = cq.Solid.makeBox(1, 10, 10)
    elbow = boolean("fuse", a, b)
    m = cube(6, 6, 2, size=1)
    p = validate_translation("m", m, {"L": elbow}, "Z+", 2)
    assert p.status == Status.UNKNOWN
    assert all(f.kind != "positive_volume_intersection" for f in p.findings)


def test_unvalidated_proxy_cannot_false_clear():
    m = cube()
    proxy = Box(min=(0, 0, 0), max=(0.5, 0.5, 0.5))
    p = validate_translation(
        "m", m, {"hidden": cube(5)}, "X+", 10, moving_boxes=(proxy,)
    )
    assert p.status == Status.UNKNOWN and not p.coverage_established


def test_tighter_coverage_accepts_empty_corner_without_mesh():
    a = cq.Solid.makeBox(10, 1, 10)
    b = cq.Solid.makeBox(1, 10, 10)
    elbow = boolean("fuse", a, b)
    p = validate_translation(
        "m",
        cube(6, 6, 2, size=1),
        {"L": elbow},
        "Z+",
        2,
        obstacle_boxes={"L": (bounds(a), bounds(b))},
    )
    assert p.status == Status.CLEAR and p.coverage_established


def contact_setup(hidden=False):
    m = cube(z=2)
    base = cq.Solid.makeBox(6, 6, 2).translate((-2, -2, 0))
    if hidden:
        base = boolean("fuse", base, cq.Solid.makeBox(1, 1, 5).translate((0.5, 0.5, 2)))
    a = Region(
        id="a",
        component_id="m",
        kind="contact",
        bounds_mm=Box(min=(0, 0, 2), max=(2, 2, 4)),
        plane_axis="Z",
        plane_coordinate_mm=2,
    )
    b = Region(
        id="b",
        component_id="base",
        kind="contact",
        bounds_mm=Box(min=(-2, -2, 0), max=(4, 4, 2)),
        plane_axis="Z",
        plane_coordinate_mm=2,
    )
    d = Seat(
        id="seat",
        kind="planar_seat",
        component_a_id="m",
        component_b_id="base",
        region_a_id="a",
        region_b_id="b",
        outward_normal_world=(0, 0, 1),
    )
    return m, base, Contact(d, a, b)


def test_separating_contact_checked_geometrically():
    m, b, c = contact_setup()
    p = validate_translation("m", m, {"base": b}, "Z+", 10, contacts={"base": c})
    assert p.status == Status.CLEAR and p.contact_exemptions == ("seat",)
    assert p.clearance_lower_bound_mm is None  # no positive gap promised at contact t=0


def test_inward_contact_not_admitted():
    m, b, c = contact_setup()
    assert (
        validate_translation("m", m, {"base": b}, "Z-", 1, contacts={"base": c}).status
        != Status.CLEAR
    )


def test_undeclared_penetration_in_contact_obstacle():
    m, b, c = contact_setup(True)
    assert (
        validate_translation("m", m, {"base": b}, "Z+", 10, contacts={"base": c}).status
        == Status.BLOCKED
    )


def test_hidden_obstacle_stays_active_with_valid_contact():
    m, b, c = contact_setup()
    p = validate_translation(
        "m", m, {"base": b, "hidden": cube(z=7)}, "Z+", 10, contacts={"base": c}
    )
    assert p.status == Status.BLOCKED


def test_contact_region_cannot_mask_other_material():
    m, b, c = contact_setup()
    # A connected overhanging roof lies above the contact, outside its declared volume.
    b = boolean("fuse", b, cq.Solid.makeBox(1, 6, 8).translate((3, -2, 2)))
    b = boolean("fuse", b, cq.Solid.makeBox(6, 6, 1).translate((-2, -2, 9)))
    p = validate_translation("m", m, {"base": b}, "Z+", 10, contacts={"base": c})
    assert p.status == Status.BLOCKED


@pytest.mark.parametrize(
    "matrix",
    [
        (2.0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        (-1.0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        (1.0, 0.1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        (1.0,) * 15,
    ],
)
def test_reject_unsupported_transforms(matrix):
    with pytest.raises(ValueError):
        Transform(matrix=matrix)


def test_rotations_large_offsets_and_repeated_transforms():
    t = Transform(
        matrix=(0, -1, 0, 1000000, 1, 0, 0, -1000000, 0, 0, 1, 30, 0, 0, 0, 1)
    )
    s = cube()
    world = transform(s, t)
    assert bounds(world).min == pytest.approx((999998, -1000000, 30))
    for _ in range(25):
        world = transform(transform(world, inverse(t)), t)
    assert difference_volume(world, transform(s, t)) <= POLICY.volume_noise_mm3
    assert (
        validate_translation(
            "m", world, {"o": world.translate((10, 0, 0))}, "X+", 20
        ).status
        == Status.BLOCKED
    )


def test_original_brep_immutable_under_checks():
    a = cube()
    b = cube(1)
    h = fingerprint(a)
    collision(a, b)
    boolean("cut", a, b)
    cover(a, (bounds(a),))
    assert fingerprint(a) == h


@pytest.mark.parametrize("distance", [0, -1, math.nan, math.inf])
def test_invalid_motion_distance(distance):
    assert (
        validate_translation("m", cube(), {}, "X+", distance).status == Status.INVALID
    )


def test_kernel_invalid_shape_never_clear():
    assert collision(cq.Compound.makeCompound([]), cube()).status == Status.UNKNOWN


def test_validity_cache_tracks_actual_geometry_and_protects_evidence():
    shape = cube()
    result = validate_solid(shape)
    result["volume_mm3"] = -100
    result["bounds_mm"]["min"] = (999, 999, 999)
    assert validate_solid(shape)["volume_mm3"] == pytest.approx(8)
    assert validate_solid(shape)["bounds_mm"]["min"] == (0, 0, 0)
    shifted = shape.translate((100, 0, 0))
    assert validate_solid(shifted)["bounds_mm"]["min"] == (100, 0, 0)
    shape.wrapped.Nullify()
    with pytest.raises(EngineError):
        validate_solid(shape)
