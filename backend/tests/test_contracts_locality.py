import json

import cadquery as cq
import pytest
from jsonschema import Draft202012Validator

from unlock_engine.cli import write_schemas
from unlock_engine.geometry import bounds, fingerprint, same_geometry
from unlock_engine.service import import_revision, construct_candidate


def test_proposal_rejects_code_unknown_fields_and_missing_evidence():
    from unlock_engine.contracts import Proposal

    proposal = dict(
        candidate_request_id="request",
        bracket_id="bridge",
        template_id="T01",
        parameters=dict(center_x_mm=0, center_y_mm=-20, width_mm=40, depth_mm=16),
        evidence_ids=["known_obstruction"],
        rationale="Bounded relief",
    )
    assert Proposal.model_validate(proposal).template_id == "T01"
    for corrupted in (
        {**proposal, "pass": True},
        {**proposal, "evidence_ids": []},
        {**proposal, "parameters": {"python_code": "run()"}},
        {**proposal, "template_id": "freeform"},
    ):
        with pytest.raises(ValueError):
            Proposal.model_validate(corrupted)


def test_manifest_boolean_strings_are_invalid(revision):
    from unlock_engine.contracts import Manifest

    metadata = revision.manifest.model_dump(mode="json")
    metadata["components"][0]["fixed"] = "false"
    with pytest.raises(ValueError):
        Manifest.model_validate(metadata)


def test_failed_demo_cannot_reuse_a_previous_pass(tmp_path, monkeypatch):
    from unlock_engine.cli import run_demo
    from unlock_engine.contracts import EngineError
    import unlock_engine.worker as module

    previous = b'{"status":"passed","candidate_id":"old"}'
    (tmp_path / "summary.json").write_bytes(previous)

    def timeout(*args, **kwargs):
        raise EngineError("GEOMETRY_FAILED", "native operation timed out")

    monkeypatch.setattr(module, "isolated_operation", timeout)
    with pytest.raises(EngineError):
        run_demo(str(tmp_path))
    assert not (tmp_path / "summary.json").exists()
    assert (
        json.loads((tmp_path / "failed_summary.json").read_text())["status"] == "failed"
    )
    assert any(
        p.read_bytes() == previous
        for p in (tmp_path / "history").glob("*/*")
        if p.is_file()
    )


def test_json_schema_matches_native_contracts(tmp_path, revision):
    write_schemas(tmp_path)
    schema = json.loads((tmp_path / "Manifest.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(revision.manifest.model_dump(mode="json"))
    inventory_schema = json.loads((tmp_path / "InventoryItem.schema.json").read_text())
    for occurrence in revision.inventory()["components"]:
        Draft202012Validator(inventory_schema).validate(occurrence)


def test_repeated_bracket_edit_is_occurrence_local(tmp_path, revision):
    from OCP.gp import gp_Trsf

    bridge = revision.by_id()["bridge"].local_shape.copy()
    # Reuse exactly the same part object, at a separate occurrence placement.
    # Both initial instances must share a real XDE part definition.
    root = cq.Assembly(name="repeated_bridge")
    for id, original in revision.by_id().items():
        t = gp_Trsf()
        t.SetValues(*original.placement.matrix[:12])
        root.add(
            bridge if id == "bridge" else original.local_shape.copy(),
            name=id,
            loc=cq.Location(t),
        )
    root.add(bridge, name="bridge_copy", loc=cq.Location((0, 150, 0)))
    path = tmp_path / "assembly.step"
    root.export(str(path))
    metadata = revision.manifest.model_dump(mode="json")
    metadata["envelope_mm"]["max"][1] = 200
    extra = dict(metadata["components"][5])
    extra.update(
        id="bridge_copy",
        source_occurrence_path="/0/8",
        display_name="repeated bridge",
        placement={"matrix": [1, 0, 0, 0, 0, 1, 0, 150, 0, 0, 1, 0, 0, 0, 0, 1]},
        bounds_mm=bounds(bridge.translate((0, 150, 0))).model_dump(mode="json"),
    )
    metadata["components"].append(extra)
    imported = import_revision(path, metadata)
    assert imported.ready
    ids = imported.by_id()
    assert ids["bridge"].definition_id == ids["bridge_copy"].definition_id
    before = fingerprint(ids["bridge_copy"].shape)
    candidate = construct_candidate(
        imported,
        "bridge",
        "T01",
        dict(center_x_mm=0, center_y_mm=-20, width_mm=40, depth_mm=16),
    )
    assert not same_geometry(candidate.shapes["bridge"], ids["bridge"].shape)
    assert same_geometry(candidate.shapes["bridge_copy"], ids["bridge_copy"].shape)
    assert fingerprint(ids["bridge_copy"].shape) == before
