"""Reconstruct actual candidates, derive every check and fail closed on missing evidence."""

from __future__ import annotations

import itertools
from datetime import datetime, timezone
from importlib.metadata import version

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

from .contracts import (
    Check,
    EngineError,
    Model,
    POLICY,
    Screw,
    Status,
    axis_vector,
    digest,
)
from .geometry import (
    boolean,
    bounds,
    box_shape,
    collision,
    difference_volume,
    fingerprint,
    inverse,
    same_geometry,
    transform,
    validate_solid,
    volume,
)
from .motion import split_contact, validate_translation
from .service import Candidate, Revision, contacts_for, direct_path, shapes_hash
from .templates import construct, modify
from .tools import evaluate_fastener


UNVERIFIED = (
    "Structural strength and fatigue",
    "Electrical safety",
    "Manufacturing feasibility",
    "Restored product function",
    "Complete replacement requires separate state-aware plan replay and inverse sequence certificates",
)


class VerificationReport(Model):
    id: str
    candidate_id: str
    original_revision_id: str
    candidate_revision_id: str
    input_hash: str
    constraint_hash: str
    engine_versions: dict[str, str]
    generated_at: str
    status: str
    checks: tuple[Check, ...]
    path_certificates: tuple[dict, ...]
    unverified_properties: tuple[str, ...] = UNVERIFIED
    scope: str = "Independent geometry constraints and explicitly requested direct segments; no complete repair-route verdict"


def aggregate(checks, required_ids):
    by_id = {c.constraint_id: c for c in checks}
    if len(by_id) != len(checks):
        return "failed"
    if any(c.mandatory and c.result == "fail" for c in checks):
        return "failed"
    if not set(required_ids) <= by_id.keys():
        return "unknown"
    if any(by_id[id].result != "pass" for id in required_ids):
        return "unknown"
    if any(c.mandatory and c.result != "pass" for c in checks):
        return "unknown"
    return "passed"


def holes_signature(shape):
    result = []
    for face in shape.Faces():
        s = BRepAdaptor_Surface(face.wrapped)
        if s.GetType() == GeomAbs_Cylinder:
            cylinder = s.Cylinder()
            axis = cylinder.Axis()
            p = axis.Location()
            d = axis.Direction()
            result.append(
                (
                    cylinder.Radius(),
                    p.X(),
                    p.Y(),
                    p.Z(),
                    d.X(),
                    d.Y(),
                    d.Z(),
                    face.Area(),
                )
            )
    return sorted(result)


def verify_candidate(
    revision: Revision, candidate: Candidate, *, static_only=False
) -> VerificationReport:
    checks = []
    paths = []

    def add(
        id,
        result,
        explanation,
        *,
        label=None,
        value=None,
        limit="",
        units=None,
        ids=(),
        mandatory=True,
        evidence=(),
    ):
        if isinstance(result, bool):
            result = "pass" if result else "fail"
        checks.append(
            Check(
                constraint_id=id,
                label=label or id,
                result=result,
                mandatory=mandatory,
                measured_value=value,
                limit=limit,
                units=units,
                component_ids=ids,
                evidence_ids=evidence,
                explanation=explanation,
            )
        )

    if revision.manifest is None:
        raise EngineError(
            "INVALID_MANIFEST",
            "independent verification requires complete semantic metadata",
        )
    m = revision.manifest
    sources = revision.by_id()
    originals = {k: o.shape for k, o in sources.items()}
    invariant_ids = {
        "integrity",
        "solid_validity",
        "trusted_reconstruction",
        "actual_change",
        "protected_interfaces",
        "hole_geometry",
        "fixed_components",
        "placements",
        "design_envelope",
        "keep_outs",
        "assembled_intersections",
        "tool_access",
    }
    if static_only:
        invariant_ids.remove("tool_access")
    required = invariant_ids | {
        c.id
        for c in m.constraints
        if c.mandatory
        and not (static_only and c.kind == "clearance" and c.scope == "path")
    }
    expected_id = digest(
        [
            revision.input_hash,
            digest(m),
            candidate.bracket_id,
            candidate.template_id,
            dict(candidate.parameters),
            candidate.geometry_hash,
            POLICY.model_dump(),
        ]
    )
    integrity = (
        revision.ready
        and candidate.id == expected_id
        and candidate.original_revision_id == revision.input_hash
        and candidate.manifest_hash == revision.manifest_hash
        and candidate.constraint_hash == digest(m)
        and candidate.source_assembly_hash == revision.assembly.source_hash
        and candidate.bracket_id in sources
        and candidate.source_occurrence_path
        == sources[candidate.bracket_id].source_occurrence_path
        and candidate.original_shape_hash == sources[candidate.bracket_id].geometry_hash
        and candidate.original_geometry_hash == shapes_hash(originals)
        and candidate.geometry_hash == shapes_hash(candidate.shapes)
        and set(candidate.shapes) == set(originals)
        and all(fingerprint(o.shape) == o.geometry_hash for o in sources.values())
    )
    add(
        "integrity",
        integrity,
        "Revision, geometry, policy, parameters and full constraint metadata must match recorded hashes",
    )
    if integrity:
        binding = next(
            (b for b in m.template_bindings if b.bracket_id == candidate.bracket_id),
            None,
        )
        try:
            for s in candidate.shapes.values():
                validate_solid(s)
            if (
                sum(len(s.Faces()) for s in candidate.shapes.values())
                > POLICY.max_faces
            ):
                raise ValueError("candidate assembly face budget exceeded")
            if any(
                max(bounds(s).max[k] for s in candidate.shapes.values())
                - min(bounds(s).min[k] for s in candidate.shapes.values())
                > POLICY.max_envelope_mm
                for k in range(3)
            ):
                raise ValueError(
                    "candidate assembly exceeds 500 mm compatibility envelope"
                )
            add(
                "solid_validity",
                True,
                "Every occurrence remains one valid closed positive-volume solid",
            )
        except Exception as exc:
            add("solid_validity", False, str(exc))
        try:
            if binding is None:
                raise ValueError("missing constructor binding")
            placement = sources[candidate.bracket_id].placement
            old = transform(originals[candidate.bracket_id], inverse(placement))
            new = transform(candidate.shapes[candidate.bracket_id], inverse(placement))
            expected = modify(
                old, binding, candidate.template_id, dict(candidate.parameters)
            )
            add(
                "trusted_reconstruction",
                same_geometry(new, expected.shape),
                "Independently regenerated trusted solid compared by two-way BRep material difference",
            )
            changed = difference_volume(old, new)
            add(
                "actual_change",
                changed > POLICY.volume_noise_mm3,
                "Actual two-way material difference",
                value=changed,
                units="mm3",
                limit="> 1e-9 mm3",
            )
            if candidate.template_id == "T01":
                editable = next(
                    r for r in m.regions if r.id == binding.editable_region_id
                )
                removed = boolean(
                    "cut",
                    originals[candidate.bracket_id],
                    candidate.shapes[candidate.bracket_id],
                )
                outside = volume(boolean("cut", removed, box_shape(editable.bounds_mm)))
                add(
                    "editable_region",
                    outside <= POLICY.volume_noise_mm3,
                    "Actual removed material must be wholly inside engineer-declared world editable region",
                    value=outside,
                    units="mm3",
                )
                required.add("editable_region")
            baseline = construct(binding)
            protected_ok = True
            for region in baseline.protected:
                selector = box_shape(bounds(region))
                protected_ok &= same_geometry(
                    boolean("common", old, selector), boolean("common", new, selector)
                )
            add(
                "protected_interfaces",
                protected_ok,
                "Complete feet and post selectors include hole voids; material added into protected holes also fails",
            )
            # Equality of the complete protected material/void regions is stronger
            # than axis tolerance alone; additionally inspect actual cylindrical surfaces.
            hs1 = holes_signature(old)
            hs2 = holes_signature(new)
            holes_ok = len(hs1) == len(hs2) == 2 and all(
                abs(a - b) <= POLICY.tolerance_mm
                for one, two in zip(hs1, hs2)
                for a, b in zip(one, two)
            )
            add(
                "hole_geometry",
                holes_ok and protected_ok,
                "Actual cylindrical hole surfaces and complete surrounding protected regions agree",
            )
        except Exception as exc:
            add("trusted_reconstruction", False, str(exc)) if not any(
                c.constraint_id == "trusted_reconstruction" for c in checks
            ) else None
        add(
            "fixed_components",
            all(
                same_geometry(originals[k], candidate.shapes[k])
                for k in originals
                if k != candidate.bracket_id
            ),
            "Every unedited occurrence compared independently, including repeated shared-definition instances",
        )
        add(
            "placements",
            dict(candidate.placements) == {k: o.placement for k, o in sources.items()},
            "STEP world placements must match the original occurrences exactly",
        )
        add(
            "design_envelope",
            all(
                m.envelope_mm.contains(bounds(s), POLICY.tolerance_mm)
                for s in candidate.shapes.values()
            ),
            "All revised assembled solids must remain inside declared envelope with numerical guard",
        )
        ko = []
        for k in m.keep_outs:
            for id, s in candidate.shapes.items():
                ko.append(collision(s, box_shape(k.box()), 0, (id, "keepout:" + k.id)))
        add(
            "keep_outs",
            _finding_check(ko),
            "Every assembled solid checked against each declared keep-out",
            evidence=tuple(digest(f) for f in ko),
        )
        assembled = []
        for a, b in itertools.combinations(sorted(candidate.shapes), 2):
            f = collision(candidate.shapes[a], candidate.shapes[b], 0, (a, b))
            if f.status == Status.UNKNOWN:
                for moving, obstacle in ((a, b), (b, a)):
                    contact = contacts_for(m, moving).get(obstacle)
                    if contact:
                        try:
                            axis = next(
                                ax
                                for ax in ("X+", "X-", "Y+", "Y-", "Z+", "Z-")
                                if axis_vector(ax)
                                == contact.declaration.outward_normal_world
                            )
                            split_contact(
                                candidate.shapes[moving],
                                candidate.shapes[obstacle],
                                contact,
                                axis,
                            )
                            f = f.model_copy(
                                update=dict(
                                    status=Status.CLEAR,
                                    kind="validated_planar_start_contact",
                                )
                            )
                        except Exception:
                            pass
            assembled.append(f)
        add(
            "assembled_intersections",
            _finding_check(assembled),
            "All assembled occurrence pairs checked, with only independently validated planar contacts",
            evidence=tuple(digest(f) for f in assembled),
        )
        tool_findings = []
        for screw in m.connections:
            if isinstance(screw, Screw) and not static_only:
                try:
                    tool = next(t for t in m.tools if t.id == screw.tool_id)
                    region = next(
                        r for r in m.regions if r.id == screw.engagement_region_id
                    )
                    result = evaluate_fastener(
                        tool,
                        screw,
                        candidate.shapes[screw.fastener_id],
                        {
                            k: s
                            for k, s in candidate.shapes.items()
                            if k != screw.fastener_id
                        },
                        region,
                    )
                    tool_findings.append(result["status"])
                    paths.extend(
                        [
                            result["tool_access"].model_dump(mode="json"),
                            result["extraction"].model_dump(mode="json"),
                        ]
                    )
                except Exception:
                    tool_findings.append(Status.UNKNOWN)
        add(
            "tool_access",
            "not_applicable"
            if static_only
            else "fail"
            if Status.BLOCKED in tool_findings
            else "unknown"
            if any(x != Status.CLEAR for x in tool_findings)
            else "pass",
            "Deferred to independent state-aware plan replay and reverse validation"
            if static_only
            else "Declared screws independently checked; no tool operation is inferred when none is declared",
            mandatory=not static_only,
        )
        for constraint in m.constraints:
            if (
                static_only
                and constraint.kind == "clearance"
                and constraint.scope == "path"
            ):
                continue
            try:
                ids = constraint.component_ids
                result = "unknown"
                value = None
                evidence = ()
                if constraint.kind == "fixed_geometry":
                    result = (
                        all(
                            k != candidate.bracket_id
                            and same_geometry(originals[k], candidate.shapes[k])
                            for k in ids
                        )
                        if ids
                        else "unknown"
                    )
                elif constraint.kind == "envelope":
                    result = (
                        all(
                            m.envelope_mm.contains(
                                bounds(candidate.shapes[k]), POLICY.tolerance_mm
                            )
                            for k in ids
                        )
                        if ids
                        else "unknown"
                    )
                elif constraint.kind == "keep_out":
                    result = next(
                        c.result for c in checks if c.constraint_id == "keep_outs"
                    )
                elif constraint.kind == "template_bound":
                    result = next(
                        c.result
                        for c in checks
                        if c.constraint_id == "trusted_reconstruction"
                    )
                elif constraint.kind == "hole_axis":
                    result = (
                        next(
                            c.result
                            for c in checks
                            if c.constraint_id == "hole_geometry"
                        )
                        if ids == (candidate.bracket_id,)
                        else "unknown"
                    )
                elif constraint.kind == "protected_region":
                    result = True if constraint.region_ids else "unknown"
                    for rid in constraint.region_ids:
                        region = next(r for r in m.regions if r.id == rid)
                        selector = box_shape(region.bounds_mm)
                        result &= same_geometry(
                            boolean("common", originals[region.component_id], selector),
                            boolean(
                                "common",
                                candidate.shapes[region.component_id],
                                selector,
                            ),
                        )
                elif (
                    constraint.kind == "clearance"
                    and constraint.threshold_mm is not None
                ):
                    if constraint.scope == "pair" and len(ids) == 2:
                        f = collision(
                            candidate.shapes[ids[0]],
                            candidate.shapes[ids[1]],
                            constraint.threshold_mm,
                            ids,
                        )
                        result = _finding_check([f])
                        value = f.distance_mm
                        evidence = (digest(f),)
                    elif (
                        constraint.scope == "path"
                        and len(ids) == 1
                        and constraint.axis
                        and constraint.distance_mm
                    ):
                        p = direct_path(
                            revision,
                            ids[0],
                            constraint.axis,
                            constraint.distance_mm,
                            candidate=candidate,
                            clearance_mm=constraint.threshold_mm,
                        )
                        result = _finding_check([p])
                        evidence = (p.id,)
                        paths.append(p.model_dump(mode="json"))
                        # The goal must actually reach the declared external stage.
                        component = next(c for c in m.components if c.id == ids[0])
                        stage = next(
                            s
                            for s in m.staging_regions
                            if s.id == component.staging_region_id
                        )
                        delta = tuple(
                            x * constraint.distance_mm
                            for x in axis_vector(constraint.axis)
                        )
                        end = bounds(candidate.shapes[ids[0]].translate(delta))
                        stage_ok = stage.bounds_mm.contains(
                            end, POLICY.tolerance_mm
                        ) and any(
                            end.min[k] > m.envelope_mm.max[k] + POLICY.clearance_mm
                            or end.max[k] < m.envelope_mm.min[k] - POLICY.clearance_mm
                            for k in range(3)
                        )
                        add(
                            "stage:" + constraint.id,
                            stage_ok,
                            "Endpoint lies entirely inside declared staging volume and outside assembly envelope",
                            mandatory=constraint.mandatory,
                        )
                        required.add(
                            "stage:" + constraint.id
                        ) if constraint.mandatory else None
                        opposite = constraint.axis[0] + (
                            "-" if constraint.axis[1] == "+" else "+"
                        )
                        obs = {k: s for k, s in candidate.shapes.items() if k != ids[0]}
                        obs.update(
                            {"keepout:" + k.id: box_shape(k.box()) for k in m.keep_outs}
                        )
                        # Rebuild the conservative material decomposition at the inverse
                        # segment too, rather than assuming sampled playback is reversible.
                        binding = next(
                            b
                            for b in m.template_bindings
                            if b.bracket_id == candidate.bracket_id
                        )
                        bracket = modify(
                            transform(
                                originals[candidate.bracket_id],
                                inverse(sources[candidate.bracket_id].placement),
                            ),
                            binding,
                            candidate.template_id,
                            dict(candidate.parameters),
                        )
                        proxies = {
                            candidate.bracket_id: tuple(
                                bounds(
                                    transform(
                                        box_shape(b),
                                        sources[candidate.bracket_id].placement,
                                    )
                                ).inflate(POLICY.tolerance_mm)
                                for b in bracket.proxies
                            )
                        }
                        reverse = validate_translation(
                            ids[0],
                            candidate.shapes[ids[0]].translate(delta),
                            obs,
                            opposite,
                            constraint.distance_mm,
                            constraint.threshold_mm,
                            obstacle_boxes=proxies,
                        )
                        paths.append(reverse.model_dump(mode="json"))
                        add(
                            "reverse:" + constraint.id,
                            _finding_check([reverse]),
                            "Explicit reverse direct segment rechecked against assembled obstacles; full sequence planning remains outside this engine",
                            mandatory=constraint.mandatory,
                            evidence=(reverse.id,),
                        )
                        required.add(
                            "reverse:" + constraint.id
                        ) if constraint.mandatory else None
                add(
                    constraint.id,
                    result,
                    "Measured by the independent verifier",
                    label=constraint.label,
                    value=value,
                    limit=constraint.limit,
                    units="mm" if constraint.kind == "clearance" else None,
                    ids=ids,
                    mandatory=constraint.mandatory,
                    evidence=evidence,
                )
            except Exception as exc:
                add(
                    constraint.id,
                    "unknown",
                    str(exc),
                    label=constraint.label,
                    limit=constraint.limit,
                    ids=constraint.component_ids,
                    mandatory=constraint.mandatory,
                )
    for missing in sorted(required - {c.constraint_id for c in checks}):
        add(missing, "unknown", "Required independent evidence was not produced")
    status = aggregate(checks, required)
    versions = {x: version(x) for x in ("cadquery", "cadquery-ocp", "pydantic")}
    versions["unlock_engine"] = "0.1.0"
    ih = digest(
        [
            revision.input_hash,
            candidate.id,
            dict(candidate.parameters),
            shapes_hash(candidate.shapes),
            POLICY.model_dump(),
        ]
    )
    return VerificationReport(
        id=digest([ih, checks, paths]),
        candidate_id=candidate.id,
        original_revision_id=revision.input_hash,
        candidate_revision_id=candidate.geometry_hash,
        input_hash=ih,
        constraint_hash=digest(m),
        engine_versions=versions,
        generated_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        checks=tuple(checks),
        path_certificates=tuple(paths),
        scope="Static candidate constraints only; tools, removal and insertion must be checked by the planner"
        if static_only
        else VerificationReport.model_fields["scope"].default,
    )


def _finding_check(findings):
    if any(f.status == Status.BLOCKED for f in findings):
        return "fail"
    if any(f.status != Status.CLEAR for f in findings):
        return "unknown"
    return "pass"
