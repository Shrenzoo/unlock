"""Server-owned bridge constructor and two bounded, occurrence-local interventions."""

from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq

from .contracts import Binding, Box, EngineError, Model, POLICY, Positive
from .geometry import (
    boolean,
    box_shape,
    cover,
    difference_volume,
    same_geometry,
    validate_solid,
    volume,
)


SERVER_DOMAINS = {
    "T01": dict(
        center_x_mm=(-4.0, 0.0, 4.0),
        center_y_mm=(-24.0, -20.0, -16.0, 0.0),
        width_mm=(24.0, 40.0, 46.0, 52.0),
        depth_mm=(8.0, 12.0, 16.0, 20.0),
    ),
    "T02": dict(offset_y_mm=(-12.0, 12.0, 24.0, 36.0)),
}


class Relief(Model):
    center_x_mm: float
    center_y_mm: float
    width_mm: Positive
    depth_mm: Positive


class Offset(Model):
    offset_y_mm: float


@dataclass(frozen=True)
class Bracket:
    shape: cq.Shape
    protected: tuple[cq.Shape, ...]
    web: Box
    proxies: tuple[Box, ...]
    holes: tuple[tuple[float, float, float], ...]


def construct(
    binding: Binding, *, relief: Relief | None = None, offset: float = 0.0
) -> Bracket:
    p = binding.parameters
    if (
        p.hole_diameter_mm
        >= min(p.foot_width_mm, p.foot_depth_mm) - 2 * POLICY.tolerance_mm
    ):
        raise EngineError("CONSTRAINT_VIOLATION", "hole consumes mounting foot")
    if (
        p.web_underside_height_mm <= p.foot_thickness_mm
        or p.post_width_mm >= p.foot_width_mm / 2 - p.hole_diameter_mm / 2
    ):
        raise EngineError(
            "CONSTRAINT_VIOLATION",
            "posts must leave centered mounting hole unobstructed",
        )
    foot_in = p.span_mm / 2 - p.foot_width_mm / 2
    if (
        p.web_length_mm / 2 < foot_in + p.post_width_mm
        or p.post_depth_mm > p.foot_depth_mm
    ):
        raise EngineError(
            "CONSTRAINT_VIOLATION",
            "web must span complete protected posts; posts must fit feet",
        )
    solids = []
    protected = []
    proxies = []
    holes = []
    posts = []
    for sign in (-1, 1):
        x = sign * p.span_mm / 2
        fb = Box(
            min=(x - p.foot_width_mm / 2, -p.foot_depth_mm / 2, 0),
            max=(x + p.foot_width_mm / 2, p.foot_depth_mm / 2, p.foot_thickness_mm),
        )
        foot = box_shape(fb)
        hole = cq.Solid.makeCylinder(
            p.hole_diameter_mm / 2, p.foot_thickness_mm, pnt=cq.Vector(x, 0, 0)
        )
        foot = boolean("cut", foot, hole)
        px0 = foot_in if sign > 0 else -foot_in - p.post_width_mm
        pb = Box(
            min=(px0, -p.post_depth_mm / 2, p.foot_thickness_mm),
            max=(px0 + p.post_width_mm, p.post_depth_mm / 2, p.web_underside_height_mm),
        )
        post = box_shape(pb)
        solids.extend((foot, post))
        protected.extend((foot, post))
        proxies.extend((fb, pb))
        holes.append((x, 0.0, 0.0))
        posts.append(pb)
    z = p.web_underside_height_mm
    web = Box(
        min=(-p.web_length_mm / 2, -p.web_depth_mm / 2 + offset, z),
        max=(p.web_length_mm / 2, p.web_depth_mm / 2 + offset, z + p.web_thickness_mm),
    )
    if relief:
        cut = Box(
            min=(
                relief.center_x_mm - relief.width_mm / 2,
                relief.center_y_mm - relief.depth_mm / 2,
                z,
            ),
            max=(
                relief.center_x_mm + relief.width_mm / 2,
                relief.center_y_mm + relief.depth_mm / 2,
                z + p.web_thickness_mm,
            ),
        )
        if not web.contains(cut):
            raise EngineError(
                "CONSTRAINT_VIOLATION", "relief lies outside editable web"
            )
        xmin, ymin, _ = web.min
        xmax, ymax, _ = web.max
        a, b, _ = cut.min
        c, d, _ = cut.max
        if min(a - xmin, xmax - c, b - ymin, ymax - d) < binding.minimum_web_mm:
            raise EngineError("CONSTRAINT_VIOLATION", "minimum remaining web violated")
        if (
            relief.width_mm * relief.depth_mm * p.web_thickness_mm
            > binding.maximum_cut_volume_mm3
        ):
            raise EngineError("CONSTRAINT_VIOLATION", "maximum relief volume exceeded")
        for protected_shape in protected:
            if (
                volume(boolean("common", protected_shape, box_shape(cut)))
                > POLICY.volume_noise_mm3
            ):
                raise EngineError(
                    "CONSTRAINT_VIOLATION", "cut touches protected feet, posts or holes"
                )
        wb = (
            Box(min=web.min, max=(xmax, b, web.max[2])),
            Box(min=(xmin, d, z), max=web.max),
            Box(min=(xmin, b, z), max=(a, d, web.max[2])),
            Box(min=(c, b, z), max=(xmax, d, web.max[2])),
        )
        # Actual Boolean change, not a presentation decomposition.
        websolid = boolean("cut", box_shape(web), box_shape(cut))
        solids.append(websolid)
        proxies.extend(wb)
    else:
        solids.append(box_shape(web))
        proxies.append(web)
    if offset:
        for pb in posts:
            link = Box(
                min=(pb.min[0], min(pb.min[1], web.min[1]), z),
                max=(pb.max[0], max(pb.max[1], web.max[1]), web.max[2]),
            )
            solids.append(box_shape(link))
            proxies.append(link)
    shape = solids[0]
    for s in solids[1:]:
        shape = boolean("fuse", shape, s)
    validate_solid(shape)
    if not cover(shape, tuple(proxies)):
        raise EngineError("GEOMETRY_FAILED", "constructor proxy coverage failed")
    return Bracket(shape, tuple(protected), web, tuple(proxies), tuple(holes))


def admit(binding: Binding, template_id: str, parameters: dict):
    if template_id not in SERVER_DOMAINS:
        raise EngineError("UNSUPPORTED_TEMPLATE", "unknown trusted template")
    spec = next((s for s in binding.templates if s.id == template_id), None)
    if spec is None:
        raise EngineError(
            "UNSUPPORTED_TEMPLATE", "template not enabled for this binding"
        )
    params = (Relief if template_id == "T01" else Offset).model_validate(parameters)
    for key, value in params.model_dump().items():
        if value not in SERVER_DOMAINS[template_id][
            key
        ] or value not in spec.domain.get(key, ()):
            raise EngineError(
                "CONSTRAINT_VIOLATION",
                f"{key}={value} not in server/binding finite domain",
            )
    return params


def modify(
    original_local: cq.Shape, binding: Binding, template_id: str, parameters: dict
) -> Bracket:
    expected = construct(binding)
    validate_solid(original_local)
    if not same_geometry(original_local, expected.shape):
        raise EngineError(
            "UNSUPPORTED_TEMPLATE",
            "imported solid does not match bridge_bracket_v1 constructor and protected geometry",
        )
    params = admit(binding, template_id, parameters)
    candidate = construct(
        binding,
        relief=params if template_id == "T01" else None,
        offset=params.offset_y_mm if template_id == "T02" else 0.0,
    )
    if difference_volume(original_local, candidate.shape) <= POLICY.volume_noise_mm3:
        raise EngineError("CONSTRAINT_VIOLATION", "empty modification")
    for region in expected.protected:
        if not same_geometry(
            boolean("common", original_local, region),
            boolean("common", candidate.shape, region),
        ):
            raise EngineError("CONSTRAINT_VIOLATION", "protected material changed")
    return candidate
