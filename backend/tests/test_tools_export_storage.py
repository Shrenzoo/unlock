import json
from pathlib import Path
import threading
import zipfile

import cadquery as cq
import pytest

from unlock_engine.artifacts import ArtifactStore, atomic_write
from unlock_engine.contracts import EngineError, POLICY, Region, Screw, Tool
from unlock_engine.export import export_bundle
from unlock_engine.geometry import fingerprint, validate_solid
from unlock_engine.package import load_files
from unlock_engine.preview import preview_meshes
from unlock_engine.service import import_revision
from unlock_engine.tools import evaluate_fastener, tool_approach, tool_solid
from unlock_engine.worker import isolated_import


def tool_inputs():
    tool = Tool(
        id="driver",
        type="screwdriver",
        tip_type="PH1",
        shaft_radius_mm=2,
        shaft_length_mm=30,
        handle_radius_mm=6,
        handle_length_mm=20,
        approach_distance_mm=15,
        permitted_axis="Z+",
    )
    screw = Screw(
        id="ret",
        kind="screw_retainer",
        fastener_id="screw",
        retained_component_ids=("cover",),
        host_component_id="base",
        tool_id="driver",
        axis_world=(0, 0, 1),
        head_origin_mm=(0, 0, 6),
        extraction_distance_mm=20,
        engagement_region_id="engage",
    )
    region = Region(
        id="engage",
        component_id="screw",
        kind="engagement",
        bounds_mm={"min": (-2, -2, 0), "max": (2, 2, 6)},
        plane_axis="Z",
        plane_coordinate_mm=6,
    )
    return tool, screw, region, cq.Solid.makeCylinder(2, 6)


def test_tool_real_shaft_handle_and_clear_engagement():
    t, s, r, fastener = tool_inputs()
    solid = tool_solid(t, s.head_origin_mm)
    assert validate_solid(solid)["volume_mm3"] == pytest.approx(
        3.141592653589793 * (2**2 * 30 + 6**2 * 20)
    )
    assert tool_approach(t, s, {"screw": fastener}, r).status == "clear"
    assert evaluate_fastener(t, s, fastener, {}, r)["status"] == "clear"


def test_tool_handle_conflict_not_masked_by_thin_shaft():
    t, s, r, fastener = tool_inputs()
    blocker = cq.Solid.makeBox(1, 1, 0.1).translate((4, 0, 45))
    result = tool_approach(t, s, {"screw": fastener, "handle_blocker": blocker}, r)
    assert result.status == "blocked"
    assert any("handle_blocker" in x.component_ids for x in result.findings)


def test_missing_and_wrong_engagement_rejected():
    t, s, r, fastener = tool_inputs()
    with pytest.raises(EngineError):
        tool_approach(
            t,
            s,
            {"screw": fastener},
            r.model_copy(update={"component_id": "unrelated"}),
        )
    with pytest.raises(EngineError):
        tool_approach(t, s, {}, r)


def test_fixture_b03_blocked_tool_access(fixture_dirs):
    p = fixture_dirs["B03"]
    rev = import_revision(
        p / "assembly.step", json.loads((p / "manifest.json").read_text())
    )
    assert rev.ready
    m = rev.manifest
    source = rev.by_id()
    s = m.connections[0]
    t = m.tools[0]
    r = next(r for r in m.regions if r.id == s.engagement_region_id)
    result = evaluate_fastener(
        t,
        s,
        source[s.fastener_id].shape,
        {k: o.shape for k, o in source.items() if k != s.fastener_id},
        r,
    )
    assert result["tool_access"].status == "blocked"


def test_full_assembly_export_round_trip_and_artifacts(revision, candidate, tmp_path):
    before = {k: fingerprint(o.shape) for k, o in revision.by_id().items()}
    exported = export_bundle(revision, candidate, tmp_path)
    assert (
        exported["status"] == "full_assembly"
        and exported["roundtrip_status"] == "passed"
    )
    assert before == {k: fingerprint(o.shape) for k, o in revision.by_id().items()}
    with zipfile.ZipFile(exported["zip_path"]) as z:
        assert {
            "original.step",
            "revised.step",
            "changed_bracket.step",
            "manifest.json",
            "paths.json",
            "verification.json",
            "geometry_difference.json",
            "limitations.txt",
        } <= set(z.namelist())
        rt = json.loads(z.read("roundtrip.json"))
        assert (
            rt["occurrences"] == 8
            and rt["independent_verification"]["status"] == "passed"
        )
        assert max(rt["symmetric_differences_mm3"].values()) <= POLICY.volume_noise_mm3
        assert json.loads(z.read("geometry_difference.json"))[
            "removed_volume_mm3"
        ] == pytest.approx(2560)
        assert json.loads(z.read("preview.json"))["authoritative"] is False
        provenance = json.loads(z.read("manifest.json"))["provenance"]
        assert provenance["license"] == "CC-BY-4.0"
        assert "UNLOCK team" in provenance["author"]
        assert (
            "https://creativecommons.org/licenses/by/4.0/"
            in z.read("LICENSE-B02.txt").decode()
        )
        assert "CadQuery 2.6.1" in z.read("THIRD_PARTY_NOTICES.txt").decode()


def test_assembly_writer_failure_truthfully_falls_back(
    revision, candidate, tmp_path, monkeypatch
):
    import unlock_engine.export as module

    def fail(*args, **kwargs):
        raise OSError("disk/native export failure")

    monkeypatch.setattr(module, "export_assembly", fail)
    exported = export_bundle(revision, candidate, tmp_path)
    assert (
        exported["status"] == "changed_part_only"
        and exported["roundtrip_status"] == "failed"
    )
    assert (
        "revised.step" not in exported["files"]
        and "changed_bracket.step" in exported["files"]
    )


def test_part_writer_failure_has_no_completed_bundle(
    revision, candidate, tmp_path, monkeypatch
):
    import unlock_engine.export as module

    def fail(*args, **kwargs):
        raise OSError("no output")

    monkeypatch.setattr(module.cq.exporters, "export", fail)
    with pytest.raises(OSError):
        export_bundle(revision, candidate, tmp_path)
    assert not list(tmp_path.glob("*.bundle.json"))


def test_preview_scale_applied_once_and_no_original_mutation():
    s = cq.Solid.makeBox(1000, 20, 30)
    h = fingerprint(s)
    p = preview_meshes({"occ": s})
    vertices = p["components"][0]["vertices_m"]
    assert max(v[0] for v in vertices) - min(v[0] for v in vertices) == pytest.approx(1)
    assert p["units"] == "m" and p["scale_already_applied"]
    assert fingerprint(s) == h


def test_cas_hashes_idempotent_and_rejects_paths(tmp_path):
    s = ArtifactStore(tmp_path)
    h = s.put(b"original")
    assert s.put(b"original") == h and s.get(h) == b"original"
    with pytest.raises(EngineError):
        s.get("../etc/passwd")
    (tmp_path / h[:2] / h).write_bytes(b"corrupt")
    with pytest.raises(EngineError):
        s.get(h)
    with pytest.raises(EngineError):
        s.put(b"original")


def test_interrupted_atomic_write_preserves_original(tmp_path, monkeypatch):
    p = tmp_path / "original"
    atomic_write(p, b"original")
    import unlock_engine.artifacts as module

    def fail(*args):
        raise OSError("interrupted before atomic rename")

    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(OSError):
        atomic_write(p, b"candidate")
    assert p.read_bytes() == b"original" and not list(tmp_path.glob(".pending-*"))


def test_native_worker_timeout_and_cancellation(fixture_dirs):
    p = fixture_dirs["B01"]
    package = load_files(
        {n: (p / n).read_bytes() for n in ("assembly.step", "manifest.json")}
    )
    with pytest.raises(EngineError, match="timed out"):
        isolated_import(package, timeout_seconds=0.001)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(EngineError, match="cancelled"):
        isolated_import(package, cancel_event=cancel)


def test_native_worker_real_import(fixture_dirs, monkeypatch):
    # The child uses the same pinned runtime and installed module source.

    monkeypatch.setenv("PYTHONPATH", str(Path("backend/src").resolve()))
    p = fixture_dirs["B01"]
    package = load_files(
        {n: (p / n).read_bytes() for n in ("assembly.step", "manifest.json")}
    )
    inventory = isolated_import(package)
    assert len(inventory["components"]) == 5 and all(
        x["ok"] for x in inventory["readiness"]
    )


def test_abrupt_native_process_crash_has_no_success(fixture_dirs, monkeypatch):
    import sys
    import unlock_engine.worker as module

    original_popen = module.subprocess.Popen

    def killed_worker(command, **kwargs):
        return original_popen(
            [
                sys.executable,
                "-c",
                "import os, signal; os.kill(os.getpid(), signal.SIGKILL)",
            ],
            **kwargs,
        )

    monkeypatch.setattr(module.subprocess, "Popen", killed_worker)
    p = fixture_dirs["B01"]
    package = load_files(
        {n: (p / n).read_bytes() for n in ("assembly.step", "manifest.json")}
    )
    with pytest.raises(EngineError, match="interrupted"):
        isolated_import(package)
