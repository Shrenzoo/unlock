# Disassembly planner compatibility audit

Read before implementation: the supplied planning request, all three project
documents in `docs/source/` (extracted from the original DOCX documents during
the geometry phase), and PRD sections 7, 10, 11, 13, 14, 16, 17, 20 and 21.
The original documents and their hashes are recorded in DECISIONS.md.

Baseline, before changing source: `backend/.venv/bin/python -m pytest backend/tests
-q --junitxml=backend/evidence/planner_baseline.xml`: **109 passed, 0 failed,
0 skipped, 16 warnings, 80.29 seconds**. Existing uncommitted files preserved.
Development branch: `codex/disassembly-planner`.

Reusable interfaces: `service.import_revision`, `Revision.by_id`,
`motion.validate_translation`, `service.contacts_for`, `tools.evaluate_fastener`,
`geometry.fingerprint/bounds`, `service.construct_candidate`,
`verification.verify_candidate`, `artifacts.ArtifactStore` and atomic writes.
The engine uses real XDE occurrence placements and OCCT BReps. Meshes are display
data. No alternate collision representation or model inference is needed.

Gaps identified before proceeding:

- `direct_path` assumes every part is assembled and refuses retained components.
  Add a state adapter using the same validator, with removed occurrences omitted.
- Only individual direct paths exist; add immutable states, UCS, independent replay,
  reverse restoration, metrics and comparison contracts.
- Separating planar start contacts exist; closing terminal contacts need a narrowly
  scoped inverse half-space proof, including all other material pairs.
- Candidate verification currently checks tools/paths against the fully assembled
  state. Add an explicitly labeled static-only verification scope for planning;
  tool/path checks must then be supplied by replay and reverse validation.
- Canonical B03 retains its cover, not its target. Do not change that original
  fixture's meaning or assume that its target requires the obstructed screw.
  Demonstrate a second selected replaceable cover through new manifest metadata.
- Original fixtures include unannotated loose screw occurrences. Those occurrences
  remain obstacles and cannot execute REMOVE_FASTENER; they do not automatically
  invalidate an otherwise supported target problem.
- Unknown connection kinds currently fail the entire manifest readiness gate,
  a conservative restriction stronger than failure only within target closure.
  Preserve and disclose this restriction rather than ignoring a relation.
- Staging is a region, not a set of authored final action steps. Define one frozen
  deterministic axis endpoint per region/axis, with explicit path constraints
  taking precedence. This defines the finite supported operation graph.
- No HTTP/job coordinator exists. Provide a bounded native CLI/service adapter;
  keep the frontend unchanged.
