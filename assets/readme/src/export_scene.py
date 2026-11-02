"""Export the real geometry the README's visuals are rendered from.

Nothing here is modelled by hand. Each fixture is generated and imported by the
engine, tessellated from its BRep, and paired with the planner's own witness.
Redesigned brackets are rebuilt by the trusted constructor, and the script exits
unless a rebuilt bracket's geometry hash equals the design recorded in evidence.

usage (from the repository root):
  PYTHONPATH=backend/src backend/.venv/bin/python assets/readme/src/export_scene.py
"""

import json
import tempfile
from pathlib import Path

import cadquery as cq
import numpy as np
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from unlock_engine.fixture_catalog import EXPECTED
from unlock_engine.fixtures import generate_fixture
from unlock_engine.geometry import boolean, volume
from unlock_engine.planning.contracts import SearchPolicy
from unlock_engine.planning.problem import Problem
from unlock_engine.planning.service import plan_problem
from unlock_engine.service import construct_candidate, import_revision
from unlock_engine.templates import SERVER_DOMAINS, construct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILD = HERE / ".build"
EVIDENCE = ROOT / "backend" / "evidence"

# Designs recorded in evidence. B02 and B05 are the live Muse Spark 1.3 choices;
# B04 and B06 are the offline scripted policy's verified designs in the gallery.
DESIGNS = {
    "B02": dict(
        template="T01", center_x_mm=0.0, center_y_mm=-20.0, width_mm=40.0, depth_mm=16.0
    ),
    "B04": dict(
        template="T01", center_x_mm=0.0, center_y_mm=0.0, width_mm=24.0, depth_mm=12.0
    ),
    "B05": dict(template="T02", offset_y_mm=-12.0),
    "B06": dict(
        template="T01", center_x_mm=0.0, center_y_mm=-20.0, width_mm=24.0, depth_mm=8.0
    ),
}
WEB_MOTION_FRAMES = 61
LIVE_REPORTS = dict(
    B02=EVIDENCE / "live-b02/live_run.json", B05=EVIDENCE / "live-b05/live_run.json"
)


def tessellate(shape, deflection=0.05, angle=0.12):
    # Vertices stay per BRep face, so smooth shading keeps every CAD edge sharp.
    vertices, triangles = shape.copy().tessellate(deflection, angle)
    return dict(
        vertices=[round(c, 4) for v in vertices for c in v.toTuple()],
        triangles=[i for t in triangles for i in t],
    )


def feature_edges(shape, chord=0.6):
    """BRep edges as polylines, without the seams of closed surfaces."""
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    out = []
    for edge in shape.Edges():
        unique = []
        for face in ancestors.FindFromKey(edge.wrapped):
            if not any(face.IsSame(u) for u in unique):
                unique.append(face)
        if len(unique) < 2:
            continue
        n = (
            2
            if edge.geomType() == "LINE"
            else max(6, min(96, int(edge.Length() / chord)))
        )
        points = edge.positions(np.linspace(0, 1, n))
        out.append([round(c, 4) for p in points for c in p.toTuple()])
    return out


def solid_payload(shape):
    return dict(mesh=tessellate(shape), edges=feature_edges(shape))


def bounds(shape):
    box = shape.BoundingBox()
    return [[box.xmin, box.ymin, box.zmin], [box.xmax, box.ymax, box.zmax]]


def live_candidate_hash(report_path):
    evidence = json.loads(report_path.read_text())["engineering_evidence"]
    for verified in evidence["verified"].values():
        for constructed in evidence["constructed"].values():
            candidate = constructed["candidate"]
            if candidate["id"] == verified["candidate_id"]:
                return candidate["geometry_hash"]
    raise SystemExit(f"{report_path}: no verified candidate")


def find_witnesses(plan, target):
    certificates = {c.id: c for c in plan.certificates}
    witnesses = []
    for rejection in plan.rejections:
        action = rejection.action
        if (
            action.component_id != target
            or rejection.category != "CONFIRMED_GEOMETRIC_OBSTRUCTION"
        ):
            continue
        for cid in rejection.witness_certificate_ids:
            for path in certificates[cid].paths:
                for finding in path.findings:
                    if finding.witness_mm:
                        witnesses.append(
                            dict(
                                axis=action.axis,
                                point_mm=[round(v, 3) for v in finding.witness_mm],
                                travel_mm=finding.witness_travel_mm,
                                component_ids=list(finding.component_ids),
                            )
                        )
    return witnesses


def interference(target, blocker, witness):
    """The witness's actual overlap: the target moved by the certified travel."""
    axis = dict(X=0, Y=1, Z=2)[witness["axis"][0]]
    sign = 1 if witness["axis"][1] == "+" else -1
    offset = [0.0, 0.0, 0.0]
    offset[axis] = sign * witness["travel_mm"]
    moved = target.moved(cq.Location(cq.Vector(*offset)))
    return boolean("common", moved, blocker)


def steps(plan):
    return [
        dict(
            kind=s.kind,
            component=s.component_id,
            axis=s.axis,
            distance_mm=s.distance_mm,
            tool=s.tool_id,
        )
        for s in plan.steps
    ]


def export_fixture(code):
    directory = generate_fixture(Path(tempfile.mkdtemp()) / code, code)
    manifest = json.loads((directory / "manifest.json").read_text())
    revision = import_revision(directory / "assembly.step", manifest)
    shapes = {
        c["id"]: o.shape
        for c in manifest["components"]
        for o in revision.assembly.occurrences
        if o.source_occurrence_path == c["source_occurrence_path"]
    }
    plan = plan_problem(Problem(revision, "target", SearchPolicy()))
    scene = dict(
        code=code,
        expected_outcome=EXPECTED[code],
        baseline_status=plan.status,
        baseline_steps=steps(plan),
        witnesses=find_witnesses(plan, "target"),
        components=[
            dict(
                id=c["id"],
                label=c.get("display_name"),
                role=c.get("role"),
                bounds_mm=bounds(shapes[c["id"]]),
                **solid_payload(shapes[c["id"]]),
            )
            for c in manifest["components"]
        ],
    )

    if scene["witnesses"]:
        witness = scene["witnesses"][0]
        overlap = interference(shapes["target"], shapes["bridge"], witness)
        witness["overlap_mm3"] = round(volume(overlap), 3)
        scene["interference"] = solid_payload(overlap)

    design = DESIGNS.get(code)
    if design:
        parameters = {k: v for k, v in design.items() if k != "template"}
        candidate = construct_candidate(
            revision, "bridge", design["template"], parameters
        )
        recorded = None
        if code in LIVE_REPORTS:
            recorded = live_candidate_hash(LIVE_REPORTS[code])
            if candidate.geometry_hash != recorded:
                raise SystemExit(
                    f"{code}: rebuilt bracket differs from the live run's verified design"
                )
        revised = candidate.shapes["bridge"]
        removed = boolean("cut", shapes["bridge"], revised)
        added = boolean("cut", revised, shapes["bridge"])
        scene["design"] = dict(
            template=design["template"],
            parameters=parameters,
            geometry_hash=candidate.geometry_hash,
            matches_live_run=recorded is not None,
            removed_mm3=round(volume(removed), 3),
            added_mm3=round(volume(added), 3),
            revised=solid_payload(revised),
            removed=solid_payload(removed) if volume(removed) > 1e-6 else None,
        )
    if design and design["template"] == "T02":
        # Every position the server allows, drawn so the finite choice is visible.
        scene["allowed_positions"] = [
            dict(
                offset_y_mm=value,
                edges=feature_edges(
                    construct_candidate(
                        revision, "bridge", "T02", dict(offset_y_mm=value)
                    ).shapes["bridge"]
                ),
            )
            for value in SERVER_DOMAINS["T02"]["offset_y_mm"]
        ]
        # The move itself: the constructor's own solid at each animation frame. Only
        # the last, -12 mm, is the verified design; the rest exist to show the motion.
        binding = revision.manifest.template_bindings[0]
        target_offset = design["offset_y_mm"]
        scene["web_motion"] = [
            dict(
                offset_y_mm=target_offset * i / (WEB_MOTION_FRAMES - 1),
                **solid_payload(
                    construct(
                        binding, offset=target_offset * i / (WEB_MOTION_FRAMES - 1)
                    ).shape
                ),
            )
            for i in range(WEB_MOTION_FRAMES)
        ]
    return scene


def main():
    BUILD.mkdir(exist_ok=True)
    provenance = {}
    for code in ("B02", "B04", "B05", "B06", "B07", "B08"):
        scene = export_fixture(code)
        (BUILD / f"{code}.json").write_text(json.dumps(scene, separators=(",", ":")))
        design = scene.get("design") or {}
        provenance[code] = dict(
            expected_outcome=scene["expected_outcome"],
            baseline_status=scene["baseline_status"],
            baseline_steps=scene["baseline_steps"],
            parts={c["id"]: c["role"] for c in scene["components"]},
            witnesses=scene["witnesses"][:2],
            design={
                k: design[k]
                for k in (
                    "template",
                    "parameters",
                    "geometry_hash",
                    "matches_live_run",
                    "removed_mm3",
                    "added_mm3",
                )
            }
            if design
            else None,
        )
        print(code, scene["baseline_status"], flush=True)
    (HERE / "scene_provenance.json").write_text(
        json.dumps(provenance, indent=1) + "\n"
    )


if __name__ == "__main__":
    main()
