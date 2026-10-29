import json
import threading

import cadquery as cq
import pytest
from jsonschema import Draft202012Validator

from unlock_engine.assembly import import_step
from unlock_engine.contracts import EngineError, Screw
from unlock_engine.geometry import boolean, collision, fingerprint
from unlock_engine.planning import (
    PlanResult,
    SearchPolicy,
    State,
    compare_plans,
    plan_problem,
    plan_revision,
)
from unlock_engine.planning.actions import ActionValidator
from unlock_engine.planning.contracts import Action
from unlock_engine.planning.fixtures import sequence_fixture
from unlock_engine.planning.problem import Problem
from unlock_engine.planning.replay import replay_plan, validate_reverse
from unlock_engine.planning.runner import isolated_plan, plan_files, save_result
from unlock_engine.planning.state import connections, metrics
from unlock_engine.service import construct_candidate, import_revision
from unlock_engine.package import load_files


@pytest.fixture(scope="module")
def sequence(tmp_path_factory):
    p = sequence_fixture(
        tmp_path_factory.mktemp("sequence"), tools=("driver_a", "driver_b")
    )
    return p, import_revision(
        p / "assembly.step", json.loads((p / "manifest.json").read_text())
    )


@pytest.fixture(scope="module")
def planned_sequence(sequence):
    problem = Problem(sequence[1], "target")
    result = plan_problem(problem)
    assert result.status == "feasible", result.model_dump_json()
    return problem, result


def modify_manifest(path, fn):
    m = json.loads((path / "manifest.json").read_text())
    fn(m)
    return import_revision(path / "assembly.step", m)


def real_problem(tmp_path, target, obstacle, *, policy=SearchPolicy()):
    parts = [("target", target), ("obstacle", obstacle)]
    parts.extend(
        (f"fixed{i}", cq.Solid.makeBox(2, 2, 2).translate((80, i * 10, 0)))
        for i in range(3)
    )
    assy = cq.Assembly(name="adversarial_planner")
    for k, s in parts:
        assy.add(s, name=k)
    path = tmp_path / "real.step"
    assy.export(str(path))
    imported = import_step(path)
    components = []
    for (k, _), o in zip(parts, imported.occurrences):
        components.append(
            dict(
                id=k,
                display_name=k,
                source_occurrence_path=o.source_occurrence_path,
                role="service_module" if k == "target" else "chassis",
                fixed=k != "target",
                replaceable=k == "target",
                removal_axes=["Z+"] if k == "target" else [],
                staging_region_id="above" if k == "target" else None,
            )
        )
    m = dict(
        schema_version="1.0",
        project_id="synthetic_adversarial",
        assembly_id="adversarial",
        units="mm",
        frame=dict(handedness="right", up="Z"),
        envelope_mm=dict(min=[-50, -50, -20], max=[100, 100, 100]),
        components=components,
        connections=[],
        tools=[],
        constraints=[],
        keep_outs=[],
        template_bindings=[],
        regions=[],
        staging_regions=[
            dict(id="above", bounds_mm=dict(min=[-100, -100, 120], max=[150, 150, 200]))
        ],
        unsupported_assumptions=[],
        provenance=dict(
            author="test constructor",
            license="local testing only",
            source="real_problem; synthetic",
        ),
    )
    return Problem(import_revision(path, m), "target", policy)


@pytest.mark.parametrize(
    "code,expected",
    [("B01", "feasible"), ("B02", "no_path_supported"), ("B03", "no_path_supported")],
)
def test_canonical_real_cad_plans(fixture_dirs, code, expected):
    p = fixture_dirs[code]
    revision = import_revision(
        p / "assembly.step", json.loads((p / "manifest.json").read_text())
    )
    result = plan_revision(revision, "target")
    assert (
        result.status == expected
        and result.complete
        and result.unresolved_transition_count == 0
    )
    if code == "B01":
        assert result.metrics.cost == (0, 0, 0, 1) and result.replacement_verified
        assert [s.component_id for s in result.steps] == ["target"]
    else:
        assert any(
            r.category == "CONFIRMED_GEOMETRIC_OBSTRUCTION" for r in result.rejections
        )
        assert not result.steps and result.metrics is None
    if code == "B03":
        assert any(
            r.category == "TOOL_ACCESS_BLOCKED" and r.action.component_id == "screw1"
            for r in result.rejections
        )


def test_real_sequence_found_replayed_restored_and_counted(planned_sequence):
    p, r = planned_sequence
    assert [s.component_id for s in r.steps] == ["cover", "screw1", "screw2", "target"]
    assert r.metrics.cost == (1, 2, 1, 4) and r.metrics.unique_tools == 2
    assert r.replay.status == r.reverse.status == "passed" and r.replacement_verified
    assert (
        r.reverse.geometric_insertion
        == r.reverse.fastener_reinsertion
        == r.reverse.tool_access
        == r.reverse.connection_restoration
        == "passed"
    )
    assert r.reverse.final_removed_ids == ()
    assert r.steps[-1].prerequisite_ids == ("screw1", "screw2")
    assert dict(connections(p.manifest, State())) == {
        "retainer1": "engaged",
        "retainer2": "engaged",
    }
    assert dict(connections(p.manifest, State(frozenset({"screw1"})))) == {
        "retainer1": "released",
        "retainer2": "engaged",
    }
    assert r.steps[0].axis == "X+"  # Two real geometric routes; stable tie chooses X+.
    assert p.components["screw1"].display_name == p.components["screw2"].display_name
    assert r.steps[1].component_id != r.steps[2].component_id


@pytest.mark.parametrize(
    "part,kind,axis",
    [
        ("base", "TRANSLATE_PART", "Z+"),
        ("target", "TRANSLATE_PART", "Z+"),
        ("target", "TRANSLATE_PART", "X+"),
        ("screw1", "TRANSLATE_PART", "Z+"),
    ],
)
def test_semantics_before_any_geometry(sequence, part, kind, axis):
    p = Problem(sequence[1], "target")
    validator = ActionValidator(p)
    result = validator.evaluate(
        State(), Action(kind=kind, component_id=part, axis=axis, distance_mm=80)
    )
    assert (
        result.status == "rejected"
        and validator.geometry_calls == validator.misses == 0
    )
    assert result.rejection.geometry_evidence_level == "semantic"


def test_tool_access_reevaluated_after_cover_removal_and_cache_is_exact(sequence):
    p = Problem(sequence[1], "target")
    v = ActionValidator(p)
    a = next(a for a in p.actions(State()) if a.component_id == "screw1")
    blocked = v.evaluate(State(), a)
    assert (
        blocked.status == "rejected"
        and blocked.rejection.category == "TOOL_ACCESS_BLOCKED"
    )
    clear = v.evaluate(State(frozenset({"cover"})), a)
    assert clear.status == "clear" and len(clear.certificate.paths) == 2
    assert v.evaluate(State(frozenset({"cover"})), a) == clear and v.hits == 1
    assert v.evaluate(State(frozenset({"cover", "screw1"})), a).status == "rejected"
    assert blocked.certificate.before_state_hash != clear.certificate.before_state_hash


def test_one_screw_releases_only_explicit_multiple_relations(sequence):
    path, _ = sequence
    revision = modify_manifest(
        path,
        lambda m: m["connections"][0].update(
            retained_component_ids=["cover", "target"]
        ),
    )
    p = Problem(revision, "target")
    state = State(frozenset({"screw1"}))
    a = next(a for a in p.actions(state) if a.component_id == "target")
    reason = p.semantic_reason(state, a)
    assert reason and "screw2" in reason[0] and "screw1" not in reason[0]
    cover = next(a for a in p.actions(state) if a.component_id == "cover")
    assert p.semantic_reason(state, cover) is None


def test_invalid_engagement_never_runs_tool_geometry(sequence):
    path, _ = sequence
    revision = modify_manifest(path, lambda m: m["regions"][0].update(kind="contact"))
    p = Problem(revision, "target")
    v = ActionValidator(p)
    a = next(a for a in p.actions(State()) if a.component_id == "screw1")
    r = v.evaluate(State(frozenset({"cover"})), a)
    assert (
        r.status == "rejected"
        and "engagement" in r.rejection.reason
        and v.geometry_calls == 0
    )


def test_thin_hidden_plate_retains_actual_brep_witness(tmp_path):
    target = cq.Solid.makeBox(2, 2, 2)
    plate = cq.Solid.makeBox(2, 2, 0.001).translate((0, 0, 50.123))
    p = real_problem(tmp_path, target, plate)
    action = next(a for a in p.actions(State()) if a.component_id == "target")
    assert collision(target, plate).status == "clear"
    assert (
        collision(target.translate((0, 0, action.distance_mm)), plate).status == "clear"
    )
    result = plan_problem(p)
    assert result.status == "no_path_supported"
    rejection = next(r for r in result.rejections if r.action.component_id == "target")
    certificate = next(
        c for c in result.certificates if c.id in rejection.witness_certificate_ids
    )
    witness = next(
        f
        for path in certificate.paths
        for f in path.findings
        if f.kind == "positive_volume_intersection"
    )
    assert (
        witness.component_ids == ("target", "obstacle")
        and witness.intersection_volume_mm3 > 0
    )
    assert 0 < witness.witness_travel_mm < action.distance_mm
    assert (
        "obstacle" in rejection.remaining_obstacle_ids
        and rejection.revision_id == p.revision_id
    )
    assert rejection.state_hash == State().identity(p.input_hash)


def test_real_proxy_uncertainty_cannot_admit_transition(tmp_path):
    elbow = boolean("fuse", cq.Solid.makeBox(10, 1, 10), cq.Solid.makeBox(1, 10, 10))
    p = real_problem(tmp_path, cq.Solid.makeBox(1, 1, 1).translate((6, 6, 2)), elbow)
    r = plan_problem(p)
    assert (
        r.status == "incomplete"
        and not r.complete
        and not r.steps
        and r.unresolved_transition_count == 1
    )
    rejection = next(rj for rj in r.rejections if rj.category == "UNKNOWN_GEOMETRY")
    assert rejection.geometry_evidence_level == "unresolved"
    assert all(
        f.kind != "positive_volume_intersection"
        for c in r.certificates
        for path in c.paths
        for f in path.findings
    )


@pytest.mark.parametrize(
    "corruption",
    [
        "distance",
        "transform",
        "state",
        "prerequisite",
        "missing_certificate",
        "certificate",
        "ordering",
        "duplicate",
    ],
)
def test_independent_replay_rejects_corrupted_plan(planned_sequence, corruption):
    p, r = planned_sequence
    steps = list(r.steps)
    certs = list(r.certificates)
    if corruption == "distance":
        steps[0] = steps[0].model_copy(update={"distance_mm": 20})
    elif corruption == "transform":
        steps[0] = steps[0].model_copy(
            update={"end_transform": steps[0].start_transform}
        )
    elif corruption == "state":
        steps[0] = steps[0].model_copy(update={"after_state_hash": "wrong"})
    elif corruption == "prerequisite":
        steps[-1] = steps[-1].model_copy(update={"prerequisite_ids": ()})
    elif corruption == "missing_certificate":
        certs = []
    elif corruption == "certificate":
        used = steps[0].certificate_ids[0]
        certs = [
            c.model_copy(update={"geometry_hash": "stale"}) if c.id == used else c
            for c in certs
        ]
    elif corruption == "ordering":
        steps[0], steps[1] = steps[1], steps[0]
    else:
        steps.insert(2, steps[1])
    assert replay_plan(p, steps, certs).status == "failed"


def test_reverse_checks_actual_target_obstruction_and_tool_blockage(sequence):
    p = Problem(sequence[1], "target")
    v = ActionValidator(p)
    # Both screws released, but cover restored too early: real target insertion is blocked.
    state = State(frozenset({"screw1", "screw2"}))
    target = next(a for a in p.actions(state) if a.component_id == "target")
    result = v.evaluate(state, target, insertion=True)
    assert (
        result.status == "rejected" and result.certificate.paths[0].status == "blocked"
    )
    screw = next(a for a in p.actions(State()) if a.component_id == "screw1")
    result = v.evaluate(State(), screw, insertion=True)
    assert (
        result.status == "rejected"
        and result.rejection.category == "TOOL_ACCESS_BLOCKED"
    )
    assert result.certificate.subchecks == ("tool_access", "fastener_reinsertion")
    assert result.certificate.paths[1].status == "blocked"


def test_reverse_rejects_wrong_order_and_stale_geometry(planned_sequence):
    p, r = planned_sequence
    steps = list(r.steps)
    steps[0], steps[1] = steps[1], steps[0]
    assert validate_reverse(p, steps).status == "failed"
    other = Problem(p.revision, "target", SearchPolicy(clearance_mm=0.6))
    assert validate_reverse(other, r.steps).status == "failed"
    assert replay_plan(other, r.steps, r.certificates).status == "failed"


def test_planar_contact_removal_and_terminal_insertion(tmp_path):
    path = sequence_fixture(tmp_path, seats=True)
    p = Problem(
        import_revision(
            path / "assembly.step", json.loads((path / "manifest.json").read_text())
        ),
        "target",
    )
    result = plan_problem(p)
    assert result.replacement_verified and result.reverse.status == "passed"
    assert (
        result.metrics.has_contact_exemptions
        and result.metrics.noncontact_clearance_lower_bound_mm is None
    )
    target = next(
        c for c in result.reverse.certificates if c.action.component_id == "target"
    )
    assert (
        target.paths[0].contact_exemptions == ("target_seat",)
        and target.paths[0].axis == "Z-"
    )


def test_terminal_contact_exemption_does_not_hide_roof(tmp_path):
    from test_geometry_motion import contact_setup
    from unlock_engine.motion import validate_translation

    moving, base, contact = contact_setup()
    base = boolean("fuse", base, cq.Solid.makeBox(1, 6, 8).translate((3, -2, 2)))
    base = boolean("fuse", base, cq.Solid.makeBox(6, 6, 1).translate((-2, -2, 9)))
    r = validate_translation(
        "m",
        moving.translate((0, 0, 12)),
        {"base": base},
        "Z-",
        12,
        terminal_contacts={"base": contact},
    )
    assert r.status == "blocked" and any(
        f.kind == "positive_volume_intersection" for f in r.findings
    )


@pytest.mark.parametrize("target", ["missing", "base", "screw1", "cover"])
def test_invalid_target_contract(sequence, target):
    r = plan_revision(sequence[1], target)
    assert r.status == "invalid_input" and r.error and not r.steps


def test_unsupported_semantics_and_missing_tools_are_invalid_input(sequence):
    path, _ = sequence
    for mutate in (
        lambda m: m["connections"][0].update(kind="welded"),
        lambda m: m.update(tools=[]),
        lambda m: m["components"][1].update(staging_region_id="missing"),
    ):
        revision = modify_manifest(path, mutate)
        result = plan_revision(revision, "target")
        assert result.status == "invalid_input" and not revision.ready


def test_geometry_tool_constraint_and_policy_changes_invalidate_cache(
    sequence, revision, candidate
):
    cache = {}
    original = Problem(revision, "target")
    modified = Problem(revision, "target", candidate=candidate)
    for problem in (
        original,
        modified,
        Problem(
            revision, "target", SearchPolicy(clearance_mm=0.6), candidate=candidate
        ),
    ):
        validator = ActionValidator(problem, cache)
        action = next(a for a in problem.actions(State()) if a.component_id == "target")
        validator.evaluate(State(), action)
        assert validator.hits == 0 and validator.misses == 1
    path, _ = sequence
    a = Problem(sequence[1], "target")
    b = Problem(
        modify_manifest(path, lambda m: m["tools"][0].update(handle_radius_mm=4)),
        "target",
    )
    assert a.tool_hash != b.tool_hash and a.input_hash != b.input_hash
    c = Problem(
        modify_manifest(path, lambda m: m["constraints"][0].update(threshold_mm=0.6)),
        "target",
    )
    assert (
        a.constraint_hash != c.constraint_hash
        and a.comparison_hash != c.comparison_hash
    )


@pytest.mark.parametrize(
    "template,params",
    [
        ("T01", dict(center_x_mm=0, center_y_mm=-20, width_mm=40, depth_mm=16)),
        ("T02", dict(offset_y_mm=24)),
    ],
)
def test_replan_trusted_candidates_and_compare_without_percentage(
    revision, template, params
):
    candidate = construct_candidate(revision, "bridge", template, params)
    original = plan_revision(revision, "target")
    revised = plan_revision(revision, "target", candidate=candidate)
    assert original.status == "no_path_supported" and revised.replacement_verified
    comparison = compare_plans(original, revised)
    assert comparison["verified_improvement"] and comparison["original_metrics"] is None
    assert "%" not in json.dumps(comparison) and "percent" not in json.dumps(comparison)
    changed = plan_revision(
        revision, "target", SearchPolicy(clearance_mm=0.6), candidate=candidate
    )
    with pytest.raises(EngineError):
        compare_plans(original, changed)


def test_invalid_and_non_improving_candidates_do_not_claim_improvement(
    revision, candidate
):
    invalid = candidate.__class__(**{**candidate.__dict__, "geometry_hash": "tampered"})
    assert (
        plan_revision(revision, "target", candidate=invalid).status == "invalid_input"
    )
    blocked = construct_candidate(
        revision,
        "bridge",
        "T01",
        dict(center_x_mm=0, center_y_mm=0, width_mm=24, depth_mm=8),
    )
    original = plan_revision(revision, "target")
    revised = plan_revision(revision, "target", candidate=blocked)
    assert (
        revised.status == "no_path_supported"
        and not compare_plans(original, revised)["verified_improvement"]
    )


def test_real_limits_and_native_cancellation(sequence):
    path, revision = sequence
    limited = plan_revision(revision, "target", SearchPolicy(max_expanded_states=1))
    assert (
        limited.status == "incomplete"
        and limited.stats.termination == "state_limit"
        and limited.expanded_states == 1
    )
    timed = plan_revision(revision, "target", SearchPolicy(max_seconds=0.000001))
    assert timed.status == "incomplete" and timed.stats.termination == "time_limit"
    event = threading.Event()
    event.set()
    package = load_files(
        {
            name: (path / name).read_bytes()
            for name in ("assembly.step", "manifest.json")
        }
    )
    assert isolated_plan(package, "target", cancel_event=event).status == "cancelled"


def test_native_service_schema_and_current_result_persistence(sequence, tmp_path):
    path, _ = sequence
    r = plan_files(path / "assembly.step", path / "manifest.json", "target")
    assert r.replacement_verified
    Draft202012Validator(PlanResult.model_json_schema()).validate(
        r.model_dump(mode="json")
    )
    assert PlanResult.model_validate_json(r.model_dump_json()) == r
    save_result(r, tmp_path)
    stale = plan_files(
        path / "assembly.step",
        path / "manifest.json",
        "target",
        expected_revision_id="stale",
    )
    assert (
        stale.status == "invalid_input"
        and stale.error["error_code"] == "STALE_REVISION"
    )
    save_result(stale, tmp_path)
    assert (
        json.loads((tmp_path / "result.json").read_text())["status"] == "invalid_input"
    )
    assert (
        json.loads((tmp_path / "latest.json").read_text())["status"] == "invalid_input"
    )


def test_actual_metrics_and_originals_remain_immutable(planned_sequence):
    p, r = planned_sequence
    before = {k: fingerprint(s) for k, s in p.shapes.items()}
    repeated = plan_problem(p)
    assert (
        repeated.id == r.id
        and repeated.steps == r.steps
        and repeated.metrics == r.metrics
    )
    assert before == {k: fingerprint(s) for k, s in p.shapes.items()}
    assert metrics(r.steps, r.replay.certificates, "target") == r.metrics
    with pytest.raises(ValueError):
        metrics((r.steps[0], r.steps[0]), r.replay.certificates, "target")


def test_independent_exhaustive_oracle_on_actual_cad_assembly(planned_sequence):
    p, result = planned_sequence
    validator = ActionValidator(p)
    solutions = []

    def enumerate_sequences(removed, last_tool, sequence):
        if "target" in removed:
            tools = [a.tool_id for a in sequence if a.tool_id]
            cost = (
                len(
                    {
                        a.component_id
                        for a in sequence
                        if a.kind == "TRANSLATE_PART" and a.component_id != "target"
                    }
                ),
                len({a.component_id for a in sequence if a.kind == "REMOVE_FASTENER"}),
                sum(a != b for a, b in zip(tools, tools[1:])),
                len(sequence),
            )
            solutions.append((cost, sequence))
            return
        # Independently enumerate manifest operations; do not call Problem.actions,
        # production add_cost, advance, best-state bookkeeping, or any heap.
        for k, c in sorted(p.components.items()):
            if c.fixed or k in removed:
                continue
            retainers = {
                s.fastener_id
                for s in p.manifest.connections
                if isinstance(s, Screw)
                and k in (*s.retained_component_ids, s.host_component_id)
            }
            if retainers - removed:
                continue
            if c.role == "fastener":
                s = p.screws[k]
                actions = [
                    Action(
                        kind="REMOVE_FASTENER",
                        component_id=k,
                        axis=p.tools[s.tool_id].permitted_axis,
                        distance_mm=s.extraction_distance_mm,
                        tool_id=s.tool_id,
                    )
                ]
            else:
                actions = [
                    Action(
                        kind="TRANSLATE_PART",
                        component_id=k,
                        axis=ax,
                        distance_mm=p.distance(k, ax),
                    )
                    for ax in c.removal_axes
                    if p.distance(k, ax) is not None
                ]
            for action in actions:
                if (
                    validator.evaluate(
                        State(frozenset(removed), last_tool), action
                    ).status
                    == "clear"
                ):
                    enumerate_sequences(
                        removed | {k}, action.tool_id or last_tool, sequence + (action,)
                    )

    enumerate_sequences(set(), None, ())
    assert len(solutions) == 4  # Both cover axes, both screw orderings, real geometry.
    assert min(x[0] for x in solutions) == result.metrics.cost
    assert all(
        [a.component_id for a in seq][0] == "cover" and seq[-1].component_id == "target"
        for _, seq in solutions
    )


def test_cached_unknown_remains_unknown_and_cannot_become_clear(tmp_path):
    elbow = boolean("fuse", cq.Solid.makeBox(10, 1, 10), cq.Solid.makeBox(1, 10, 10))
    p = real_problem(tmp_path, cq.Solid.makeBox(1, 1, 1).translate((6, 6, 2)), elbow)
    v = ActionValidator(p)
    a = next(a for a in p.actions(State()) if a.component_id == "target")
    assert v.evaluate(State(), a).status == v.evaluate(State(), a).status == "unknown"
    assert v.hits == 1 and v.misses == 1


def test_begin_run_labels_history_and_removes_stale_current_success(
    planned_sequence, tmp_path
):
    from unlock_engine.planning.runner import begin_run, retrieve_result

    _, result = planned_sequence
    artifact = save_result(result, tmp_path)
    begin_run(tmp_path)
    assert not (tmp_path / "result.json").exists()
    assert json.loads((tmp_path / "latest.json").read_text()) == dict(
        status="running", completed=False
    )
    historical = retrieve_result(tmp_path, artifact)
    assert historical.provenance == "retrieved" and historical.id == result.id


def test_invalid_file_input_returns_typed_result(tmp_path):
    r = plan_files(tmp_path / "missing.step", tmp_path / "missing.json", "target")
    assert r.status == "invalid_input" and r.error["error_code"] == "INVALID_PACKAGE"


def test_native_crash_returns_incomplete_not_no_path(sequence, monkeypatch):
    import subprocess
    import sys
    import unlock_engine.worker as worker

    real_popen = subprocess.Popen

    def crash(*args, **kwargs):
        return real_popen([sys.executable, "-c", "import os; os._exit(9)"], **kwargs)

    monkeypatch.setattr(worker.subprocess, "Popen", crash)
    path, _ = sequence
    r = plan_files(path / "assembly.step", path / "manifest.json", "target")
    assert r.status == "incomplete" and not r.complete and not r.steps
    assert r.error["error_code"] == "GEOMETRY_FAILED" and "exit 9" in r.error["message"]


def test_parent_enforces_phase_deadline_even_when_child_does_not_cooperate(
    tmp_path, monkeypatch
):
    import subprocess
    import sys
    import time
    import unlock_engine.worker as worker

    real_popen = subprocess.Popen
    children = []

    def hang(*args, **kwargs):
        process = real_popen(
            [sys.executable, "-c", "import time; time.sleep(5)"], **kwargs
        )
        children.append(process)
        return process

    monkeypatch.setattr(worker.subprocess, "Popen", hang)
    (tmp_path / "phase.json").write_text(
        json.dumps(dict(name="search", started=time.monotonic()))
    )
    with pytest.raises(EngineError, match="deadline"):
        worker._run_worker(tmp_path, "plan", 2, None, phase_limits={"search": 0.01})
    assert children[0].poll() is not None


def test_feasible_baseline_improvement_uses_actual_route_counts(fixture_dirs):
    path = fixture_dirs["B02"]

    def release_bridge(m):
        bridge = next(c for c in m["components"] if c["id"] == "bridge")
        bridge.update(fixed=False, removal_axes=["Z+"], staging_region_id="above")

    revision = modify_manifest(path, release_bridge)
    candidate = construct_candidate(
        revision,
        "bridge",
        "T01",
        dict(center_x_mm=0, center_y_mm=-20, width_mm=40, depth_mm=16),
    )
    original = plan_revision(revision, "target")
    revised = plan_revision(revision, "target", candidate=candidate)
    assert original.status == "feasible" and original.metrics.cost == (1, 0, 0, 2)
    assert [s.component_id for s in original.steps] == ["bridge", "target"]
    assert original.reverse.status == "passed"
    assert revised.metrics.cost == (0, 0, 0, 1)
    assert compare_plans(original, revised)["verified_improvement"]


def test_metrics_and_certificate_tampering_cannot_drive_comparison(planned_sequence):
    _, r = planned_sequence
    bad = r.model_copy(
        update={"metrics": r.metrics.model_copy(update={"cost": (0, 0, 0, 0)})}
    )
    with pytest.raises(EngineError, match="identity"):
        compare_plans(r, bad)


def test_kernel_exception_remains_unknown_without_success(sequence, monkeypatch):
    import unlock_engine.planning.actions as actions

    def fail(*args, **kwargs):
        raise EngineError("GEOMETRY_FAILED", "injected native failure")

    monkeypatch.setattr(actions, "validate_translation", fail)
    p = Problem(sequence[1], "target")
    r = plan_problem(p)
    assert r.status == "incomplete" and not r.steps
    assert any(
        "injected native failure" in rejection.reason for rejection in r.rejections
    )
    assert r.stats.geometry_validation_calls > 0


def test_error_contract_rejects_unknown_fields_and_codes():
    from unlock_engine.planning.contracts import ErrorEnvelope

    data = EngineError("INVALID_MANIFEST", "missing data").envelope()
    assert ErrorEnvelope.model_validate(data).error_code == "INVALID_MANIFEST"
    with pytest.raises(ValueError):
        ErrorEnvelope.model_validate({**data, "model_says_safe": True})
    with pytest.raises(ValueError):
        ErrorEnvelope.model_validate({**data, "error_code": "SAFE_ANYWAY"})


def test_planning_context_cannot_mutate_tools_stages_or_policy(sequence):
    p = Problem(sequence[1], "target")
    with pytest.raises(TypeError):
        p.tools["driver_a"] = p.tools["driver_b"]
    with pytest.raises(TypeError):
        p.stages["above"] = p.stages["side"]
    with pytest.raises(AttributeError):
        p.policy = SearchPolicy(clearance_mm=0.6)
    p.check_integrity()


def test_mismatched_declared_template_family_is_invalid_input(fixture_dirs):
    revision = modify_manifest(
        fixture_dirs["B02"],
        lambda m: m["template_bindings"][0]["parameters"].update(web_depth_mm=60),
    )
    r = plan_revision(revision, "target")
    assert r.status == "invalid_input" and "binding differs" in r.error.message
