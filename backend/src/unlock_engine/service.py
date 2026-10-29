"""Typed domain entry points for a future coordinator, planner and frontend adapter."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

from pydantic import ValidationError
from jsonschema import Draft202012Validator

from .assembly import Assembly, import_step
from .contracts import (
    EngineError,
    InventoryItem,
    Manifest,
    POLICY,
    Screw,
    Seat,
    Status,
    axis_vector,
    digest,
)
from .geometry import (
    bounds,
    collision,
    fingerprint,
    inverse,
    transform,
    validate_solid,
)
from .motion import Contact, split_contact, validate_translation
from .templates import modify

_MANIFEST_VALIDATOR = Draft202012Validator(Manifest.model_json_schema())


@dataclass(frozen=True)
class Revision:
    assembly: Assembly
    manifest: Manifest | None
    manifest_hash: str
    input_hash: str
    readiness: tuple[dict, ...]

    @property
    def ready(self):
        return self.manifest is not None and all(x["ok"] for x in self.readiness)

    def by_id(self):
        if self.manifest is None:
            raise EngineError(
                "INVALID_MANIFEST", "Geometry imported — analysis unavailable."
            )
        paths = {o.source_occurrence_path: o for o in self.assembly.occurrences}
        return {c.id: paths[c.source_occurrence_path] for c in self.manifest.components}

    def inventory(self):
        semantics = (
            {c.source_occurrence_path: c for c in self.manifest.components}
            if self.manifest
            else {}
        )
        inventory = []
        for o in self.assembly.occurrences:
            c = semantics.get(o.source_occurrence_path)
            validity = validate_solid(o.shape)
            inventory.append(
                InventoryItem(
                    id=c.id if c else o.id,
                    native_occurrence_id=o.id,
                    source_occurrence_path=o.source_occurrence_path,
                    definition_id=o.definition_id,
                    display_name=c.display_name if c else o.display_name,
                    role=c.role if c else None,
                    fixed=c.fixed if c else None,
                    replaceable=c.replaceable if c else None,
                    removal_axes=c.removal_axes if c else (),
                    placement=o.placement,
                    bounds_mm=bounds(o.shape),
                    geometry_valid=True,
                    geometry_hash=o.geometry_hash,
                    volume_mm3=validity["volume_mm3"],
                    face_count=validity["faces"],
                ).model_dump(mode="json")
            )
        return dict(
            id=self.input_hash,
            input_hash=self.input_hash,
            geometry_hash=self.assembly.geometry_hash,
            manifest_hash=self.manifest_hash,
            message="Geometry imported — analysis ready."
            if self.ready
            else "Geometry imported — analysis unavailable.",
            readiness=self.readiness,
            components=inventory,
            manifest=self.manifest.model_dump(mode="json") if self.manifest else None,
        )


def import_revision(step_path: Path, metadata: dict) -> Revision:
    assembly = import_step(step_path)
    mh = digest(metadata)
    ih = digest([assembly.source_hash, mh, POLICY.model_dump()])
    readiness = []
    try:
        manifest = Manifest.model_validate(metadata)
    except ValidationError as exc:
        readiness = [
            dict(field=".".join(map(str, e["loc"])), ok=False, message=e["msg"])
            for e in exc.errors()
        ]
        return Revision(assembly, None, mh, ih, tuple(readiness))
    schema_errors = list(_MANIFEST_VALIDATOR.iter_errors(metadata))
    if schema_errors:
        readiness = [
            dict(field=".".join(map(str, e.absolute_path)), ok=False, message=e.message)
            for e in schema_errors
        ]
        return Revision(assembly, None, mh, ih, tuple(readiness))
    paths = {o.source_occurrence_path: o for o in assembly.occurrences}
    for c in manifest.components:
        if c.source_occurrence_path not in paths:
            readiness.append(
                dict(
                    field=f"components.{c.id}.source_occurrence_path",
                    ok=False,
                    message="not found in STEP inventory",
                )
            )
            continue
        o = paths[c.source_occurrence_path]
        if c.placement and any(
            abs(a - b) > POLICY.volume_noise_mm3
            for a, b in zip(c.placement.matrix, o.placement.matrix)
        ):
            readiness.append(
                dict(
                    field=f"components.{c.id}.placement",
                    ok=False,
                    message="manifest placement differs from authoritative STEP; never applied twice",
                )
            )
        if c.bounds_mm and any(
            abs(a - b) > POLICY.tolerance_mm
            for a, b in zip(
                (*c.bounds_mm.min, *c.bounds_mm.max),
                (*bounds(o.shape).min, *bounds(o.shape).max),
            )
        ):
            readiness.append(
                dict(
                    field=f"components.{c.id}.bounds_mm",
                    ok=False,
                    message="declared bounds differ from BRep",
                )
            )
        if not manifest.envelope_mm.contains(bounds(o.shape)):
            readiness.append(
                dict(
                    field=f"components.{c.id}.envelope",
                    ok=False,
                    message="solid outside declared assembly envelope",
                )
            )
    if set(paths) != {c.source_occurrence_path for c in manifest.components}:
        readiness.append(
            dict(
                field="components",
                ok=False,
                message="manifest must map every STEP leaf exactly once",
            )
        )
    for c in manifest.constraints:
        if c.kind == "clearance" and (
            c.threshold_mm is None
            or c.scope is None
            or (c.scope == "path" and (not c.axis or c.distance_mm is None))
        ):
            readiness.append(
                dict(
                    field=f"constraints.{c.id}",
                    ok=False,
                    message="clearance requires numeric threshold_mm, scope and path axis/distance",
                )
            )
        if c.kind == "protected_region" and not c.region_ids:
            readiness.append(
                dict(
                    field=f"constraints.{c.id}.region_ids",
                    ok=False,
                    message="named protected geometry required",
                )
            )
    if manifest.unsupported_assumptions:
        readiness.append(
            dict(
                field="unsupported_assumptions",
                ok=False,
                message="; ".join(manifest.unsupported_assumptions),
            )
        )
    if all(c.source_occurrence_path in paths for c in manifest.components):
        ids = {c.id: paths[c.source_occurrence_path] for c in manifest.components}
        for a, b in itertools.combinations(sorted(ids), 2):
            f = collision(ids[a].shape, ids[b].shape, 0, (a, b))
            if f.status != Status.CLEAR:
                valid = False
                for s in manifest.connections:
                    if isinstance(s, Seat) and {s.component_a_id, s.component_b_id} == {
                        a,
                        b,
                    }:
                        try:
                            contacts = contacts_for(manifest, s.component_a_id)
                            axis = next(
                                ax
                                for ax in ("X+", "X-", "Y+", "Y-", "Z+", "Z-")
                                if axis_vector(ax) == s.outward_normal_world
                            )
                            split_contact(
                                ids[s.component_a_id].shape,
                                ids[s.component_b_id].shape,
                                contacts[s.component_b_id],
                                axis,
                            )
                            valid = True
                        except Exception:
                            pass
                if not valid:
                    readiness.append(
                        dict(
                            field=f"assembled.{a}.{b}",
                            ok=False,
                            message=f"{f.kind}: {f.explanation}",
                        )
                    )
    if not readiness:
        readiness = [
            dict(
                field="geometry_and_semantics",
                ok=True,
                message="STEP occurrence mapping, solid checks and semantic references validated",
            )
        ]
    return Revision(assembly, manifest, mh, ih, tuple(readiness))


def contacts_for(manifest: Manifest, moving_id: str):
    regions = {r.id: r for r in manifest.regions}
    result = {}
    for s in manifest.connections:
        if isinstance(s, Seat) and s.component_a_id == moving_id:
            if s.component_b_id in result:
                raise EngineError(
                    "UNSUPPORTED_SEMANTICS",
                    "multiple contact declarations for one pair require a richer partition",
                )
            result[s.component_b_id] = Contact(
                s, regions[s.region_a_id], regions[s.region_b_id]
            )
        elif isinstance(s, Seat) and s.component_b_id == moving_id:
            reversed_seat = s.model_copy(
                update=dict(
                    component_a_id=s.component_b_id,
                    component_b_id=s.component_a_id,
                    region_a_id=s.region_b_id,
                    region_b_id=s.region_a_id,
                    outward_normal_world=tuple(-x for x in s.outward_normal_world),
                )
            )
            result[s.component_a_id] = Contact(
                reversed_seat, regions[s.region_b_id], regions[s.region_a_id]
            )
    return result


@dataclass(frozen=True)
class Candidate:
    id: str
    original_revision_id: str
    manifest_hash: str
    original_geometry_hash: str
    constraint_hash: str
    bracket_id: str
    template_id: str
    parameters: dict
    shapes: dict
    placements: dict
    geometry_hash: str

    source_assembly_hash: str
    source_occurrence_path: str
    original_shape_hash: str
    created_at: str

    def record(self):
        return dict(
            id=self.id,
            original_revision_id=self.original_revision_id,
            manifest_hash=self.manifest_hash,
            original_geometry_hash=self.original_geometry_hash,
            constraint_hash=self.constraint_hash,
            bracket_id=self.bracket_id,
            template_id=self.template_id,
            template_version="1",
            parameters=dict(self.parameters),
            geometry_hash=self.geometry_hash,
            policy=POLICY.model_dump(),
            engine_version="0.1.0",
            modified_occurrence_id=self.bracket_id,
            source_assembly_hash=self.source_assembly_hash,
            created_at=self.created_at,
            original_shape_ref=dict(
                file="original.step",
                source_occurrence_path=self.source_occurrence_path,
                geometry_hash=self.original_shape_hash,
            ),
            revised_shape_ref=dict(
                file="changed_bracket.step",
                geometry_hash=fingerprint(self.shapes[self.bracket_id]),
            ),
        )


def shapes_hash(shapes):
    return digest({k: fingerprint(v) for k, v in sorted(shapes.items())})


def construct_candidate(
    revision: Revision, bracket_id: str, template_id: str, parameters: dict
) -> Candidate:
    if not revision.ready:
        raise EngineError(
            "UNSUPPORTED_SEMANTICS", "Geometry imported — analysis unavailable."
        )
    manifest = revision.manifest
    binding = next(
        (b for b in manifest.template_bindings if b.bracket_id == bracket_id), None
    )
    if not binding:
        raise EngineError(
            "UNSUPPORTED_TEMPLATE", "occurrence has no trusted constructor binding"
        )
    source = revision.by_id()
    o = source[bracket_id]
    original_hash = shapes_hash({k: v.shape for k, v in source.items()})
    if fingerprint(o.shape) != o.geometry_hash:
        raise EngineError("STALE_REVISION", "original BRep was mutated")
    local = transform(o.shape, inverse(o.placement))
    edited = modify(local, binding, template_id, parameters)
    shapes = {k: v.shape for k, v in source.items()}
    shapes[bracket_id] = transform(edited.shape, o.placement)
    gh = shapes_hash(shapes)
    ch = digest(manifest)
    cid = digest(
        [
            revision.input_hash,
            ch,
            bracket_id,
            template_id,
            parameters,
            gh,
            POLICY.model_dump(),
        ]
    )
    return Candidate(
        cid,
        revision.input_hash,
        revision.manifest_hash,
        original_hash,
        ch,
        bracket_id,
        template_id,
        MappingProxyType(dict(parameters)),
        MappingProxyType(shapes),
        MappingProxyType({k: v.placement for k, v in source.items()}),
        gh,
        revision.assembly.source_hash,
        o.source_occurrence_path,
        o.geometry_hash,
        datetime.now(timezone.utc).isoformat(),
    )


def direct_path(
    revision: Revision,
    moving_id: str,
    axis,
    distance_mm,
    *,
    candidate: Candidate | None = None,
    clearance_mm=POLICY.clearance_mm,
):
    if not revision.ready:
        raise EngineError("UNSUPPORTED_SEMANTICS", "revision is not analysis ready")
    m = revision.manifest
    components = {c.id: c for c in m.components}
    if moving_id not in components:
        raise EngineError("NOT_FOUND", "unknown component")
    c = components[moving_id]
    if c.role == "fastener":
        raise EngineError(
            "UNSUPPORTED_SEMANTICS",
            "fasteners require annotated tool-access and extraction subchecks",
        )
    if c.fixed or axis not in c.removal_axes:
        raise EngineError(
            "UNSUPPORTED_SEMANTICS", "component is fixed or axis is not permitted"
        )
    if any(
        isinstance(s, Screw) and moving_id in s.retained_component_ids
        for s in m.connections
    ):
        raise EngineError(
            "UNSUPPORTED_SEMANTICS",
            "retainers remain assembled; a disassembly planner must supply a checked released state",
        )
    shapes = (
        candidate.shapes
        if candidate
        else {k: o.shape for k, o in revision.by_id().items()}
    )
    if candidate and (
        set(shapes) != set(components)
        or candidate.original_revision_id != revision.input_hash
        or candidate.constraint_hash != digest(m)
    ):
        raise EngineError(
            "STALE_REVISION", "candidate assembly or constraint identity is stale"
        )
    proposed = {}
    if candidate:
        # Only the trusted constructor can supply the tighter material union. The
        # validator independently subtracts it from actual candidate material.
        b = next(b for b in m.template_bindings if b.bracket_id == candidate.bracket_id)
        local = modify(
            transform(
                revision.by_id()[b.bracket_id].shape,
                inverse(revision.by_id()[b.bracket_id].placement),
            ),
            b,
            candidate.template_id,
            dict(candidate.parameters),
        )
        from .geometry import box_shape

        proposed[b.bracket_id] = tuple(
            bounds(
                transform(box_shape(box), revision.by_id()[b.bracket_id].placement)
            ).inflate(POLICY.tolerance_mm)
            for box in local.proxies
        )
    obstacles = {k: s for k, s in shapes.items() if k != moving_id}
    from .geometry import box_shape

    obstacles.update({"keepout:" + k.id: box_shape(k.box()) for k in m.keep_outs})
    result = validate_translation(
        moving_id,
        shapes[moving_id],
        obstacles,
        axis,
        distance_mm,
        clearance_mm,
        contacts=contacts_for(m, moving_id),
        obstacle_boxes=proposed,
    )
    return result
