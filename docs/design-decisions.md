# Design decisions and what they cost

[← Back to the README](../README.md)

Every interesting engineering choice is a trade we accepted somewhere. These are the six that shaped UNLOCK, with what each one actually cost.

## 1. Bounded grids instead of generated code

**Decision.** The model selects values from server-owned finite domains (19 values across five parameters, 196 possible designs). It never emits code and never emits geometry.

**What it cost.** Generality, immediately and obviously. A generated CadQuery script could express relief shapes these grids cannot. Adding a template means writing a constructor, proving its geometric preconditions and adding tests, not asking the model nicely.

**Why it was worth it.** The model's total authority is legible by reading one dictionary (`SERVER_DOMAINS` in `backend/src/unlock_engine/templates.py`), and there is no code path from model output to unbounded behaviour. That property cannot be retrofitted onto generated code later, because by then the code has already run.

## 2. Independent reconstruction rather than inspecting the candidate

**Decision.** The verifier discards the geometry the constructor produced, rebuilds the bracket from the frozen parameters in its own process, and compares the two by two-way B-rep difference.

**What it cost.** Roughly double the verification work, plus a second implementation of the same parameter interpretation that must be kept in sync.

**Why it was worth it.** It is the only check that fails when the constructor and the verifier disagree about what a parameter means. Inspecting the candidate the pipeline produced would only confirm that the code did what it said it did. `test_verifier_rejects_forged_candidate_geometry_even_with_updated_hashes` covers the case where someone tampers with the candidate and recomputes its hashes.

## 3. `unknown` as a first-class result

**Decision.** `clear`, `blocked` and `unknown` are distinct and never merged, and a mandatory `unknown` forbids a passing aggregate.

**What it cost.** The system returns "we don't know" in situations where a scorecard would return a number.

**Why it was worth it.** Folding `unknown` into `fail` under-reports capability. Folding it into `pass` over-reports safety. Keeping it distinct is the only option that doesn't skew the result in either direction. Witness sampling may reject or leave a translation unknown, but it can never admit one.

## 4. Policy baked into evidence identity

**Decision.** The full `contracts.Policy` digest is part of every evidence identity, so changing a tolerance invalidates the geometry and constraint hashes derived under the old one.

**What it cost.** Debugging is more annoying. Adjusting a tolerance invalidates prior evidence, and you can't quietly compare a fresh run against stale results.

**Why it was worth it.** Stale evidence can't pass for fresh evidence. With hashes over geometry only, a pass computed under one set of assumptions could be replayed against a different policy, which is exactly the failure that makes a verification layer decorative.

## 5. Per-operation subprocess isolation

**Decision.** Every native operation runs in its own subprocess with a 30 s wall limit. Credentials are stripped from worker environments before any process starts.

**What it cost.** Process-spawn overhead on every operation, and the need for a warm standby worker just to make OCCT's import cost tolerable. Peak RSS sits around 440 MiB.

**Why it was worth it.** A hung or corrupted kernel cannot take the coordinator with it, a native crash costs exactly one operation, and credential stripping is enforced rather than aspirational.

## 6. One retry policy, owned by the controller

**Decision.** SDK retries are disabled. The controller owns bounded retries, with exactly one schema repair allowed per run.

**What it cost.** More controller code, including our own backoff.

**Why it was worth it.** With SDK retries on, a 429 would be retried invisibly below the layer that tracks budgets, and a run could silently exceed its stated cost and latency envelope. One retry policy means one place to reason about it, and a second malformed response fails the run rather than starting a negotiation with the model.
