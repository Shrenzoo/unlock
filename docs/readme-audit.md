# README audit

[← Back to the README](../README.md) · [Claim ledger](claims.md) · [Validation report](validation-report.md)

An audit of the README as it stood on `main` at `6604c31` (1,589 lines), carried out before the redesign. Each row was checked against the source code, the committed evidence, or by running the command. Line numbers refer to that version.

## Findings that would mislead a reader

| # | Lines | What it said | What is true | Source |
|--:|:--|:--|:--|:--|
| 1 | 13, 135 | The system "proves the redesign is safe" | It checks stated geometric constraints and supported motion. Every run report lists strength, fatigue, electrical safety, manufacturing feasibility and restored function as not assessed. | `limitations` in [`live_run.json`](../backend/evidence/live-b02/live_run.json) |
| 2 | 176–187, 244–291 | "Why nothing like this exists"; the question was "genuinely unanswerable" | The project's own PRD says disassembly planning, tool-access analysis and redesign for part access have substantial prior art, that novelty is not established, and to avoid claims of "first". | [`UNLOCK_PRD.txt`](../backend/docs/source/UNLOCK_PRD.txt), sections 1 and 2 |
| 3 | 21, 168–172, 1168, 1522 | "Track: Push the Frontier" | Push the Frontier is a **theme**. The tracks are Indie Developer and Startup. | PRD event status; public event guides |
| 4 | 23, 865, 1062–1069, 1108, 1563 | "327 tests pass" | Stale. The last recorded full run is 342 passed, 27 deselected (2026-10-31). At `6604c31`, 389 tests exist and the default selection is 357. | [`backend-tests.txt`](../backend/docs/judge-access/backend-tests.txt); `pytest --collect-only` |
| 5 | 1156, 1409 | "One live run, on B02" | There are two complete live redesign runs (B02, B05) and one live tool-calling check (B01). Line 620 of the same README records the second. | [`LIVE_B05_REDESIGN.md`](../backend/docs/LIVE_B05_REDESIGN.md) |
| 6 | 326–329, 1566 | The model's decision space is "twelve numbers" | `SERVER_DOMAINS` holds 19 values across 5 parameters: 192 T01 combinations plus 4 T02 offsets, 196 designs. | `backend/src/unlock_engine/templates.py:21` |
| 7 | 123, 196, 587, 642 | Verification is "twelve mandatory checks" | True only for a T01 cut's static stage. A T02 move has 11, because `editable_region` applies only to cuts. At plan level the live reports list 13 (B02) and 12 (B05), adding `target_path`. | `candidates[0].verification` and `revised_plan.constraint_checks` in both live reports |
| 8 | 17, 99, 921 | B02's part is a `fan_module`; "select `fan_module`" | That is the landing page's illustrative model. B02's target is `target`. The demo's first instruction would fail. | `fixtures.py`; [`scene_provenance.json`](../assets/readme/src/scene_provenance.json) |
| 9 | 927, 1096, 1127, 1575 | The offline demo "reproduces the live run's decision sequence exactly" with "identical candidates and outcomes", and this equivalence is "the proof" of independence | False. The offline policy tries T01 24×8 (rejected by replanning), then 24×12. The live run chose 40×16. No refusal occurs offline. Independence is shown by adversarial tests, not by that comparison. | `ai/demo.py`; `worker_standby_benchmark.jsonl`; `test_verifier_rejects_forged_candidate_geometry_even_with_updated_hashes` |
| 9a | 665, 1581 | Constructor and verifier have "no shared code path" | False. `verification.py` imports `construct` and `modify` from `templates.py`. The verifier rebuilds with the same trusted constructor in a fresh process. That catches a candidate that does not match its parameters, and it is independent of the model, but it would not catch a bug in the constructor itself. Other checks measure the resulting material directly. | `backend/src/unlock_engine/verification.py:37`, `:238` |
| 10 | 267, 347, 1461 | The model's final `"safe": true` was recorded and ignored | The recorded final message has no `safe` field. It has `decision`, `candidate_ids`, `summary`, `structured` and `authority`. | `final_model_message` in B02's report |
| 11 | 191 | The model "reasons that the bracket's web is the only material in the removal envelope" | Private reasoning is not stored, so this cannot be known. Only tool calls and stated rationale are on record. | [`LIVE_B02_REDESIGN.md`](../backend/docs/LIVE_B02_REDESIGN.md), Evidence |
| 12 | 99 | "a $200 part failure becomes a $2,000 replacement" | Invented. The PRD labels such figures "a rhetorical example, not a measured customer case". | PRD, section 2 |
| 13 | 1005–1009, 1155, 1333–1335 | Public deployment is "blocked"; "no public endpoint was created"; "no authentication" | Stale. The site has been public since 2026-10-30 and serves six projects. A separate authenticated judge gateway exists. | [`CLOUDFLARE_DEPLOYMENT.md`](../backend/docs/CLOUDFLARE_DEPLOYMENT.md), [`GALLERY.md`](../backend/docs/GALLERY.md), [`JUDGE_ACCESS.md`](../backend/docs/JUDGE_ACCESS.md); `GET /health` on 2026-11-01 |
| 14 | 162, 238, 616, 1160 | "safety-relevant engineering loop"; "physically real"; "certified as is" | Overstated. A pass is a design-review result on synthetic geometry, and the report says so. | `limitations` and `scope` in the live reports |

## Commands that fail or print the wrong thing

| # | Lines | Command | Result when run | Correction |
|--:|:--|:--|:--|:--|
| 15 | 1087 | `python -m unlock_engine plan-demo` | Fails: the package has no `__main__.py` | `.venv/bin/unlock-engine plan-demo` |
| 16 | 1116 | `jq … "\(.name) \(.status)"` on the smoke report | Prints `null` fifteen times: the field is `result` | Use `.result` |
| 17 | 1115 | `file live_changed_bridge.step` "shows AP214" | Prints `ASCII text` | `grep -m1 FILE_SCHEMA …` shows `AUTOMOTIVE_DESIGN`, which is AP214 |
| 18 | 1117 | `grep -c "$MODEL_API_KEY" live_run.json` shows `0` | With no key set, the empty pattern matches every line: 4,958 | Removed. The smoke report's `no_secret_in_report` check is the record |
| 19 | 1109–1119 | The check table | Rows mix `evidence/…` and `backend/evidence/…`, so no single directory runs them all | All commands now run from the repository root |
| 20 | 792 | Node "18+" | Vite 7.3.7 requires `^20.19.0 \|\| >=22.12.0` | Stated correctly |

## Stale numbers

| # | Lines | Said | Now | Source |
|--:|:--|:--|:--|:--|
| 21 | 1172 | "Four days, 56 commits" | 209 commits on `main`, from 2026-10-27 | `git rev-list --count origin/main` |
| 22 | 1212–1214 | 13,627 / 6,542 / 7,832 lines | 15,763 / 7,830 / 8,646 | `wc -l` over tracked sources |
| 23 | 1216–1220 | Evidence: 5.9 MB, four sets | 9.2 MB, nine sets | `du` over `backend/evidence` |
| 24 | 1347 | Warm worker saves 36% | That table measures a superseded first version. Under today's one-process policy the saving is 6.6% with no model latency and 25% with simulated 3 s turns. | [`LIVE_B02_REDESIGN.md`](../backend/docs/LIVE_B02_REDESIGN.md), Runtime hardening |
| 25 | 521 | `max_completion_tokens=16_000` | The run budget is 16,000, but each request caps at `min(4096, remaining)` | `backend/src/unlock_engine/ai/controller.py:563` |

## Structure

| # | Lines | Finding | Correction |
|--:|:--|:--|:--|
| 26 | 1571–1589 | "What would change our mind" sits after the footer and is missing from the contents | Moved to [objections.md](objections.md) |
| 27 | 32–89 | Contents table padded with runs of non-breaking spaces to force its width | Replaced by a short navigation line |
| 28 | whole | The live-run story, verification table and model comparison each appear three or four times | One telling each, with detail moved to [docs/](README.md) |
| 29 | whole | Five badges at the top and five at the bottom, three of them stale | No badges. Status is stated in prose, with a source |
| 30 | 18 SVGs | Diagrams repeat outdated claims: `fan_module`, "twelve", "safe" | Unused or wrong diagrams removed; Git history keeps them |

## Noted but not changed here

These sit outside a documentation pass, and each needs a decision from the maintainers.

- **GitHub repository description** still says "proves the redesign is safe with a CAD kernel before anyone cuts metal". It is a repository setting, not a file. A suggested replacement is in the pull request.
- **No software license.** The repository has no `LICENSE` file. Open pull request [#8](https://github.com/Shrenzoo/unlock/pull/8) proposes Apache-2.0, but choosing one is the authors' decision, so this pass states the current position and does not add one.
- **Fixture provenance strings.** `B01`, `B03` and the held-out B02 variant still carry "Redistribution license pending author approval". That is correct: they were not relicensed and are not published.
- **`backend/README.md`** refers to `evidence/demo/summary.json`, which is not tracked in Git. `unlock-engine demo` regenerates it. The new README does not depend on it.
