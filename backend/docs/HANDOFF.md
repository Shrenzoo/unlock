# UNLOCK geometry engineering handoff

Implemented and executed locally on October 28, 2026. Scope is the supported geometry subsystem. The full UNLOCK application and complete repair-route verification remain separate work.

## Implemented

Safe STEP/manifest packages; XDE hierarchy, occurrence identity and placements; single-solid validity; BRep collision and clearance evidence; continuous conservative six-axis translations; restricted planar contacts; shaft/handle tool volumes and screw extraction; matched bridge constructors with T01/T02; independent material/constraint checks; immutable artifacts; preview mapping; STEP export and actual reimport. Existing frontend code is unchanged.

Primary files: `src/unlock_engine/{contracts,package,assembly,geometry,motion,tools,templates,service,verification,export,artifacts,preview,worker,cli}.py`. Seven versioned JSON schemas are in `schemas/`. Numerical and interpretation decisions, requirement mapping and source-document hashes are in [DECISIONS.md](DECISIONS.md).

## Runtime and checks

- Python: `3.12.16`.
- CadQuery `2.6.1`; cadquery-ocp `7.8.1.1.post1`; Pydantic `2.12.3`; pytest `8.4.2`; Ruff `0.14.2`.
- Final pytest: **109 passed, 0 failed, 0 errors, 0 skipped**. Actual output and durations: [pytest.txt](../evidence/pytest.txt), [JUnit XML](../evidence/pytest.xml).
- Ruff format/check, dependency consistency check and existing frontend TypeScript check passed. Dependency deprecation warnings and the intentional duplicate-ZIP warning remain visible in pytest output.

Commands executed from the repository root:

```sh
backend/.venv/bin/python -m pytest backend/tests -q --junitxml=backend/evidence/pytest.xml --durations=10
backend/.venv/bin/ruff check backend/src backend/tests
backend/.venv/bin/ruff format --check backend/src backend/tests
backend/.venv/bin/python -m pip check
npm --prefix frontend run typecheck
backend/.venv/bin/unlock-engine fixtures --output backend/evidence/fixtures
backend/.venv/bin/unlock-engine demo --output backend/evidence/demo
backend/.venv/bin/unlock-engine benchmark --fixtures backend/evidence/fixtures --output backend/evidence/benchmark.json --repetitions 10
```

Tests use real OCCT geometry, including a 0.001 mm intermediate obstacle between clear endpoints, contact/inward/hidden-material cases, rotated nested hierarchy, repeated definitions and occurrence-local bracket editing, protected-hole corruption, disconnected geometry, stale parameters, unknown/missing mandatory checks, export failures, cancellation, abrupt worker termination and actual assembly reimport. Kernel mocking is not used to establish geometric correctness; injected writer failures and a killed process exercise supervision/error handling.

Initial implementation runs exposed absent OCP APIs, solid/solid tangency returning no contact face, mutation of shared topology flags, and contamination of a shared test fixture. These were corrected with installed-binding probes, explicit planar boundary checks, private copies and isolated corrupt-candidate inputs. Timeouts remained failures; they were addressed by separate bounded stages.

## Executed CAD demonstration

- Imported **8** separate occurrences from genuine synthetic AP214 STEP, including a repeated screw definition at distinct placements.
- Original target direct Z+ segment: **blocked**, with stored BRep obstruction evidence.
- T01 parameters: `{"center_x_mm": 0, "center_y_mm": -20, "depth_mm": 16, "width_mm": 40}`; actual removed material **2560.000 mm³**.
- Independent verification: **passed**, 16 individual checks. Explicit forward and reverse direct segments are included; the staging endpoint is checked.
- Original geometry unchanged: **True**.
- Export: **full_assembly**; actual reimport and independent geometry/path checks **passed**. Changed-part STEP also passed reimport.

[Actual CAD/evidence ZIP](../evidence/demo/export/177692a3f4dcd509611a07cf1cfa8c5ec2edbbf46ec520ae6bf507f2ad1a1f7c.zip) · [Machine-readable summary](../evidence/demo/summary.json)

| Identity | SHA-256 |
|---|---|
| Source STEP | `55a3f284c1b849bb9fe33bdb1ffbfd5672dbebc15101e2f01a5ee73844a031a9` |
| Manifest | `ffa268991a0fad138af494322a87e61d7a302002ef0f72f3b7a3448a44f31113` |
| Original bracket BRep | `8db90c447cc40d9a24ec838ba786d9a0871ff3a6425fa50c9f1b73f4aa8a2f7e` |
| Revised bracket BRep | `cbdfb73900634e238d1031ae877e999d0cba2459f77a2ff37641d5471bfd7748` |
| Candidate | `793e0e431aec54c8f44ce87f195f141808819ac77eaa25755dd9798807dced41` |
| Verification report | `bb43a4684c80ded0f5209e24fc2042bef5616a486ed20c28b5e084677dc48ef2` |

## Observed performance

Environment: `macOS-27.0-arm64-arm-64bit`, 10 logical CPUs. RAM capacity was not verified through the sandbox. These are local development observations on synthetic fixtures, not qualification of the PRD's reference 8-core/16-GB Linux worker.

Three fresh native processes per repetition, one per fixture. Stage timers exclude Python/CAD import startup; worker_wall_ms spans the three processes. solid_validation_ms runs after import and can reuse internally cached validity for identical BReps. OS filesystem caches remain warm after the first iteration. No controlled cold-disk benchmark. p95 nearest rank.

| Fixture / stage | n | p50 ms | p95 ms |
|---|---:|---:|---:|
| B01 / import_ms | 10 | 367.11 | 421.45 |
| B01 / solid_validation_ms | 10 | 0.53 | 0.57 |
| B01 / import_and_semantics_ms | 10 | 232.84 | 241.49 |
| B01 / collision_check_ms | 10 | 11.65 | 12.58 |
| B01 / translation_validation_ms | 10 | 47.58 | 53.05 |
| B02 / import_ms | 10 | 591.65 | 675.04 |
| B02 / solid_validation_ms | 10 | 1.29 | 1.40 |
| B02 / import_and_semantics_ms | 10 | 532.17 | 608.18 |
| B02 / collision_check_ms | 10 | 11.49 | 12.20 |
| B02 / translation_validation_ms | 10 | 248.12 | 261.77 |
| B02 / candidate_construction_ms | 10 | 763.29 | 812.57 |
| B02 / verification_ms | 10 | 3279.85 | 3402.44 |
| B03 / import_ms | 10 | 740.25 | 819.13 |
| B03 / solid_validation_ms | 10 | 1.55 | 2.04 |
| B03 / import_and_semantics_ms | 10 | 779.35 | 861.30 |
| B03 / collision_check_ms | 10 | 11.62 | 11.75 |
| B03 / translation_validation_ms | 10 | 272.08 | 281.99 |

Final demo export plus reimport and repeated constraints/path checks: **8009.88 ms**, n=1. No export p95 is claimed. Raw samples: [benchmark.json](../evidence/benchmark.json).

## Limits and next integration

Only uniformly millimetre STEP assemblies and single closed-solid leaf occurrences are supported. Contact exceptions require isolated world-axis planar material regions; complex/terminal contacts can remain unknown. Proxy overlap without decisive CAD evidence stays unknown. Exact strength, force, torque, threads, flexible parts, manufacturing, electrical safety and restored function are unverified. STEP preserves editable solids and supported assembly structure, not native feature history or mates.

No disassembly optimizer or complete state-based reverse sequence was integrated, so no full repair-route or operation-count improvement is claimed. No Muse calls, FastAPI coordinator, authentication or live frontend integration were added. No real manufactured assembly or independent human engineering review was performed. Synthetic fixture redistribution rights remain pending. Docker/Podman was unavailable: the Linux image, base digest and Linux resource caps remain unvalidated. The supplied Dockerfile is a deployment starting point, not a tested container release.

The planner should consume `validate_translation` and `evaluate_fastener` under checked semantic states. The Muse controller should consume the Proposal schema, server grids and `construct_candidate`, while the independent verifier owns pass/fail. FastAPI should own immutable job/revision state, one-job scheduling, isolated native execution and access control. The frontend adapter should consume normalized inventory, findings, certificates, reports and explicitly metre-scaled previews. All are separate integration responsibilities; the current viewer still uses its existing fixture/HTTP boundary.


## Additional AP242 check

Real AP214 → XDE → AP242 export/reimport preserved 5 occurrences; measured symmetric material differences were `[0.0, 0.0, 0.0, 0.0, 0.0]` mm³. [Actual AP242 STEP](../evidence/ap242_assembly.step), [report](../evidence/ap242_smoke.json), reproducible command: `backend/.venv/bin/python backend/scripts/check_ap242.py`.
