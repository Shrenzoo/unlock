import io
import json
import stat
import zipfile

import cadquery as cq
import pytest

from unlock_engine.assembly import export_assembly, import_step
from unlock_engine.contracts import EngineError, Manifest, POLICY
from unlock_engine.geometry import bounds, difference_volume
from unlock_engine.package import load_files, load_zip
from unlock_engine.service import import_revision


def test_valid_import_units_and_repeated_occurrences(revision):
    assert revision.ready
    ids = revision.by_id()
    assert len(ids) == 8
    assert ids["screw1"].id != ids["screw2"].id
    assert ids["screw1"].definition_id == ids["screw2"].definition_id
    assert ids["screw1"].placement.matrix[3] == -60
    assert ids["screw2"].placement.matrix[3] == 60
    b = bounds(ids["target"].shape)
    assert tuple(z - a for a, z in zip(b.min, b.max)) == pytest.approx((20, 8, 12))
    assert all(o.source_occurrence_path.startswith("/0/") for o in ids.values())


def test_stable_source_occurrence_ids(fixture_dirs):
    p = fixture_dirs["B01"] / "assembly.step"
    assert [o.id for o in import_step(p).occurrences] == [
        o.id for o in import_step(p).occurrences
    ]


@pytest.mark.parametrize(
    "field", ["connections", "tools", "regions", "staging_regions", "provenance"]
)
def test_missing_semantics_retains_geometry_with_precise_readiness(fixture_dirs, field):
    p = fixture_dirs["B02"]
    metadata = json.loads((p / "manifest.json").read_text())
    del metadata[field]
    r = import_revision(p / "assembly.step", metadata)
    assert not r.ready and len(r.assembly.occurrences) == 8
    assert r.inventory()["message"] == "Geometry imported — analysis unavailable."
    assert any(x["field"] == field for x in r.readiness)


def test_bad_reference_and_unknown_connection(fixture_dirs):
    p = fixture_dirs["B03"]
    m = json.loads((p / "manifest.json").read_text())
    m["connections"][0]["host_component_id"] = "missing"
    with pytest.raises(ValueError, match="unknown reference missing"):
        Manifest.model_validate(m)
    m["connections"][0]["kind"] = "glued"
    with pytest.raises(ValueError, match="union_tag_invalid"):
        Manifest.model_validate(m)


def test_missing_screw_axis_lists_field(fixture_dirs):
    p = fixture_dirs["B03"]
    m = json.loads((p / "manifest.json").read_text())
    del m["connections"][0]["axis_world"]
    r = import_revision(p / "assembly.step", m)
    assert not r.ready and any("axis_world" in x["field"] for x in r.readiness)


@pytest.mark.parametrize(
    "name",
    ["../evil", "/tmp/evil", "a/assembly.step", "..\\evil", "script.py", "preview.glb"],
)
def test_unsafe_archive_paths(name):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr(name, b"x")
    with pytest.raises(EngineError, match="path"):
        load_zip(stream.getvalue())


def test_zip_symlink_and_duplicate():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        i = zipfile.ZipInfo("assembly.step")
        i.create_system = 3
        i.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(i, b"/tmp/target")
    with pytest.raises(EngineError, match="nonregular"):
        load_zip(stream.getvalue())
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("manifest.json", b"{}")
        z.writestr("manifest.json", b"{}")
    with pytest.raises(EngineError, match="duplicate"):
        load_zip(stream.getvalue())


def test_valid_zip_and_expanded_budget(fixture_dirs, monkeypatch):
    p = fixture_dirs["B01"]
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(p / "assembly.step", "assembly.step")
        z.write(p / "manifest.json", "manifest.json")
    package = load_zip(data.getvalue())
    assert package.manifest["assembly_id"] == "B01"
    import unlock_engine.package as module

    monkeypatch.setattr(
        module, "POLICY", POLICY.model_copy(update={"max_expanded_bytes": 100})
    )
    with pytest.raises(EngineError, match="expanded"):
        load_zip(data.getvalue())


def test_oversize_compressed_and_corrupt_zip(monkeypatch):
    import unlock_engine.package as module

    monkeypatch.setattr(
        module, "POLICY", POLICY.model_copy(update={"max_compressed_bytes": 10})
    )
    with pytest.raises(EngineError, match="compressed"):
        load_zip(b"x" * 11)
    with pytest.raises(EngineError):
        load_zip(b"bad")


def test_corrupted_and_unsupported_step(tmp_path, fixture_dirs):
    p = tmp_path / "bad.step"
    p.write_bytes(b"not STEP")
    with pytest.raises(EngineError):
        import_step(p)
    p.write_text(
        (fixture_dirs["B01"] / "assembly.step")
        .read_text()
        .replace("AUTOMOTIVE_DESIGN", "CONFIG_CONTROL_DESIGN")
    )
    with pytest.raises(EngineError, match="AP214/AP242"):
        import_step(p)


@pytest.mark.parametrize(
    "entity",
    [
        "EXTERNAL_SOURCE",
        "DOCUMENT_FILE",
        "EXTERNALLY_DEFINED_REPRESENTATION",
        "REFERENCE;",
    ],
)
def test_external_references_rejected_before_native_parser(fixture_dirs, entity):
    from unlock_engine.package import check_step

    data = (
        (fixture_dirs["B01"] / "assembly.step")
        .read_bytes()
        .replace(b"DATA;", ("DATA;\n#999=" + entity + "();").encode())
    )
    with pytest.raises(EngineError, match="external STEP"):
        check_step(data)


def test_single_fused_solid_not_an_assembly(tmp_path):
    p = tmp_path / "one.step"
    cq.exporters.export(cq.Solid.makeBox(5, 5, 5), str(p))
    with pytest.raises(EngineError, match="5–12"):
        import_step(p)


def test_scaled_units_rejected_explicitly(tmp_path, fixture_dirs):
    p = tmp_path / "inch.step"
    p.write_bytes(
        (fixture_dirs["B01"] / "assembly.step")
        .read_bytes()
        .replace(b".MILLI.,.METRE.", b".CENTI.,.METRE.")
    )
    with pytest.raises(EngineError, match="millimetre"):
        import_step(p)


def test_nested_rotated_hierarchy_round_trip(tmp_path):
    small = cq.Solid.makeBox(2, 4, 6)
    root = cq.Assembly(name="root")
    root.add(small, name="first")
    sub = cq.Assembly(name="sub", loc=cq.Location((20, 30, 40), (0, 0, 1), 90))
    sub.add(small, name="a", loc=cq.Location((10, 0, 0)))
    sub.add(small, name="b", loc=cq.Location((20, 0, 0)))
    root.add(sub)
    root.add(small, name="fourth", loc=cq.Location((-20, 0, 0)))
    root.add(small, name="fifth", loc=cq.Location((-30, 0, 0)))
    p = tmp_path / "nested.step"
    root.export(str(p))
    original = import_step(p)
    child = next(
        o for o in original.occurrences if o.source_occurrence_path == "/0/1/0"
    )
    assert bounds(child.shape).min == pytest.approx((16, 40, 40))
    out = tmp_path / "roundtrip.step"
    export_assembly(original, out)
    after = import_step(out)
    assert [o.source_occurrence_path for o in after.occurrences] == [
        o.source_occurrence_path for o in original.occurrences
    ]
    assert [n.path for n in original.nodes] == [n.path for n in after.nodes]
    for a, b in zip(original.occurrences, after.occurrences):
        assert a.placement.matrix == pytest.approx(b.placement.matrix)
        assert difference_volume(a.shape, b.shape) < POLICY.volume_noise_mm3


def test_manifest_extra_nan_and_duplicate_ids(fixture_dirs):
    m = json.loads((fixture_dirs["B02"] / "manifest.json").read_text())
    m["units"] = "m"
    with pytest.raises(ValueError):
        Manifest.model_validate(m)
    m["units"] = "mm"
    m["unexpected"] = True
    with pytest.raises(ValueError):
        Manifest.model_validate(m)
    del m["unexpected"]
    m["components"][0]["id"] = m["components"][1]["id"]
    with pytest.raises(ValueError, match="duplicate"):
        Manifest.model_validate(m)


def test_json_duplicate_key_and_nonfinite(fixture_dirs):
    step = (fixture_dirs["B01"] / "assembly.step").read_bytes()
    for bad in (b'{"a":1,"a":2}', b'{"a":NaN}'):
        with pytest.raises(EngineError):
            load_files({"assembly.step": step, "manifest.json": bad})
