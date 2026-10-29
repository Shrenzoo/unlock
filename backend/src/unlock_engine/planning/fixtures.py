"""Additional synthetic assemblies with manually enumerable semantic oracles."""

import json
from pathlib import Path

import cadquery as cq

from ..assembly import import_step
from ..contracts import Manifest
from ..geometry import bounds


def sequence_fixture(
    directory,
    *,
    tools=("driver_a", "driver_a"),
    cover_fixed=False,
    seats=False,
    thin_obstacle=False,
):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    parts = [
        ("base", cq.Solid.makeBox(80, 60, 3).translate((-30, -30, -8))),
        ("target", cq.Solid.makeBox(10, 10, 10)),
        ("cover", cq.Solid.makeBox(40, 30, 1).translate((-15, -15, 30))),
        ("screw1", cq.Solid.makeCylinder(1, 4).translate((-8, -8, 10))),
        ("screw2", cq.Solid.makeCylinder(1, 4).translate((18, -8, 10))),
    ]
    if seats:
        parts[0] = ("base", cq.Solid.makeBox(10, 10, 3).translate((0, 0, -3)))
    if thin_obstacle:
        parts.append(
            ("hidden_plate", cq.Solid.makeBox(10, 10, 0.001).translate((0, 0, 60)))
        )
    assy = cq.Assembly(name="synthetic_sequence")
    for k, s in parts:
        assy.add(s, name=k)
    assy.export(str(root / "assembly.step"))
    imported = import_step(root / "assembly.step")
    components, regions, connections = [], [], []
    for (k, _), occurrence in zip(parts, imported.occurrences):
        fixed = k in ("base", "hidden_plate") or (k == "cover" and cover_fixed)
        axes = [] if fixed else ["X+", "Y+"] if k == "cover" else ["Z+"]
        components.append(
            dict(
                id=k,
                source_occurrence_path=occurrence.source_occurrence_path,
                display_name="Repeated screw" if k.startswith("screw") else k,
                role="fastener"
                if k.startswith("screw")
                else "service_module"
                if k == "target"
                else "cover"
                if k == "cover"
                else "chassis",
                fixed=fixed,
                replaceable=k == "target",
                removal_axes=axes,
                staging_region_id=None
                if fixed
                else "side"
                if k == "cover"
                else "above",
                bounds_mm=bounds(occurrence.shape).model_dump(),
                placement=occurrence.placement.model_dump(),
            )
        )
    for i, x in enumerate((-8, 18), 1):
        k = f"screw{i}"
        regions.append(
            dict(
                id=f"engage{i}",
                component_id=k,
                kind="engagement",
                bounds_mm=dict(min=[x - 2, -10, 9], max=[x + 2, -6, 14]),
                plane_axis="Z",
                plane_coordinate_mm=14,
            )
        )
        connections.append(
            dict(
                id=f"retainer{i}",
                kind="screw_retainer",
                fastener_id=k,
                retained_component_ids=["target"],
                host_component_id="base",
                tool_id=tools[i - 1],
                axis_world=[0, 0, 1],
                head_origin_mm=[x, -8, 14],
                extraction_distance_mm=80,
                engagement_region_id=f"engage{i}",
            )
        )
    if seats:
        for k, z0, z1 in (("target", 0, 10), ("base", -3, 0)):
            regions.append(
                dict(
                    id=f"seat_{k}",
                    component_id=k,
                    kind="contact",
                    bounds_mm=dict(
                        min=[-0.01, -0.01, z0 - 0.01], max=[10.01, 10.01, z1 + 0.01]
                    ),
                    plane_axis="Z",
                    plane_coordinate_mm=0,
                )
            )
        connections.append(
            dict(
                id="target_seat",
                kind="planar_seat",
                component_a_id="target",
                component_b_id="base",
                region_a_id="seat_target",
                region_b_id="seat_base",
                outward_normal_world=[0, 0, 1],
            )
        )
    manifest = dict(
        schema_version="1.0",
        project_id="synthetic_sequence",
        assembly_id="sequence_v1",
        units="mm",
        frame=dict(handedness="right", up="Z"),
        envelope_mm=dict(min=[-35, -35, -10], max=[55, 40, 65]),
        components=components,
        connections=connections,
        tools=[
            dict(
                id=k,
                type="screwdriver",
                tip_type=k,
                shaft_radius_mm=1,
                shaft_length_mm=12,
                handle_radius_mm=3,
                handle_length_mm=6,
                approach_distance_mm=20,
                permitted_axis="Z+",
            )
            for k in sorted(set(tools))
        ],
        constraints=[
            dict(
                id="target_path",
                kind="clearance",
                mandatory=True,
                label="Target staged upward",
                component_ids=["target"],
                limit="0.5mm",
                threshold_mm=0.5,
                scope="path",
                axis="Z+",
                distance_mm=80,
            )
        ],
        keep_outs=[],
        template_bindings=[],
        regions=regions,
        staging_regions=[
            dict(id="above", bounds_mm=dict(min=[-60, -60, 70], max=[60, 60, 150])),
            dict(id="side", bounds_mm=dict(min=[-60, -40, 20], max=[160, 160, 40])),
        ],
        unsupported_assumptions=[],
        provenance=dict(
            author="UNLOCK synthetic constructor",
            license="Redistribution license pending author approval; local engineering fixture",
            source="planning.fixtures.sequence_fixture; deterministic seed 0; screw mating and workholding are explicit abstractions",
        ),
    )
    Manifest.model_validate(manifest)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (root / "oracle.json").write_text(
        json.dumps(
            dict(
                synthetic=True,
                tools=tools,
                cover_fixed=cover_fixed,
                expected="no_path_supported"
                if cover_fixed or thin_obstacle
                else "feasible",
                cost=None
                if cover_fixed or thin_obstacle
                else [1, 2, int(tools[0] != tools[1]), 4],
                ordering="cover before both screws; both screws before target; cover has two geometric axis routes",
                seats=seats,
                thin_obstacle=thin_obstacle,
            ),
            indent=2,
        )
    )
    return root
