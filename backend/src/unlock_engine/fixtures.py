"""Synthetic CAD fixtures, authored here. No industrial product validation implied."""

from pathlib import Path
import json

import cadquery as cq

from .assembly import import_step
from .contracts import Binding, Manifest
from .geometry import bounds
from .fixture_license import B02_PROVENANCE
from .templates import SERVER_DOMAINS, construct


def binding_data(span=96):
    return dict(
        bracket_id="bridge",
        family="bridge_bracket_v1",
        constructor_version="1",
        editable_region_id="web",
        minimum_web_mm=6,
        maximum_cut_volume_mm3=5000,
        parameters=dict(
            span_mm=span,
            foot_width_mm=16,
            foot_depth_mm=24,
            foot_thickness_mm=4,
            hole_diameter_mm=3.4,
            post_width_mm=6,
            post_depth_mm=24,
            web_length_mm=span - 4,
            web_depth_mm=68,
            web_thickness_mm=4,
            web_underside_height_mm=34,
        ),
        templates=[
            dict(id=id, label=id, domain=domain)
            for id, domain in SERVER_DOMAINS.items()
        ],
    )


def generate_fixture(directory: Path, code="B02", *, held_out=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    binding = Binding.model_validate(binding_data(104 if held_out else 96))
    bracket = construct(binding)
    target = cq.Solid.makeBox(22 if held_out else 20, 8, 12).translate((-10, -24, 15))
    base = cq.Solid.makeBox(140, 100, 3).translate((-70, -50, -10))
    screw = cq.Solid.makeCylinder(2, 6)
    cover = cq.Solid.makeBox(20, 10, 2)
    parts = [
        ("base", base, cq.Location()),
        ("target", target, cq.Location()),
        ("cover", cover, cq.Location((55, 35, 20))),
        ("screw1", screw, cq.Location((-60, 35, 8))),
        ("screw2", screw, cq.Location((60, -35, 8))),
    ]
    if code in ("B02", "B03"):
        parts.extend(
            [
                ("bridge", bracket.shape, cq.Location()),
                ("board", cq.Solid.makeBox(10, 6, 2), cq.Location((-65, -40, 15))),
                ("spacer", cq.Solid.makeBox(4, 4, 4), cq.Location((58, 36, 5))),
            ]
        )
    if code == "B03":
        parts.extend(
            [
                (
                    "tool_blocker",
                    cq.Solid.makeBox(12, 12, 0.2),
                    cq.Location((-66, 29, 35)),
                ),
                ("spacer2", cq.Solid.makeBox(4, 4, 4), cq.Location((-66, 38, 5))),
            ]
        )
    assy = cq.Assembly(name=code)
    for id, shape, loc in parts:
        assy.add(shape, name=id, loc=loc)
    assy.export(str(directory / "assembly.step"))
    imported = import_step(directory / "assembly.step")
    # Source paths come from real XDE traversal, not a display-name identity lookup.
    assert len(imported.occurrences) == len(parts)
    components = []
    for (id, _, _), o in zip(parts, imported.occurrences):
        fixed = id not in ("target", "screw1", "screw2", "cover")
        role = (
            "service_module"
            if id == "target"
            else "fastener"
            if id.startswith("screw")
            else "bracket"
            if id == "bridge"
            else "cover"
            if id == "cover"
            else "chassis"
        )
        components.append(
            dict(
                id=id,
                source_occurrence_path=o.source_occurrence_path,
                display_name=id,
                role=role,
                fixed=fixed,
                replaceable=id == "target",
                removal_axes=[] if fixed else ["Z+"],
                staging_region_id=None if fixed else "above",
                bounds_mm=bounds(o.shape).model_dump(),
                placement=o.placement.model_dump(),
            )
        )
    regions = []
    bindings = []
    if code != "B01":
        regions = [
            dict(
                id="web",
                component_id="bridge",
                kind="editable",
                bounds_mm=bracket.web.model_dump(),
            )
        ]
        bindings = [binding.model_dump(mode="json")]
    constraints = [
        dict(
            id="target_path",
            kind="clearance",
            mandatory=True,
            label="Target complete upward segment",
            component_ids=["target"],
            limit="0.5 mm continuous gap",
            threshold_mm=0.5,
            scope="path",
            axis="Z+",
            distance_mm=80,
        )
    ]
    connections = []
    tools = []
    if code == "B03":
        tools = [
            dict(
                id="driver",
                type="screwdriver",
                tip_type="PH1",
                shaft_radius_mm=2,
                shaft_length_mm=50,
                handle_radius_mm=8,
                handle_length_mm=30,
                approach_distance_mm=20,
                permitted_axis="Z+",
            )
        ]
        connections = [
            dict(
                id="screw_cover",
                kind="screw_retainer",
                fastener_id="screw1",
                retained_component_ids=["cover"],
                host_component_id="base",
                tool_id="driver",
                axis_world=[0, 0, 1],
                head_origin_mm=[-60, 35, 14],
                extraction_distance_mm=30,
                engagement_region_id="engage1",
            )
        ]
        regions.append(
            dict(
                id="engage1",
                component_id="screw1",
                kind="engagement",
                bounds_mm=dict(min=[-63, 32, 7], max=[-57, 38, 14]),
                plane_axis="Z",
                plane_coordinate_mm=14,
            )
        )
    manifest = dict(
        schema_version="1.0",
        project_id=f"fixture_{code}",
        assembly_id=code,
        units="mm",
        frame=dict(handedness="right", up="Z"),
        envelope_mm=dict(min=[-80, -60, -15], max=[80, 60, 50]),
        components=components,
        connections=connections,
        tools=tools,
        constraints=constraints,
        keep_outs=[],
        template_bindings=bindings,
        regions=regions,
        staging_regions=[
            dict(id="above", bounds_mm=dict(min=[-100, -100, 70], max=[100, 100, 160]))
        ],
        unsupported_assumptions=[],
        provenance=dict(B02_PROVENANCE)
        if code == "B02" and not held_out
        else dict(
            author="UNLOCK synthetic constructor",
            license="Redistribution license pending author approval; local engineering fixture",
            source=f"unlock_engine.fixtures.generate_fixture({code}, held_out={held_out}); deterministic seed 0",
        ),
    )
    Manifest.model_validate(manifest)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (directory / "oracle.json").write_text(
        json.dumps(
            dict(
                synthetic=True,
                held_out=held_out,
                leaf_count=len(parts),
                target_box_mm=[22 if held_out else 20, 8, 12],
                expected_upward_path="clear" if code == "B01" else "blocked",
                expected_t01_upward_path="clear" if code == "B02" else None,
                explanation="Target Z segment crosses full web at z=34..38; T01 x=[-20,20], y=[-28,-12] encloses target x=[-10,10 or 12], y=[-24,-16]. B03 driver crosses thin plate at z=35.",
                repeated_definition_ids=["screw1", "screw2"],
            ),
            indent=2,
        )
    )
    return directory
