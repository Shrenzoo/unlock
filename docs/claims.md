# Claim ledger

[← Back to the README](../README.md) · [Validation report](validation-report.md) · [README audit](readme-audit.md)

Every substantive claim on the README, where it comes from and how it was checked for this version. **Read** means compared by hand with the file named. **Ran** means the command was executed on 2026-11-01 and its output matched. **Live** means checked against the deployed service on 2026-11-01, read-only.

## Product and positioning

| Claim | Source | Check |
|:--|:--|:--|
| Indie Developer track, Push the Frontier theme | PRD section 1 names Indie and Startup tracks; public event guides name the Build for Your World and Push the Frontier themes; track and theme as stated by the maintainer. The organizer's own page was not reachable when checked | Read |
| Not affiliated with or endorsed by Meta | No such relationship appears anywhere in the repository | Read |
| Disassembly planning and related areas have substantial prior art; novelty not established | `backend/docs/source/UNLOCK_PRD.txt`, section 1 | Read |
| 62 million tonnes of e-waste in 2022, 22.3% documented as formally collected and recycled | Global E-waste Monitor 2024, UNITAR press release | Read |

## The agent

| Claim | Source | Check |
|:--|:--|:--|
| Eight tools; no shell, Python, URL, filesystem, accept or export tool | `TOOL_ARGS`, `ai/schemas.py:65` | Read |
| Tool definitions are generated from the validating schema | `Toolbox.specs`, `ai/toolbox.py:283` | Read |
| `tool_choice="auto"`, SDK retries off | `ai/meta.py:85`, `:119` | Read |
| 196 designs: 192 T01, 4 T02 | `SERVER_DOMAINS`, `templates.py:21`: 3×4×4×4 + 4 | Read |
| Budgets, and that setting them higher raises an error | `Budget`, `ai/toolbox.py:40` | Read |
| 4,096 output tokens per turn, reserved before each request | `ai/controller.py:501–508`, `:563` | Read |
| Dispatcher gates and failure codes | `ai/toolbox.py:298–330`, `:753–885`; `ai/schemas.py` | Read |
| Unexposed tools are never dispatched; forged or out-of-domain calls never construct | `test_invalid_proposals_never_start_construction`; offline `test_meta_tool_smoke.py` | Read: tests exist |
| The outcome is derived from records, not model messages | `derive`, `ai/controller.py:252` | Read |
| Model claiming success on failing candidates does not change the verdict | `test_all_candidates_fail_duplicate_and_budget_and_false_success_claim`, `test_ai_controller.py:197` | Read: test exists |
| Closing message stored with `authority: none…` | `ai/controller.py:399`; `final_model_message` in B02's report | Ran |
| B02 decision sequence, including the refused 24×12 | `tool_results` in `live-b02/live_run.json` | Ran |
| The refusal was a defect fixed in `fffc1e4` | `git log`; `LIVE_B02_REDESIGN.md` | Ran |
| B05's recorded rationale, quoted | `candidates[0].proposal.rationale` in `live-b05/live_run.json` | Ran |
| Seven of eight tools exercised live | Distinct `tool` values in both reports, plus the B01 check | Ran |
| `geometry_ranked` 1,152 mm³ at 24.1 s, 2 calls; `stable_enumeration` none verified at 30.3 s; Muse matched and did not beat the first | `selector_*.json`, `live_run.json` | Ran |
| The B05 offline policy picks the same −12 mm | `LIVE_B05_REDESIGN.md`; candidate `offset_y -12` from the public API | Live |

## The engine and verification

| Claim | Source | Check |
|:--|:--|:--|
| Engineering on BReps; preview meshes marked non-authoritative | `preview.py`; `verification.py` | Read |
| Analytic coverage admits a translation; sampling can only reject or leave unknown | `motion.py`; `backend/AGENTS.md` | Read |
| 0.5 mm clearance, 0.01 mm tolerance | `Policy`, `contracts.py:60` | Read |
| B05 overlap 1,397 mm³ at 12 mm | Recomputed by `export_scene.py` from the planner's witness | Ran |
| B02 overlap 640 mm³ at 13 mm, matching the record | `export_scene.py`; `AI_CONTROLLER.md` | Ran |
| Driver declared with shaft and handle solids; B07 blocked | `fixtures.py:148`; `tools.py`; gallery `validation.json` | Read |
| T02 moves the web; feet and posts stay | `templates.construct` | Read |
| 12 and 11 static checks, 13 and 12 at plan level, 15 and 14 distinct | Both live reports | Ran |
| The workspace's 25 on B05 lists static checks twice | `GET /v1/candidates/candidate_630dfe626ff6dbd31b54b01a5097edc5` | Live |
| Verifier shares the constructor (`modify`) and runs in a fresh process | `verification.py:37`, `:238`; `ai/native.py` | Read |
| A forged candidate with recomputed hashes fails | `test_verifier_rejects_forged_candidate_geometry_even_with_updated_hashes` | Read: test exists |
| Missing or unknown mandatory check prevents a pass | `aggregate`, `verification.py:66` | Read |
| Interface only paints computed passes green | `resultLabel`, `frontend/src/ui/Evidence.tsx:53` | Read |
| Export refuses without a current pass, reimports and rechecks | `export_bundle`, `export.py:30`, `:136–149` | Read |
| What is not assessed | `limitations` and `scope` in both reports | Ran |

## Results and deployment

| Claim | Source | Check |
|:--|:--|:--|
| Six outcomes as listed | `gallery-release-lighter/validation.json`; `GET /v1/projects` | Live |
| Gallery runs used the offline policy with no model inference | `/health`: provider `mock`, credentials `missing`; `validation.json`: `live_model: false` | Live |
| Outcomes pre-registered; a mismatch is refused | `fixture_catalog.py`; `GALLERY.md`; `deployment/publication.py` | Read |
| B07 first expectation was wrong, and revised | `fixture_catalog.py`; `GALLERY.md` | Read |
| B08's route is two screws then a lift | `baseline_steps` from the planner, in `scene_provenance.json` | Ran |
| Public API is read-only; anonymous POST refused | `/health` `mode: read_only`; POST returned 403 | Live |
| Public site reached and made no write requests while opening B05 | Headless Chrome capture: 0 non-GET requests | Live |
| Judge gateway: private code, 10 MiB, six attempts, no live inference | `JUDGE_ACCESS.md`; `deployment/judges.py`. The code itself was not used | Read |
| Judge upload completed in 76.3 s on the deployed worker | `backend/docs/judge-access/` | Read |
| 6 of 6 Modal jobs, 58 to 154 s | `gallery-release-lighter/validation.json`: 57.6 to 153.9 s | Ran |
| 71 of 71 artifacts hash-exact, 28 of 28 writes refused, first gallery | `gallery-release/validation.json` | Ran |
| Token usage and list-price estimates | `usage` in reports; `META_LIST_PRICES`, `ai/config.py` | Ran |
| 389 tests, 357 default | `pytest --collect-only` at `6604c31` | Ran |
| Last recorded full run: 342 passed, 27 deselected | `backend/docs/judge-access/backend-tests.txt` | Read |
| Node 20.19+ or 22.12+ | `engines` for Vite 7.3.7 in `frontend/package-lock.json` | Ran |
| Python 3.12 | `requires-python` in `backend/pyproject.toml` | Read |
| Heavy load can end a run `INCOMPLETE_ANALYSIS` | Offline B02 run during this work, load above 16 | Ran |

## Licensing

| Claim | Source | Check |
|:--|:--|:--|
| B02 and B04–B08 are CC BY 4.0, covering demonstration assets and not software | `fixture_license.py`; `B02_PROVENANCE.md`; `GALLERY.md`, Rights | Read |
| B01, B03 and held-out B02 are not covered | `fixture_license.GRANTS`; `GALLERY.md` | Read |
| No software license file | No `LICENSE` at the repository root on `main`; `gh repo view` reports none | Ran |

## Visuals

| Claim | Source | Check |
|:--|:--|:--|
| Geometry is the engine's, and redesigned brackets match the record | `export_scene.py` exits on a hash mismatch; `7aebefb8…` and `c9b46d5a…` matched | Ran |
| Captions match evidence | `compose.py` asserts them before drawing | Ran |
| Ledger values read from reports | `diagrams.py` | Ran |
