# Performance, measured

[← Back to the README](../README.md)

Every number here comes from committed benchmark files under `backend/evidence/live-b02/`, run on a loaded machine rather than an idle one. The load average is given because the conditions matter: a single developer laptop, offline scripted provider unless stated. These are not general benchmarks.

## The cost of OCCT, and what the warm worker does about it

Each native operation cold-starts Python and imports OCP, CadQuery and VTK, which takes 4–6 s under load. A warm, single-use standby worker takes that off the critical path.

The first version kept a replacement warming during the operation, and on a machine with a 1-minute load of 5–6 it measured as follows (`worker_standby_benchmark.jsonl`). **This version was replaced**, because two CAD processes could exist at once:

| | Cold worker | Warm standby | Δ |
|:--|--:|--:|--:|
| Full run wall time | 46.12 s / 47.00 s | 29.52 s / 29.69 s | **−36%** |
| Stage A (import + baseline) | 11.1 s / 10.2 s | 7.3 s / 7.0 s | −34% |
| Mean native tool operation | 8.73 s / 9.20 s | 5.55 s / 5.68 s | −36% |

## What the current policy gives

Today at most one pooled CAD process exists, and a replacement starts only after the previous operation has exited, so peak memory equals the cold path. The saving now comes only from overlap with the model's think time (`worker_policy_benchmark.jsonl`, load ≈ 10–12):

| Simulated model turn latency | Cold | Warm | Δ |
|:--|--:|--:|--:|
| 0 s (geometry-bound) | 59.16 s | 55.25 s | −6.6% |
| 3.0 s (realistic) | 80.47 s | 60.03 s | **−25%** |

When the model is slow, geometry work overlaps with waiting for it, so the standby hides its import cost. When the model is fast, the run is geometry-bound and the standby buys almost nothing.

## Budgets are wall-clock, so load matters

The 120 s run budget and 30 s native limits are real deadlines. On 2026-11-01, during this documentation pass, the offline B02 demo was run while a GPU render held the machine's load average above 16. It ended `INCOMPLETE_ANALYSIS` with `GEOMETRY_FAILED: native operation timed out`. That is the correct behaviour: the run reported that it could not finish rather than reporting a result. A quiet machine completes the same run. See the [validation report](validation-report.md).

Modal's single CPU is the tighter budget, about 1.7× slower than the development Mac in a private profile, which is why the gallery geometry was thinned ([`GALLERY.md`](../backend/docs/GALLERY.md)).

## The B02 live run, end to end

| Stage | Time | Share |
|:--|--:|--:|
| Import | 13.26 s | 27.5% |
| Baseline search | 2.73 s | 5.7% |
| Model inference (total) | 20.05 s | 41.6% |
| Verification, comparison and the rest | 12.11 s | 25.2% |
| **Wall clock** | **48.15 s** | budget: 120 s |

The run used 40% of its wall-clock budget. Inference is the largest single share but not the majority.

The B05 live run took 73.3 s: 16.8 s of model latency and 37.0 s of geometry.

## Limits, stated as limits

| Property | Value |
|:--|:--|
| Components per assembly | 5–12 |
| Maximum envelope | 500 mm |
| Archive package | ≤ 25 MiB compressed, 100 MiB expanded (10 MiB through the judge gateway) |
| Faces / preview triangles | ≤ 30,000 / ≤ 200,000 |
| Native operation wall limit | 30 s |
| Parent run budget | 120 s |
| Peak worker RSS on B02 | ~440 MiB |
| Reported API rate limits | 3,000 req/min · 4,000,000 tok/min |

These limits bound the search and keep B-rep booleans inside the native time limit. They have not been characterised beyond these fixtures.
