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
    oracle = json.loads((directory / "oracle.json").read_text())
    assert oracle["expected_outcome"] == GALLERY[code]["expected"]


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
