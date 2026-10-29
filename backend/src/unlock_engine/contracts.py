"""PRD §13/20 contracts. Supplemental geometric metadata is explicit, never inferred."""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def digest(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")

    def encode(obj):
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        raise TypeError(f"not serializable: {type(obj)}")

    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=encode,
        ).encode()
    ).hexdigest()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


Vec3 = tuple[float, float, float]
Positive = Annotated[float, Field(gt=0)]
StrictBool = Annotated[bool, Field(strict=True)]
Axis = Literal["X+", "X-", "Y+", "Y-", "Z+", "Z-"]


def axis_vector(axis: Axis) -> Vec3:
    if axis not in ("X+", "X-", "Y+", "Y-", "Z+", "Z-"):
        raise ValueError("unsupported world axis")
    v = [0.0, 0.0, 0.0]
    v["XYZ".index(axis[0])] = 1.0 if axis[1] == "+" else -1.0
    return tuple(v)


class Status(StrEnum):
    CLEAR = "clear"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid_input"


class Policy(Model):
    version: Literal["policy_v1"] = "policy_v1"
    tolerance_mm: float = 0.01
    clearance_mm: float = 0.5
    volume_noise_mm3: float = 1e-9
    algebraic_tolerance: float = 1e-9
    contact_plane_noise_mm: float = 1e-9
    contact_area_noise_mm2: float = 1e-9
    max_faces: int = 30_000
    max_triangles: int = 200_000
    max_envelope_mm: float = 500
    max_compressed_bytes: int = 25 * 1024 * 1024
    max_expanded_bytes: int = 100 * 1024 * 1024


POLICY = Policy()


class Box(Model):
    min: Vec3
    max: Vec3

    @model_validator(mode="after")
    def ordered(self):
        if any(a >= b for a, b in zip(self.min, self.max)):
            raise ValueError("box requires finite positive extent on every axis")
        return self

    def inflate(self, amount: float) -> Box:
        return Box(
            min=tuple(x - amount for x in self.min),
            max=tuple(x + amount for x in self.max),
        )

    def translated(self, v: Vec3) -> Box:
        return Box(
            min=tuple(a + b for a, b in zip(self.min, v)),
            max=tuple(a + b for a, b in zip(self.max, v)),
        )

    def contains(self, other: Box, guard: float = 0) -> bool:
        return all(
            a + guard <= c and d <= b - guard
            for a, b, c, d in zip(self.min, self.max, other.min, other.max)
        )


IDENTITY = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


class Transform(Model):
    matrix: tuple[float, ...] = IDENTITY

    @model_validator(mode="after")
    def rigid(self):
        m = self.matrix
        if len(m) != 16 or any(not math.isfinite(x) for x in m):
            raise ValueError("row-major transform requires exactly 16 finite numbers")
        e = POLICY.algebraic_tolerance
        if any(abs(a - b) > e for a, b in zip(m[12:], (0, 0, 0, 1))):
            raise ValueError("invalid homogeneous transform")
        rows = [m[i : i + 3] for i in (0, 4, 8)]
        if any(
            abs(sum(a * b for a, b in zip(rows[i], rows[j])) - (i == j)) > e
            for i in range(3)
            for j in range(3)
        ):
            raise ValueError("scale or shear is unsupported")
        a, b, c = rows
        det = (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        )
        if det < 0:
            raise ValueError("reflection is unsupported")
        return self


class Component(Model):
    id: str
    source_occurrence_path: str
    display_name: str
    role: Literal[
        "chassis", "cover", "bracket", "service_module", "electronics", "fastener"
    ]
    fixed: StrictBool
    replaceable: StrictBool
    removal_axes: tuple[Axis, ...]
    staging_region_id: str | None
    fixed_reason: str | None = None
    bounds_mm: Box | None = None
    template_family: Literal["bridge_bracket_v1"] | None = None
    shared_definition: str | None = None
    placement: Transform | None = None

    @model_validator(mode="after")
    def movement(self):
        if self.fixed and (self.replaceable or self.removal_axes):
            raise ValueError(
                "fixed component cannot be replaceable or have removal axes"
            )
        if not self.fixed and (not self.removal_axes or not self.staging_region_id):
            raise ValueError(
                "removable component requires removal_axes and staging_region_id"
            )
        return self


class Tool(Model):
    id: str
    type: Literal["screwdriver"]
    tip_type: str
    shaft_radius_mm: Positive
    shaft_length_mm: Positive
    handle_radius_mm: Positive
    handle_length_mm: Positive
    approach_distance_mm: Positive
    permitted_axis: Axis


class Screw(Model):
    id: str
    kind: Literal["screw_retainer"]
    fastener_id: str
    retained_component_ids: tuple[str, ...] = Field(min_length=1)
    host_component_id: str
    tool_id: str
    axis_world: Vec3
    head_origin_mm: Vec3
    extraction_distance_mm: Positive
    engagement_region_id: str


class Seat(Model):
    id: str
    kind: Literal["planar_seat"]
    component_a_id: str
    component_b_id: str
    region_a_id: str
    region_b_id: str
    outward_normal_world: Vec3


Connection = Annotated[Screw | Seat, Field(discriminator="kind")]


class Region(Model):
    id: str
    component_id: str
    kind: Literal["contact", "engagement", "protected", "editable"]
    bounds_mm: Box
    plane_axis: Literal["X", "Y", "Z"] | None = None
    plane_coordinate_mm: float | None = None


class Stage(Model):
    id: str
    bounds_mm: Box


class BracketParameters(Model):
    span_mm: Positive
    foot_width_mm: Positive
    foot_depth_mm: Positive
    foot_thickness_mm: Positive
    hole_diameter_mm: Positive
    post_width_mm: Positive
    post_depth_mm: Positive
    web_length_mm: Positive
    web_depth_mm: Positive
    web_thickness_mm: Positive
    web_underside_height_mm: Positive


class Template(Model):
    id: Literal["T01", "T02"]
    label: str
    domain: dict[str, tuple[float, ...]]


class Binding(Model):
    bracket_id: str
    family: Literal["bridge_bracket_v1"]
    parameters: BracketParameters
    editable_region_id: str
    templates: tuple[Template, ...]
    minimum_web_mm: Positive
    maximum_cut_volume_mm3: Positive
    constructor_version: Literal["1"] = "1"


class Constraint(Model):
    id: str
    mandatory: StrictBool
    kind: Literal[
        "fixed_geometry",
        "protected_region",
        "hole_axis",
        "envelope",
        "keep_out",
        "clearance",
        "template_bound",
    ]
    label: str
    component_ids: tuple[str, ...]
    limit: str
    threshold_mm: float | None = Field(default=None, ge=0)
    scope: Literal["pair", "path"] | None = None
    axis: Axis | None = None
    distance_mm: Positive | None = None
    region_ids: tuple[str, ...] = ()


class KeepOut(Model):
    id: str
    label: str
    min_mm: Vec3
    max_mm: Vec3

    def box(self):
        return Box(min=self.min_mm, max=self.max_mm)


class Provenance(Model):
    author: str = Field(min_length=1)
    license: str = Field(min_length=1)
    source: str = Field(min_length=1)


class Frame(Model):
    handedness: Literal["right"]
    up: Literal["Z"]


class Manifest(Model):
    schema_version: Literal["1.0"]
    project_id: str
    assembly_id: str
    units: Literal["mm"]
    frame: Frame
    envelope_mm: Box
    components: tuple[Component, ...] = Field(min_length=5, max_length=12)
    connections: tuple[Connection, ...]
    tools: tuple[Tool, ...]
    constraints: tuple[Constraint, ...]
    keep_outs: tuple[KeepOut, ...]
    template_bindings: tuple[Binding, ...]
    provenance: Provenance
    regions: tuple[Region, ...]
    staging_regions: tuple[Stage, ...]
    unsupported_assumptions: tuple[str, ...]

    @model_validator(mode="after")
    def references(self):
        groups = [
            self.components,
            self.connections,
            self.tools,
            self.constraints,
            self.keep_outs,
            self.regions,
            self.staging_regions,
        ]
        for group in groups:
            ids = [x.id for x in group]
            if len(set(ids)) != len(ids):
                raise ValueError("duplicate IDs")
        c = {x.id: x for x in self.components}
        t = {x.id: x for x in self.tools}
        r = {x.id: x for x in self.regions}
        stages = {x.id for x in self.staging_regions}
        paths = [x.source_occurrence_path for x in self.components]
        if len(paths) != len(set(paths)):
            raise ValueError("ambiguous source occurrence paths")

        def require(ids, group, field):
            for id in ids:
                if id not in group:
                    raise ValueError(f"{field}: unknown reference {id}")

        for x in self.components:
            if x.staging_region_id:
                require(
                    [x.staging_region_id],
                    stages,
                    f"components.{x.id}.staging_region_id",
                )
        for x in self.regions:
            require([x.component_id], c, f"regions.{x.id}.component_id")
        edges = {k: [] for k in c}
        for x in self.connections:
            if isinstance(x, Screw):
                require(
                    [x.fastener_id, x.host_component_id, *x.retained_component_ids],
                    c,
                    f"connections.{x.id}",
                )
                require([x.tool_id], t, f"connections.{x.id}.tool_id")
                require(
                    [x.engagement_region_id],
                    r,
                    f"connections.{x.id}.engagement_region_id",
                )
                if c[x.fastener_id].role != "fastener":
                    raise ValueError("screw must reference fastener role")
                if tuple(x.axis_world) != axis_vector(t[x.tool_id].permitted_axis):
                    raise ValueError("screw axis must match tool permitted world axis")
                if (
                    not c[x.fastener_id].fixed
                    and t[x.tool_id].permitted_axis not in c[x.fastener_id].removal_axes
                ):
                    raise ValueError("inward screw extraction axis")
                for retained in x.retained_component_ids:
                    edges[retained].append(x.fastener_id)
            else:
                require([x.component_a_id, x.component_b_id], c, f"connections.{x.id}")
                require(
                    [x.region_a_id, x.region_b_id], r, f"connections.{x.id}.regions"
                )
                if (
                    r[x.region_a_id].component_id != x.component_a_id
                    or r[x.region_b_id].component_id != x.component_b_id
                ):
                    raise ValueError("contact region ownership mismatch")
                if x.outward_normal_world not in tuple(
                    axis_vector(a) for a in ("X+", "X-", "Y+", "Y-", "Z+", "Z-")
                ):
                    raise ValueError("only world-axis planar contact normals supported")

        def visit(k, active, done):
            if k in active:
                raise ValueError("cyclic retaining relationships")
            if k in done:
                return
            for nxt in edges[k]:
                visit(nxt, active | {k}, done)
            done.add(k)

        done = set()
        for k in c:
            visit(k, set(), done)
        for x in self.constraints:
            require(x.component_ids, c, f"constraints.{x.id}.component_ids")
            require(x.region_ids, r, f"constraints.{x.id}.region_ids")
        seen = set()
        for x in self.template_bindings:
            require([x.bracket_id], c, "template_bindings.bracket_id")
            require([x.editable_region_id], r, "template_bindings.editable_region_id")
            if x.bracket_id in seen:
                raise ValueError("duplicate bracket binding")
            seen.add(x.bracket_id)
            if r[x.editable_region_id].component_id != x.bracket_id:
                raise ValueError("editable region ownership mismatch")
        for x in self.keep_outs:
            x.box()
        return self


class Finding(Model):
    status: Status
    kind: str
    component_ids: tuple[str, ...] = ()
    explanation: str
    distance_mm: float | None = None
    intersection_volume_mm3: float | None = None
    witness_mm: Vec3 | None = None
    witness_travel_mm: float | None = None


class Proposal(Model):
    candidate_request_id: str = Field(min_length=1)
    bracket_id: str = Field(min_length=1)
    template_id: Literal["T01", "T02"]
    parameters: dict[str, float]
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    rationale: str = Field(max_length=800)

    @model_validator(mode="after")
    def parameter_contract(self):
        expected = (
            {"center_x_mm", "center_y_mm", "width_mm", "depth_mm"}
            if self.template_id == "T01"
            else {"offset_y_mm"}
        )
        if set(self.parameters) != expected:
            raise ValueError(
                "template parameter fields do not match the declared template"
            )
        return self


class InventoryItem(Model):
    id: str
    native_occurrence_id: str
    source_occurrence_path: str
    definition_id: str
    display_name: str
    role: str | None
    fixed: bool | None
    replaceable: bool | None
    removal_axes: tuple[Axis, ...]
    placement: Transform
    bounds_mm: Box
    geometry_valid: bool
    geometry_hash: str
    volume_mm3: float
    face_count: int


class Check(Model):
    constraint_id: str
    label: str
    result: Literal["pass", "fail", "unknown", "not_applicable"]
    mandatory: bool = True
    measured_value: float | str | None = None
    limit: str = ""
    units: str | None = None
    component_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    explanation: str


class EngineError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

    def envelope(self):
        return dict(
            error_code=self.code,
            message=str(self),
            retryable=False,
            field_errors=[],
            evidence_ids=[],
            run_id=None,
        )
