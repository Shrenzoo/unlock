"""Export the real data the demo video animates. Nothing here is drawn by hand.

- B05 meshes, original and with the strap moved -12 mm, tessellated by the engine.
- The BRep witness of the confirmed obstruction, recomputed by the planner.
- The live Muse Spark 1.3 run's decision sequence, from the committed evidence.

usage (from the repository root):
  PYTHONPATH=backend/src backend/.venv/bin/python video/scripts/export_data.py
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

from unlock_engine.ai.schemas import TOOL_ARGS
from unlock_engine.fixture_catalog import EXPECTED, GALLERY, NAMES
from unlock_engine.fixtures import generate_fixture
from unlock_engine.planning.contracts import SearchPolicy
from unlock_engine.planning.problem import Problem
from unlock_engine.planning.service import plan_problem
from unlock_engine.preview import preview_meshes
from unlock_engine.service import construct_candidate, import_revision

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "video" / "public" / "data"
LIVE = ROOT / "backend" / "evidence" / "live-b05" / "live_run.json"
LIVE_GEOMETRY_HASH = "c9b46d5ad8a9b1784a1284c8e066a7157646a93900053359bde8fdc7baf1e2d2"


def mesh(preview):
    out = {}
    for c in preview["components"]:
        out[c["occurrence_id"]] = dict(
            vertices=[round(v * 1000, 2) for p in c["vertices_m"] for v in p],
            indices=[i for t in c["triangles"] for i in t],
        )
    return out


def b05():
    directory = generate_fixture(Path(tempfile.mkdtemp()) / "B05", "B05")
    manifest = json.loads((directory / "manifest.json").read_text())
    revision = import_revision(directory / "assembly.step", manifest)
    shapes = {
        c["id"]: o.shape
        for c in manifest["components"]
        for o in revision.assembly.occurrences
        if o.source_occurrence_path == c["source_occurrence_path"]
    }
    candidate = construct_candidate(revision, "bridge", "T02", {"offset_y_mm": -12.0})
    if candidate.geometry_hash != LIVE_GEOMETRY_HASH:
        raise SystemExit("candidate differs from the live run's verified design")
    plan = plan_problem(Problem(revision, "target", SearchPolicy()))
    certificates = {c.id: c for c in plan.certificates}
    witness = None
    for rejection in plan.rejections:
        action = rejection.action
        if (action.component_id, action.axis, rejection.category) != (
            "target",
            "Z+",
            "CONFIRMED_GEOMETRIC_OBSTRUCTION",
        ):
            continue
        for cid in rejection.witness_certificate_ids:
            for path in certificates[cid].paths:
                for f in path.findings:
                    if f.witness_mm and "bridge" in f.component_ids:
                        witness = dict(
                            point_mm=[round(v, 2) for v in f.witness_mm],
                            travel_mm=f.witness_travel_mm,
                            component_ids=list(f.component_ids),
                        )
                        break
    original = mesh(preview_meshes(shapes))
    revised = mesh(preview_meshes({"bridge": candidate.shapes["bridge"]}))
    components = [
        dict(id=c["id"], label=c["display_name"], role=c["role"], **original[c["id"]])
        for c in manifest["components"]
    ]
    return dict(
        units="mm",
        up="Z",
        components=components,
        revised_bridge=revised["bridge"],
        candidate=dict(
            template="T02",
            parameters={"offset_y_mm": -12.0},
            geometry_hash=candidate.geometry_hash,
        ),
        witness=witness,
        removal=dict(component_id="target", axis="Z+", distance_mm=80.0),
    )


def timeline():
    run = json.loads(LIVE.read_text())
    events = run["events"]
    start = datetime.fromisoformat(events[0]["at"])
    rows = []
    turn = 0
    for e in events:
        t = round((datetime.fromisoformat(e["at"]) - start).total_seconds(), 1)
        if e["kind"] == "model_turn":
            turn += 1
            rows.append(dict(t=t, kind="turn", turn=turn, note=e.get("note")))
        elif e["kind"] == "tool_call":
            row = dict(t=t, kind="tool", turn=turn, tool=e["tool"], status=e["status"])
            proposal = (e.get("arguments") or {}).get("proposal")
            if proposal:
                row.update(
                    parameters=proposal["parameters"],
                    evidence_ids=proposal["evidence_ids"],
                    rationale=proposal["rationale"],
                )
            rows.append(row)
        elif e["kind"] == "stage" and e.get("status") == "no_path_supported":
            rows.append(dict(t=t, kind="baseline", status="no_path_supported"))
        elif e["kind"] == "final":
            rows.append(dict(t=t, kind="final", outcome=e["status"]))
    candidate = run["candidates"][0]
    checks = {}

    def walk(o):
        if isinstance(o, dict):
            if "constraint_id" in o and "result" in o:
                checks.setdefault(o["constraint_id"], o["result"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(candidate)
    plan = candidate["revised_plan"]
    usage = run["usage"]
    return dict(
        run_id=run["run_id"],
        model=run["model"]["model_id"],
        generated_at=run["generated_at"],
        total_s=run["timings"]["total_s"],
        tool_calls=usage["tool_calls"],
        rejected_calls=usage["rejected_calls"],
        turns=usage["turns"],
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        tools=list(TOOL_ARGS),
        tools_used=sorted({e["tool"] for e in rows if e["kind"] == "tool"}),
        stages=candidate["stages"],
        checks=[dict(id=k, result=v) for k, v in checks.items()],
        changed_volume_mm3=candidate["construction"]["changed_volume_mm3"],
        plan_steps=plan["steps"],
        replay=plan["replay"],
        reverse=plan["reverse"],
        events=rows,
    )


def gallery():
    rows = [dict(code="B02", name=NAMES["B02"], outcome=EXPECTED["B02"])]
    rows += [
        dict(
            code=code,
            name=g["name"],
            description=g["description"],
            outcome=g["expected"],
        )
        for code, g in GALLERY.items()
    ]
    return rows


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("b05", b05()),
        ("live_run", timeline()),
        ("gallery", gallery()),
    ):
        (OUT / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")))
        print(name, (OUT / f"{name}.json").stat().st_size, "bytes")
