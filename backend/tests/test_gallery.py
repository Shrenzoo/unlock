"""Gallery fixtures: real STEP, analysis-ready, licensed, and true to their pre-registered outcomes."""

import json
import uuid

import pytest

from unlock_engine.deployment import jobs
from unlock_engine.deployment.snapshot import SnapshotStore
from unlock_engine.fixture_catalog import GALLERY
from unlock_engine.fixture_license import GRANTS
from unlock_engine.fixtures import generate_fixture
from unlock_engine.service import import_revision


# The boxes each target's outcome was registered with. Motion is certified with
# boxes, so target detail must stay inside them.
TARGET_BOXES = dict(
    B04=([-10, -5, 14], [10, 5, 36]),
    B05=([-22, 4, 10], [22, 26, 26]),
    B06=([-7, -22, 12], [7, -18, 22]),
    B07=([55, 35, 20], [75, 45, 22]),
    B08=([-20, -12, 2], [20, 12, 16]),
)


def _path_crossings(manifest):
    """Fixed parts whose box meets the upward sweep of a moving part or the driver."""
    guard = 0.52  # clearance plus numerical guard, rounded up
    sweeps = [
        (c["id"], c["bounds_mm"]["min"], c["bounds_mm"]["max"], 0)
        for c in manifest["components"]
        if not c["fixed"]
    ]
    sweeps += [
        (s["id"], s["head_origin_mm"], s["head_origin_mm"], 8)
        for s in manifest["connections"]
    ]
    crossings = []
    for name, low, high, radius in sweeps:
        reach = radius + guard
        for c in manifest["components"]:
            # The bracket and the B07 shield are the intended obstructions.
            if not c["fixed"] or c["id"] in ("bridge", "shield"):
                continue
            b = c["bounds_mm"]
            if b["max"][2] >= low[2] - guard and all(
                b["min"][k] <= high[k] + reach and low[k] - reach <= b["max"][k]
                for k in (0, 1)
            ):
                crossings.append((c["id"], name))
    return crossings


@pytest.mark.parametrize("code", sorted(GALLERY))
def test_gallery_fixture_is_ready_licensed_and_distinct(code, tmp_path):
    directory = generate_fixture(tmp_path / code, code)
    manifest = json.loads((directory / "manifest.json").read_text())
    revision = import_revision(directory / "assembly.step", manifest)
    inventory = revision.inventory()
    assert all(r["ok"] for r in inventory["readiness"]), inventory["readiness"]
    assert 5 <= len(inventory["components"]) <= 12
    assert manifest["provenance"] == GRANTS[code]
    target = next(c for c in manifest["components"] if c["id"] == "target")
    assert target["replaceable"] and target["display_name"] != "target"
    low, high = TARGET_BOXES[code]
    assert target["bounds_mm"]["min"] == pytest.approx(low, abs=1e-6)
    assert target["bounds_mm"]["max"] == pytest.approx(high, abs=1e-6)
    assert not _path_crossings(manifest)
    # Detailed parts, not placeholder blocks (the first gallery had about 60 faces).
    # Modal's CPU caps the detail, so the lightest fixture (B07) has about 190.
    assert sum(c["face_count"] for c in inventory["components"]) >= 180
    assert target["id"] in {
        c["id"] for c in inventory["components"] if c["face_count"] > 20
    }
    oracle = json.loads((directory / "oracle.json").read_text())
    assert oracle["expected_outcome"] == GALLERY[code]["expected"]


def test_path_check_flags_only_parts_above_a_moving_part():
    def box(low, high):
        return dict(min=low, max=high)

    manifest = dict(
        components=[
            dict(id="target", fixed=False, bounds_mm=box([0, 0, 10], [10, 10, 20])),
            dict(id="lamp", fixed=True, bounds_mm=box([5, 5, 40], [8, 8, 45])),
            dict(id="cradle", fixed=True, bounds_mm=box([-2, -2, 0], [12, 12, 9])),
            dict(id="board", fixed=True, bounds_mm=box([11, 0, 30], [20, 10, 31])),
        ],
        connections=[],
    )
    assert _path_crossings(manifest) == [("lamp", "target")]


def test_gallery_layouts_differ_from_b02(tmp_path):
    def signature(code):
        d = generate_fixture(tmp_path / code, code)
        return (d / "assembly.step").read_bytes(), json.loads(
            (d / "manifest.json").read_text()
        )["template_bindings"]

    seen = {signature("B02")[0]}
    for code in GALLERY:
        step, _ = signature(code)
        assert step not in seen
        seen.add(step)
    assert signature("B05")[1][0]["templates"][0]["id"] == "T02"
    assert signature("B06")[1][0]["maximum_cut_volume_mm3"] == 1200
    assert signature("B08")[1] == []


@pytest.mark.gallery
@pytest.mark.parametrize("code", sorted(GALLERY))
def test_full_offline_run_matches_pre_registered_outcome(code, tmp_path):
    id = uuid.uuid4().hex
    result = jobs.run_job(tmp_path, id, fixture=code)
    assert result["outcome"] == GALLERY[code]["expected"]
    run = SnapshotStore(tmp_path / id).get("run", result["run_id"])
    assert (run["model"] or {}).get("live", False) is False
    if result["outcome"] == "VERIFIED_IMPROVEMENT_FOUND":
        assert run["baseline"]["status"] == "no_path_supported"
        assert run["export"]["roundtrip_status"] == "passed"
    else:
        assert result["export_sha256"] is None and not run.get("export")
