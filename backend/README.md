# UNLOCK engineering backend

Python/OCP CAD engine, deterministic disassembly planner, bounded Meta-powered
redesign controller and local FastAPI coordinator for the React workspace.
See [the current integration handoff](docs/META_INTEGRATION_HANDOFF.md) for setup,
configuration, tests, known scope and the explicit distinction between offline
engineering validation and pending live Meta validation.

```sh
# From the repository root; put MODEL_API_KEY in backend/.env for live redesign.
backend/.venv/bin/python -m unlock_engine.api --port 8000
# In another terminal:
cd frontend && npm run dev -- --host 127.0.0.1 --port 5183 --strictPort
```

Open http://localhost:5183/projects. B01/B02/B03 use actual synthetic STEP inputs.
The default provider is direct Meta Model API, model `muse-spark-1.3`; explicit
`AI_PROVIDER=mock` runs the real geometry pipeline with a labeled scripted policy.
Passing reports cover only their listed geometry and supported motion checks.

The deterministic disassembly planner is now implemented. See [PLANNER.md](docs/PLANNER.md)
for the bounded native interface, full removal/reverse workflow, contracts and
run commands, and [PLANNER_HANDOFF.md](docs/PLANNER_HANDOFF.md) for measured evidence.

From the repository root, run the complete real CAD planning demonstration:

```sh
backend/.venv/bin/unlock-engine plan-demo --output backend/.work/planning
```

## Run locally

Tested: Python **3.12.16**, CadQuery **2.6.1**, cadquery-ocp **7.8.1.1.post1**, Pydantic **2.12.3**, pytest **8.4.2**, macOS ARM64. All direct and transitive dependencies are pinned in `requirements.lock`.

From `backend/`:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/unlock-engine fixtures --output .work/fixtures
.venv/bin/unlock-engine demo --output .work/demo
.venv/bin/unlock-engine demo --output .work/held-out --held-out
.venv/bin/unlock-engine import --step .work/fixtures/B01/assembly.step --manifest .work/fixtures/B01/manifest.json
.venv/bin/unlock-engine schemas --output schemas
.venv/bin/unlock-engine benchmark --fixtures .work/fixtures --output .work/benchmark.json --repetitions 10
```

Import runs in an isolated native worker. Demo preparation, independent verification and export use separate workers, each with a 30 second wall limit and a 120 second parent budget. Intermediate `.stage.json` files are not completion records; only `summary.json` records a completed demo. A failed gate returns nonzero. The local coordinator queues one engineering job at a time; it is not a public multi-user scheduler.

Packages accept only flat `assembly.step` (or `.stp`), `manifest.json`, and optional `attribution.txt`. Inputs are bounded before native parsing. Only AP214/AP242 with explicit uniform millimetre units is supported. Scripts, external references, symlinks, encrypted ZIPs and arbitrary archive paths are rejected.

## Integration

| Consumer | Interface |
|---|---|
| Import coordinator | `package.load_files/load_zip`, `worker.isolated_import`, `service.import_revision` |
| Component viewer | `Revision.inventory()` and `InventoryItem.schema.json`: semantic and native IDs, structural paths, definitions, actual transforms and bounds |
| Disassembly planner | `motion.validate_translation`, `tools.evaluate_fastener` |
| Bounded Muse tools | `templates.SERVER_DOMAINS`, `service.construct_candidate`; T01/T02 only, no generated Python execution |
| AI redesign controller | `ai.controller.run_with_model`, `ai.baseline.run_selector`; eight allowlisted tools, typed `AIRunReport`. See [AI_CONTROLLER.md](docs/AI_CONTROLLER.md) |
| Independent verifier | `verification.verify_candidate`; reconstruction, actual material comparison, every mandatory constraint |
| Export coordinator | `export.export_bundle`; real STEP reimport, repeated geometry/path checks and explicit part-only fallback |
| Frontend adapter | `schemas/`: inventory, findings, translation certificates and verification reports |

Library functions use actual BReps and do not depend on HTTP or React. Native work belongs in isolated processes. `direct_path` checks one released component against every assembled obstacle and declared keep-out; it refuses targets with remaining retainers. State-based disassembly search must supply and validate released states separately.

Preview meshes use world **metres**, `scale_already_applied=true`, and stable semantic IDs. Do not apply the existing frontend's millimetre group scale again to these vertices. CAD and path engineering calculations stay in millimetres. Preview meshes never enter verification.

## Evidence

`evidence/demo/summary.json` contains real source/candidate hashes, the obstruction witness, parameters, per-constraint verification, timings and export bundle reference. The ZIP includes original/revised assembly STEP, changed-part STEP, revised manifest, parameters, differences, paths, verification, round-trip report, preview and limitations. Bytes are addressed by SHA-256. Full assembly failures produce a labeled changed-part-only bundle.

Fixture source is `fixtures.py`; generated inputs and analytic oracles are in `evidence/fixtures`. B01 has an accessible cartridge segment; B02 has a fixed bridge obstruction and an actual T01 improvement; B03 has a thin tool obstruction. Held-out B02 changes span and target dimensions. These fixtures simplify mating and workholding. They are synthetic examples, not validated products; redistribution rights remain pending author approval.

See [DECISIONS.md](docs/DECISIONS.md) for document hashes, numerical policy, interpretation and requirement mapping. See [HANDOFF.md](docs/HANDOFF.md) for executed commands and measured results.

## Deployment and scope

`Dockerfile` targets native CPU Linux. Docker/Podman was unavailable, so the image was **not built or executed**. Linux compatibility and base-image digest are not validated. Deploy using a verified immutable official Python 3.12 digest via `--build-arg PYTHON_IMAGE=python@sha256:...`, execute the suite inside it, record the digest and calibrate resource caps. Its default exact-version tag is a development convenience, not an immutable digest.

Supported limits: 5–12 rigid single-solid leaf occurrences, ≤500 mm actual assembly envelope, 25 MiB compressed / 100 MiB expanded, 30,000 faces and 200,000 preview triangles. Motion supports six world axes, isolated planar contacts and simplified annotated reusable screws. Edits support the known bridge constructor only. Conservative overlap and ambiguous mandatory evidence prevent a verified pass.

State-aware disassembly search and complete supported inverse sequencing are implemented in `planning/`. The bounded redesign controller uses direct Meta Model API through `ai/meta.py`, with a local FastAPI coordinator in `api/` and connected React workflow. Live Meta native tool calling is verified for the read-only `inspect_assembly` tool
([META_TOOL_CALLING_VERIFICATION.md](docs/META_TOOL_CALLING_VERIFICATION.md)); a live
redesign run remains unverified until the gated B02 test passes. Public authentication and deployment are not implemented. Not assessed: strength, fatigue, torque, threads, flexible parts, arbitrary contacts, free rotation, electrical safety, manufacturing feasibility or restored function.
