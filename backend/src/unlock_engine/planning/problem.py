"""Immutable planning inputs and deterministic finite endpoint policy."""

from types import MappingProxyType

from ..contracts import EngineError, POLICY, Screw, axis_vector, digest
from ..geometry import bounds, box_shape, fingerprint, inverse, same_geometry, transform
from ..service import contacts_for, shapes_hash
from ..templates import construct, modify
from ..verification import verify_candidate
from .contracts import Action, SearchPolicy, State

AXES = ("X+", "X-", "Y+", "Y-", "Z+", "Z-")


class Problem:
    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError(
                "planning inputs are frozen; construct a new revision/problem"
            )
        object.__setattr__(self, name, value)

    def __init__(
        self,
        revision,
        target_id,
        policy=SearchPolicy(),
        *,
        candidate=None,
        expected_revision_id=None,
    ):
        if not revision.ready:
            raise EngineError(
                "UNSUPPORTED_SEMANTICS", f"Analysis unavailable: {revision.readiness}"
            )
        self.revision = revision
        self.manifest = revision.manifest
        self.components = {c.id: c for c in self.manifest.components}
        if target_id not in self.components:
            raise EngineError("NOT_FOUND", "unknown target occurrence")
        c = self.components[target_id]
        if not c.replaceable or c.fixed or c.role == "fastener":
            raise EngineError(
                "UNSUPPORTED_SEMANTICS",
                "target must be a replaceable, removable nonfastener occurrence",
            )
        self.target_id, self.policy = target_id, policy
        self.candidate = candidate
        source = revision.by_id()
        self.placements = {k: o.placement for k, o in source.items()}
        self.shapes = (
            dict(candidate.shapes)
            if candidate
            else {k: o.shape for k, o in source.items()}
        )
        self.static_report = None
        self.proxies = {}
        if candidate:
            self.static_report = verify_candidate(revision, candidate, static_only=True)
            if self.static_report.status != "passed":
                raise EngineError(
                    "CONSTRAINT_VIOLATION",
                    "candidate failed independent static verification: "
                    + self.static_report.id,
                )
            b = next(
                b
                for b in self.manifest.template_bindings
                if b.bracket_id == candidate.bracket_id
            )
            local = modify(
                transform(
                    source[b.bracket_id].shape, inverse(source[b.bracket_id].placement)
                ),
                b,
                candidate.template_id,
                dict(candidate.parameters),
            )
            self.proxies[b.bracket_id] = tuple(
                bounds(
                    transform(box_shape(box), self.placements[b.bracket_id])
                ).inflate(POLICY.tolerance_mm)
                for box in local.proxies
            )
        # Known-family source brackets may use the trusted decomposition only
        # after matching actual imported material. Coverage is checked again by
        # the authoritative motion validator for every admitted path.
        for binding in self.manifest.template_bindings:
            if binding.bracket_id in self.proxies:
                continue
            local_shape = transform(
                source[binding.bracket_id].shape,
                inverse(self.placements[binding.bracket_id]),
            )
            expected = construct(binding)
            if not same_geometry(local_shape, expected.shape):
                raise EngineError(
                    "UNSUPPORTED_SEMANTICS",
                    "template binding differs from actual imported bracket geometry",
                )
            self.proxies[binding.bracket_id] = tuple(
                bounds(
                    transform(box_shape(box), self.placements[binding.bracket_id])
                ).inflate(POLICY.tolerance_mm)
                for box in expected.proxies
            )
        self.geometry_hash = shapes_hash(self.shapes)
        self.revision_id = candidate.id if candidate else revision.input_hash
        if (
            expected_revision_id is not None
            and self.revision_id != expected_revision_id
        ):
            raise EngineError(
                "STALE_REVISION",
                "requested revision does not match actual geometry revision",
            )
        self.constraint_hash = digest(self.manifest)
        self.tool_hash = digest(
            [self.manifest.tools, self.manifest.connections, self.manifest.regions]
        )
        self.policy_hash = digest([POLICY, policy])
        self.representation_hash = digest(self.proxies)
        self.input_hash = digest(
            [
                self.revision_id,
                self.geometry_hash,
                self.constraint_hash,
                self.tool_hash,
                self.policy_hash,
                self.representation_hash,
                target_id,
            ]
        )
        # Geometry-dependent bounds/placements are excluded here, but every
        # declared constraint, role, connection, stage, grid and policy is frozen.
        comparison = self.manifest.model_dump(mode="json")
        for c in comparison["components"]:
            c.pop("bounds_mm", None)
            c.pop("placement", None)
        self.comparison_hash = digest([comparison, target_id, POLICY, policy])
        self.shape_hashes = {k: fingerprint(s) for k, s in self.shapes.items()}
        self.original_geometry_hash = shapes_hash(
            {k: o.shape for k, o in source.items()}
        )
        self.screws = {}
        for s in self.manifest.connections:
            if isinstance(s, Screw):
                if s.fastener_id in self.screws:
                    raise EngineError(
                        "UNSUPPORTED_SEMANTICS",
                        "one screw occurrence requires one annotation, which may retain multiple components",
                    )
                self.screws[s.fastener_id] = s
        self.tools = {t.id: t for t in self.manifest.tools}
        self.regions = {r.id: r for r in self.manifest.regions}
        self.stages = {s.id: s for s in self.manifest.staging_regions}
        self.keepouts = {
            "keepout:" + k.id: box_shape(k.box()) for k in self.manifest.keep_outs
        }
        self.keepout_geometry_hash = shapes_hash(self.keepouts)
        self.contacts = {k: contacts_for(self.manifest, k) for k in self.components}
        self.path_constraints = {
            k: tuple(
                c
                for c in self.manifest.constraints
                if c.kind == "clearance"
                and c.scope == "path"
                and c.mandatory
                and c.component_ids == (k,)
            )
            for k in self.components
        }
        for k, constraints in self.path_constraints.items():
            if len({c.axis for c in constraints}) > 1:
                raise EngineError(
                    "UNSUPPORTED_SEMANTICS",
                    f"{k}: multiple mandatory path axes cannot be fulfilled by one removal",
                )
        if all(
            self.distance(target_id, ax) is None
            for ax in self.components[target_id].removal_axes
        ):
            raise EngineError(
                "UNSUPPORTED_SEMANTICS",
                "target has no valid external staging endpoint on a declared axis",
            )
        self.contacts = {k: MappingProxyType(v) for k, v in self.contacts.items()}
        for name in (
            "components",
            "placements",
            "shapes",
            "proxies",
            "shape_hashes",
            "screws",
            "tools",
            "regions",
            "stages",
            "keepouts",
            "contacts",
            "path_constraints",
        ):
            setattr(self, name, MappingProxyType(getattr(self, name)))
        self._sealed = True

    def check_integrity(self):
        if (
            self.geometry_hash != shapes_hash(self.shapes)
            or self.constraint_hash != digest(self.manifest)
            or self.representation_hash != digest(dict(self.proxies))
            or self.keepout_geometry_hash != shapes_hash(self.keepouts)
            or self.original_geometry_hash
            != shapes_hash({k: o.shape for k, o in self.revision.by_id().items()})
        ):
            raise EngineError(
                "STALE_REVISION", "planning geometry or constraints changed"
            )

    def prerequisites(self, component_id):
        return tuple(
            sorted(
                s.fastener_id
                for s in self.screws.values()
                if component_id in (*s.retained_component_ids, s.host_component_id)
            )
        )

    def obstacles(self, state, moving_id):
        return {
            **{
                k: s
                for k, s in self.shapes.items()
                if k not in state.removed and k != moving_id
            },
            **self.keepouts,
        }

    def clearance(self, component_id):
        return max(
            [
                self.policy.clearance_mm,
                *(c.threshold_mm for c in self.path_constraints[component_id]),
            ]
        )

    def distance(self, component_id, axis):
        c = self.components[component_id]
        stage = self.stages.get(c.staging_region_id)
        if stage is None:
            return None
        path = self.path_constraints[component_id]
        if path and any(p.axis != axis for p in path):
            return None
        box = bounds(self.shapes[component_id])
        k = "XYZ".index(axis[0])
        sign = axis_vector(axis)[k]
        guard = POLICY.tolerance_mm
        if path:
            distance = max(p.distance_mm for p in path)
        elif sign > 0:
            distance = max(
                guard,
                stage.bounds_mm.min[k] + 2 * guard - box.min[k],
                self.manifest.envelope_mm.max[k]
                + self.policy.clearance_mm
                + 2 * guard
                - box.min[k],
            )
        else:
            distance = max(
                guard,
                box.max[k] - stage.bounds_mm.max[k] + 2 * guard,
                box.max[k]
                - self.manifest.envelope_mm.min[k]
                + self.policy.clearance_mm
                + 2 * guard,
            )
        end = box.translated(tuple(x * distance for x in axis_vector(axis)))
        exterior = any(
            end.min[j] > self.manifest.envelope_mm.max[j] + self.policy.clearance_mm
            or end.max[j] < self.manifest.envelope_mm.min[j] - self.policy.clearance_mm
            for j in range(3)
        )
        return distance if stage.bounds_mm.contains(end, guard) and exterior else None

    def actions(self, state: State):
        # PRD ordering is occurrence ID then axis, independent of dict/set order.
        for k, c in sorted(self.components.items()):
            if k in state.removed:
                continue
            screw = self.screws.get(k)
            if c.role == "fastener":
                axis = (
                    self.tools[screw.tool_id].permitted_axis
                    if screw
                    else (c.removal_axes or ("Z+",))[0]
                )
                yield Action(
                    kind="REMOVE_FASTENER",
                    component_id=k,
                    axis=axis,
                    distance_mm=screw.extraction_distance_mm if screw else 1,
                    tool_id=screw.tool_id if screw else None,
                )
            else:
                for axis in sorted(set(c.removal_axes or ("Z+",))):
                    yield Action(
                        kind="TRANSLATE_PART",
                        component_id=k,
                        axis=axis,
                        distance_mm=self.distance(k, axis) or 1,
                    )

    def semantic_reason(self, state, action):
        k = action.component_id
        if not state.removed <= self.components.keys() or state.last_tool not in (
            None,
            *self.tools,
        ):
            return "invalid state IDs", "UNSUPPORTED_OPERATION"
        if k not in self.components:
            return "unknown occurrence", "UNSUPPORTED_OPERATION"
        if any(self.components[x].fixed for x in state.removed):
            return "state removes a fixed occurrence", "UNSUPPORTED_OPERATION"
        c = self.components[k]
        if k in state.removed:
            return "occurrence already removed", "SEMANTICALLY_BLOCKED"
        if c.fixed:
            return "fixed occurrence", "SEMANTICALLY_BLOCKED"
        if action.axis not in c.removal_axes:
            return "undeclared movement axis", "UNSUPPORTED_OPERATION"
        retainers = set(self.prerequisites(k)) - state.removed
        if retainers:
            return "installed retainers: " + ", ".join(
                sorted(retainers)
            ), "SEMANTICALLY_BLOCKED"
        if action.kind == "REMOVE_FASTENER":
            screw = self.screws.get(k)
            if c.role != "fastener" or screw is None:
                return "no supported reusable screw annotation", "UNSUPPORTED_OPERATION"
            region = self.regions[screw.engagement_region_id]
            tool = self.tools[screw.tool_id]
            if region.kind != "engagement" or region.component_id != k:
                return "missing or invalid named engagement", "UNSUPPORTED_OPERATION"
            if (
                action.tool_id != screw.tool_id
                or action.axis != tool.permitted_axis
                or action.distance_mm != screw.extraction_distance_mm
            ):
                return (
                    "action differs from declared screw/tool/extraction",
                    "UNSUPPORTED_OPERATION",
                )
        else:
            if c.role == "fastener" or action.tool_id is not None:
                return (
                    "fastener requires REMOVE_FASTENER with tool subchecks",
                    "UNSUPPORTED_OPERATION",
                )
            distance = self.distance(k, action.axis)
            if distance is None or action.distance_mm != distance:
                return (
                    "invalid staging endpoint or mandatory path direction",
                    "UNSUPPORTED_OPERATION",
                )
        return None
