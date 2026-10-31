# Performance, measured

[← Back to the README](../README.md)

Every number here comes from committed benchmark files under `backend/evidence/live-b02/`, run on a loaded machine rather than an idle one. We publish the load average because the conditions matter.

## The cost of OCCT, and what the warm worker does about it

Native geometry operations pay an import cost. On a loaded machine (1-minute load ≈ 5), across repeated runs:

| | Cold worker | Warm standby | Δ |
|:--|--:|--:|--:|
| Full run wall time | 46.12 s / 47.00 s | 29.52 s / 29.69 s | **−36%** |
| Stage A (import + baseline) | 11.1 s / 10.2 s | 7.3 s / 7.0 s | −34% |
| Mean native tool operation | 8.73 s / 9.20 s | 5.55 s / 5.68 s | −36% |

The warm standby removes import overhead, not compute. Peak memory is unaffected: the standby takes exactly one request and exits, so only one CAD process exists at a time, and a replacement starts only after the previous one has exited.

## Where the warm worker does not help

Under the full policy benchmark, holding everything else constant:

| Simulated model turn latency | Cold | Warm | Δ |
|:--|--:|--:|--:|
| 0 s (geometry-bound) | 59.16 s | 55.25 s | −6.6% |
| 3.0 s (realistic) | 80.47 s | 60.03 s | **−25%** |

When the model is slow, geometry work overlaps with waiting for it, so the standby hides its import cost. When the model is fast, the run is geometry-bound and the standby buys almost nothing.

## The live run, end to end

<p align="center">
  <img src="../assets/readme/run-waterfall.svg" width="100%" alt="Waterfall of the 48.15 second live run by stage" />
</p>

| Stage | Time | Share |
|:--|--:|--:|
| Import | 13.26 s | 27.5% |
| Baseline search | 2.73 s | 5.7% |
| Model inference (total) | 20.05 s | 41.6% |
| Verification, comparison and the rest | 12.11 s | 25.2% |
| **Wall clock** | **48.15 s** | budget: 120 s |

The run used 40% of its wall-clock budget. Inference is the largest single share but not the majority: more than half the run is geometry and verification.

## Limits, stated as limits

| Property | Value |
|:--|:--|
| Components per assembly | 5–12 |
| Maximum envelope | 500 mm |
| Archive package | ≤ 25 MiB compressed |
| Native operation wall limit | 30 s |
| Parent run budget | 120 s |
| Peak worker RSS on B02 | ~440 MiB |
| Reported API rate limits | 3,000 req/min · 4,000,000 tok/min |

A 12-component ceiling keeps the removal search tractable, and a 500 mm envelope keeps B-rep booleans within the 30 s native limit. Widening them is ordinary engineering. The limits that are not meant to widen are the finite decision space and the one-way dispatcher, and neither is a performance trade-off.
