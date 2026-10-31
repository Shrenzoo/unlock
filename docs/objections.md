# Objections, and what would change our mind

[← Back to the README](../README.md)

A project that claims to verify everything should expect to be interrogated. These are the questions we asked of it, and the findings that would make us rewrite the argument rather than patch the code.

## Objections we would raise ourselves

**"Isn't this just a language model with a CAD plugin?"**
A plugin trusts the model's output. Here the model's output is a proposal, limited to one of 196 designs on a server-owned grid, and nothing downstream of the dispatcher accepts anything the model asserts. The kernel rebuilds geometry from frozen parameters and compares it with the original by two-way B-rep difference. If the model claimed success on a failing candidate, the verdict would not change. `test_all_candidates_fail_duplicate_and_budget_and_false_success_claim` covers exactly that case.

**"Why not let the model write a CadQuery script? It's more general."**
It is more general, and that's the problem. Generated code is an unbounded action space: it can build any solid, and it can also silently violate a constraint in a way nobody notices until a part is on a machine. Bounded grids trade generality for a property you can't retrofit: the model's authority can be enumerated by reading one dictionary. Every additional template widens what the kernel can build. None of them widen what the model can decide.

**"The deterministic selector found a smaller relief, faster, for free. Why pay for the model?"**
It did, and the README says so. On B02, `geometry_ranked` verified T01 24 × 12 in 24 s for $0. Muse's first proposal was that same design, and it was refused for citing the wrong kind of evidence, not for its geometry. After the refusal Muse chose a larger cut. The weaker control, `stable_enumeration`, found nothing. What B02 establishes is that a frontier model can be admitted to this loop with zero trust and still reach a verified result. It does not establish that the model beats a heuristic. That needs fixtures where the heuristic fails, which is the first item on the roadmap.

**"One run on one synthetic fixture is not evidence of much."**
Correct, which is why we call it a protocol check rather than a result, and why both deterministic controls were frozen *before* the live call rather than chosen afterwards. The claim is narrow: the loop works end to end, the guardrails fire on real input, and the verification is independent of the model.

**"Where is the model actually necessary?"**
Between evidence and action. The planner can say *that* the bracket blocks extraction and *where* the witness is. Choosing between cutting a relief in the bracket's web (T01) and shifting the web sideways (T02), sizing the cut, and reacting to a refusal are judgements over structured but open-ended evidence. The live run also shows the risk of that judgement: an unclear refusal message led the model to a larger cut than it needed. The system caught nothing wrong with the geometry, because nothing was wrong. We fixed the message.

**"Isn't `unknown` just a slower way of saying `fail`?"**
No. A `fail` says *this translation is impossible under this policy*. An `unknown` says *we could not establish whether it is possible*, and it forbids a passing aggregate. Folding `unknown` into `fail` under-reports capability, and folding it into `pass` over-reports safety (`test_missing_unknown_or_duplicate_mandatory_check_never_passes`).

**"What stops someone shipping a `pass` that means nothing?"**
Three things. Every check carries provenance, and the frontend only paints green for `live` or `computed_earlier`; an illustrative pass renders as an outline. The policy digest is bound into the evidence identity, so a pass computed under different tolerances can't be replayed against another policy. And the exported STEP is reimported and re-verified before it is called a success.

**"Does the model ever see the geometry?"**
Never. It receives compact structured evidence: coordinates, rejection certificates, finite domains and measured bounds. Not a STEP file, not a mesh. The model reasons about a *description* of the geometry, and the kernel reasons about the geometry itself. Keeping those apart is what makes `trusted_reconstruction` meaningful.

## What would change our mind

Each of these would falsify a central claim. Most already have a test; the test name is given where one exists.

**If a forged candidate passed verification.** Independent reconstruction exists so that a candidate whose geometry doesn't match its parameters fails, even if its hashes were recomputed. Covered by `test_verifier_rejects_forged_candidate_geometry_even_with_updated_hashes`.

**If a proposal could reach construction without citable evidence.** A constructed candidate whose `evidence_ids` contain no `rej_`, `plan_` or `ver_` handle from the current run would falsify the citation gate. Covered by `test_invalid_proposals_never_start_construction` and `test_live_regression_uncited_obstruction_is_refused_but_resubmittable`.

**If a mandatory `unknown` could produce a passing aggregate.** Any code path that coerces `unknown` into `pass`, or drops an unchecked mandatory constraint, invalidates every green check in the product. Covered by `test_missing_unknown_or_duplicate_mandatory_check_never_passes`.

**If the model's own success claim changed the outcome.** Covered by `test_all_candidates_fail_duplicate_and_budget_and_false_success_claim`.

**If a mutated original survived a run.** Original B-reps are deep-copied at every mutation boundary. An original shape that changed after a candidate was built would mean the baseline comparison is against a moving target. Covered by `test_original_and_other_instances_unchanged`.

**If a stale policy pass could be replayed.** Covered by `test_constraint_mutation_invalidates_prior_evidence`.

**If a deterministic selector matched or beat the model across a fixture suite.** On B02 `geometry_ranked` already matched Muse. If a broader suite showed the same everywhere, the honest conclusion would be that the model doesn't belong in this loop for template-shaped problems, and the interesting work becomes finding the task classes where it does.

Run the covered ones with the command in [Check our claims](../README.md#check-our-claims).
