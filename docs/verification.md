# Verification

[← Back to the README](../README.md)

What the verifier checks, how the checks combine, and what they do not establish. Source: `backend/src/unlock_engine/verification.py`, `motion.py`, `planning/`, `export.py`.

## The stages

A candidate passes through separate stages. A candidate can stop at any of them, and none of them consults the model.

```text
PROPOSED → CONSTRUCTED → CHECKED → VERIFIED_IMPROVEMENT
                  └───────┴──────→ REJECTED, with typed feedback
```

1. **Reconstruct.** A fresh worker process re-imports the frozen package, checks the revision hash, and rebuilds the candidate from its template and parameters. A different candidate identity stops the run.
2. **Static constraints.** `verify_candidate(static_only=True)` runs every mandatory check.
3. **Replan.** The planner searches the revised assembly for a removal route from scratch.
4. **Replay.** Every saved transition is recomputed against the frozen revision.
5. **Reverse.** Inverse translations, screw insertion and modelled tool access are rechecked, and initial connections restored.
6. **Compare.** The planner compares original and revised under the same target and frozen policy.
7. **Export.** Only on human acceptance. The STEP is written, really reimported and verified again.

## The checks

These are the labels and explanations recorded in the live reports (`engineering_evidence.verified[…].static_report.checks`).

| Check | Explanation, as recorded | B02 T01 | B05 T02 |
|:--|:--|:--|:--|
| `integrity` | Revision, geometry, policy, parameters and full constraint metadata must match recorded hashes | pass | pass |
| `solid_validity` | Every occurrence remains one valid closed positive-volume solid | pass | pass |
| `trusted_reconstruction` | Independently regenerated trusted solid compared by two-way BRep material difference | pass | pass |
| `actual_change` | Actual two-way material difference | 2,560 mm³ | 11,328 mm³ |
| `editable_region` | Actual removed material must be wholly inside engineer-declared world editable region | 0 mm³ outside | T01 only |
| `protected_interfaces` | Complete feet and post selectors include hole voids; material added into protected holes also fails | pass | pass |
| `hole_geometry` | Actual cylindrical hole surfaces and complete surrounding protected regions agree | pass | pass |
| `fixed_components` | Every unedited occurrence compared independently, including repeated shared-definition instances | pass | pass |
| `placements` | STEP world placements must match the original occurrences exactly | pass | pass |
| `design_envelope` | All revised assembled solids must remain inside declared envelope with numerical guard | pass | pass |
| `keep_outs` | Every assembled solid checked against each declared keep-out | pass | pass |
| `assembled_intersections` | All assembled occurrence pairs checked, with only independently validated planar contacts | pass | pass |
| `tool_access` | Deferred to independent state-aware plan replay and reverse validation | not applicable at the static stage | not applicable at the static stage |
| `target_path` | Plan-level check on the target's route | pass | pass |

**The count depends on the edit.** A T01 cut has 12 mandatory static checks. A T02 move has 11. At plan level, adding `target_path`, the reports list 13 and 12, and all pass. With forward replay and reverse insertion that makes 15 and 14 distinct checks. T02's `actual_change` adds removed and added material: 5,376 + 5,952 mm³.

**Why the workspace shows 25 on B05.** The candidate view (`GET /v1/candidates/{id}`) lists 11 static checks, forward replay, reverse insertion, and 12 `route:` entries, which repeat those 11 and add `target_path`. That is 25 passes covering 14 distinct checks.

## How independent is it?

The verifier is **independent of the model and of the candidate record**. It is **not a second implementation of the constructor**.

- `verification.py` imports `construct` and `modify` from `templates.py`, so reconstruction uses the same trusted constructor in a different process. A candidate whose geometry does not match its parameters fails, even with recomputed hashes (`test_verifier_rejects_forged_candidate_geometry_even_with_updated_hashes`).
- A bug in the constructor itself would not be caught by `trusted_reconstruction`. Other checks look at the result directly: `actual_change` and `editable_region` measure material, `protected_interfaces` and `hole_geometry` compare regions against the baseline, `assembled_intersections` tests every pair of parts, and the planner runs its own search over the rebuilt solids.

## Three statuses, kept apart

```python
# verification.py:66, simplified
if any(c.mandatory and c.result == "fail" for c in checks):
    return "failed"
if not set(required_ids) <= by_id.keys():
    return "unknown"
if any(by_id[id].result != "pass" for id in required_ids):
    return "unknown"
return "passed"
```

A missing mandatory check gives `unknown`, not `passed`. `test_missing_unknown_or_duplicate_mandatory_check_never_passes` covers it.

For motion, `clear`, `blocked` and `unknown` are separate. Only validated conservative coverage plus complete analytic sweep separation can admit a translation. Sampled BRep queries can reject a translation or leave it unknown, and can never admit one.

## The numerical policy

`contracts.Policy` holds tolerance (0.01 mm), required clearance (0.5 mm), noise floors and limits. The full policy is part of evidence identity, so changing a tolerance invalidates every hash derived under the old one (`test_constraint_mutation_invalidates_prior_evidence`).

## BRep, not mesh

Engineering calculations use the exact BRep in millimetres. Preview meshes are in metres, carry `authoritative: false`, and never enter verification. Tessellation can change shared topology flags, so meshing happens on a private copy (`preview.py`).

## Export

`export_bundle` refuses a candidate without a current passing report. It writes the STEP, reads it back, and verifies the reimported geometry again before reporting success. The ZIP holds original and revised assemblies, the changed part, the revised manifest, parameters, differences, paths, verification, the round-trip report, a preview and limitations. Bytes are addressed by SHA-256. A full-assembly failure gives a bundle labelled as changed-part-only.

## What a pass does not establish

Every report carries this list: structural strength and fatigue, electrical safety, manufacturing feasibility, and restored product function. Its scope line reads: "Finite rigid axis translations and annotated reusable screws; no physical repair or manufacturing certification." Also outside the model: torque, threads, cables, clips, adhesives, flexible parts, and free rotation.

A verified improvement is a design-review result, not engineering or manufacturing release approval.
