from dataclasses import replace
import json

import cadquery as cq
import pytest

from unlock_engine.contracts import Check, EngineError, POLICY, digest
from unlock_engine.fixtures import generate_fixture
from unlock_engine.geometry import (
    boolean,
    bounds,
    box_shape,
    fingerprint,
    same_geometry,
    validate_solid,
)
from unlock_engine.service import (
    construct_candidate,
    direct_path,
    import_revision,
    shapes_hash,
)
from unlock_engine.templates import construct, modify
from unlock_engine.verification import aggregate, verify_candidate


PARAMS = dict(center_x_mm=0, center_y_mm=-20, width_mm=40, depth_mm=16)


def test_real_t01_volume_and_independent_checks(revision, candidate):
    old = revision.by_id()["bridge"].shape
    new = candidate.shapes["bridge"]
    assert old.Volume() - new.Volume() == pytest.approx(40 * 16 * 4, abs=1e-8)
    assert validate_solid(new)["valid"]
    assert direct_path(revision, "target", "Z+", 80).status == "blocked"
    assert (
        direct_path(revision, "target", "Z+", 80, candidate=candidate).status == "clear"
    )
    report = verify_candidate(revision, candidate)
    assert report.status == "passed" and all(c.result == "pass" for c in report.checks)
    assert any(
        p["axis"] == "Z-" and p["status"] == "clear" for p in report.path_certificates
    )


@pytest.mark.parametrize(
    "change",
    [
        dict(width_mm=1000),
        dict(width_mm=0),
        dict(center_x_mm=100),
        dict(center_y_mm=-24, depth_mm=20),
        dict(depth_mm=-1),
        dict(width_mm=float("nan")),
        dict(untrusted_code="pass"),
    ],
)
def test_reject_out_of_bounds_degenerate_and_protected_cuts(revision, change):
    with pytest.raises((EngineError, ValueError)):
        construct_candidate(revision, "bridge", "T01", {**PARAMS, **change})


def test_binding_cannot_expand_server_domain(revision):
    b = revision.manifest.template_bindings[0]
    templates = list(b.templates)
    templates[0] = templates[0].model_copy(
        update={"domain": {**templates[0].domain, "width_mm": (10_000.0,)}}
    )
    altered = b.model_copy(update={"templates": tuple(templates)})
    with pytest.raises(EngineError, match="server/binding"):
        modify(
            revision.by_id()["bridge"].local_shape,
            altered,
            "T01",
            {**PARAMS, "width_mm": 10_000},
        )


def test_family_match_rejects_edited_foot(revision):
    b = revision.manifest.template_bindings[0]
    original = revision.by_id()["bridge"].local_shape
    corrupted = boolean(
        "cut", original, cq.Solid.makeBox(4, 4, 4).translate((42, 5, 0))
    )
    with pytest.raises(EngineError, match="does not match"):
        modify(corrupted, b, "T01", PARAMS)


def test_t02_regenerates_links_and_preserves_feet(revision):
    c = construct_candidate(revision, "bridge", "T02", {"offset_y_mm": 24})
    assert validate_solid(c.shapes["bridge"])["valid"]
    v = verify_candidate(revision, c)
    assert v.status == "passed"
    old = construct(revision.manifest.template_bindings[0])
    for region in old.protected:
        selector = box_shape(bounds(region))
        assert same_geometry(
            boolean("common", c.shapes["bridge"], selector),
            boolean("common", revision.by_id()["bridge"].shape, selector),
        )


def test_t02_invalid_offset_and_envelope(revision):
    with pytest.raises(EngineError):
        construct_candidate(revision, "bridge", "T02", {"offset_y_mm": 1})
    c = construct_candidate(revision, "bridge", "T02", {"offset_y_mm": 36})
    r = verify_candidate(revision, c)
    assert (
        r.status == "failed"
        and next(x for x in r.checks if x.constraint_id == "design_envelope").result
        == "fail"
    )


def forged(candidate, revision, **changes):
    c = replace(candidate, **changes)
    gh = shapes_hash(c.shapes)
    id = digest(
        [
            revision.input_hash,
            c.constraint_hash,
            c.bracket_id,
            c.template_id,
            dict(c.parameters),
            gh,
            POLICY.model_dump(),
        ]
    )
    return replace(c, id=id, geometry_hash=gh)


@pytest.mark.parametrize(
    "kind", ["pad", "hole", "disconnected", "unchanged", "other_component"]
)
def test_verifier_rejects_forged_candidate_geometry_even_with_updated_hashes(
    revision, candidate, kind
):
    shapes = dict(candidate.shapes)
    if kind == "pad":
        shapes["bridge"] = boolean(
            "cut", shapes["bridge"], cq.Solid.makeBox(4, 4, 4).translate((42, 5, 0))
        )
    elif kind == "hole":
        shapes["bridge"] = boolean(
            "fuse", shapes["bridge"], cq.Solid.makeCylinder(1.7, 4, cq.Vector(48, 0, 0))
        )
    elif kind == "disconnected":
        shapes["bridge"] = cq.Compound.makeCompound(
            [shapes["bridge"].copy(), cq.Solid.makeBox(1, 1, 1).translate((200, 0, 0))]
        )
    elif kind == "unchanged":
        shapes["bridge"] = revision.by_id()["bridge"].shape
    else:
        shapes["screw2"] = shapes["screw2"].translate((1, 0, 0))
    c = forged(candidate, revision, shapes=shapes)
    r = verify_candidate(revision, c)
    assert r.status == "failed"
    if kind == "hole":
        assert (
            next(
                x for x in r.checks if x.constraint_id == "protected_interfaces"
            ).result
            == "fail"
        )


def test_stale_hash_and_corrupted_parameters_fail(revision, candidate):
    for c in (
        replace(candidate, constraint_hash="stale"),
        replace(candidate, original_revision_id="stale"),
        replace(candidate, parameters={**PARAMS, "width_mm": 46}),
        replace(candidate, geometry_hash="stale"),
    ):
        assert verify_candidate(revision, c).status == "failed"


def test_missing_unknown_or_duplicate_mandatory_check_never_passes():
    check = Check(
        constraint_id="one", label="one", result="pass", explanation="actual check"
    )
    assert aggregate([check], {"one", "missing"}) == "unknown"
    assert (
        aggregate([check.model_copy(update={"result": "unknown"})], {"one"})
        == "unknown"
    )
    assert aggregate([check, check], {"one"}) == "failed"


def test_original_and_other_instances_unchanged(revision, candidate):
    before = {k: fingerprint(o.shape) for k, o in revision.by_id().items()}
    verify_candidate(revision, candidate)
    assert before == {k: fingerprint(o.shape) for k, o in revision.by_id().items()}
    assert all(
        same_geometry(candidate.shapes[k], o.shape)
        for k, o in revision.by_id().items()
        if k != "bridge"
    )


def test_held_out_geometry_variation(tmp_path):
    p = generate_fixture(tmp_path / "held_out", "B02", held_out=True)
    r = import_revision(
        p / "assembly.step", json.loads((p / "manifest.json").read_text())
    )
    c = construct_candidate(r, "bridge", "T01", PARAMS)
    assert direct_path(r, "target", "Z+", 80).status == "blocked"
    assert verify_candidate(r, c).status == "passed"


def test_constraint_mutation_invalidates_prior_evidence(revision, candidate):
    m = revision.manifest.model_copy(
        update={
            "constraints": (
                revision.manifest.constraints[0].model_copy(
                    update={"threshold_mm": 1.5}
                ),
            )
        }
    )
    stale = replace(revision, manifest=m)
    assert verify_candidate(stale, candidate).status == "failed"


def test_keepout_cannot_be_hidden_from_path_or_candidate(revision):
    from unlock_engine.contracts import KeepOut

    m = revision.manifest.model_copy(
        update={
            "keep_outs": (
                KeepOut(
                    id="ko",
                    label="hidden cable reserve",
                    min_mm=(-5, -22, 50),
                    max_mm=(5, -18, 51),
                ),
            )
        }
    )
    changed = replace(
        revision,
        manifest=m,
        manifest_hash=digest(m),
        input_hash=digest([revision.input_hash, "new keepout"]),
    )
    c = construct_candidate(changed, "bridge", "T01", PARAMS)
    report = verify_candidate(changed, c)
    assert (
        report.status == "failed"
        and next(x for x in report.checks if x.constraint_id == "target_path").result
        == "fail"
    )
