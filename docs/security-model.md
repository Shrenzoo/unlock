# Security model

[← Back to the README](../README.md)

The first threat is not a hostile user. It is **a language model that can produce plausible, confident, wrong output while driving a system that constructs geometry.** The model's output is treated as untrusted input. The public deployment adds a second threat, ordinary internet traffic, covered at the end.

## What the model can reach

Eight tools. One, `construct_candidate`, asks for new geometry, and only by choosing values from a finite server-owned grid. It builds a candidate and never changes the original revision. The other seven inspect, verify or compare. There is no shell tool, filesystem tool, URL tool, Python tool, acceptance tool or release tool. A tool that is not on the list returns a typed `TOOL_NOT_ALLOWED` and is never dispatched, so the capability set can be enumerated by reading one dictionary.

Every call is validated before it runs: extra properties, invalid or stale IDs, unsupported templates and out-of-domain values are rejected, and a foreign project ID or stale revision returns `STALE_EVIDENCE`. A proposal must cite a `rej_`, `plan_` or `ver_` handle issued by the current run, or construction never starts.

## How imported geometry is treated

A package is untrusted input. `load_zip` enforces a strict **filename allowlist of exactly three entries**: `assembly.step` (or `.stp`), `manifest.json` and an optional `attribution.txt`. Anything else raises `unsafe or unsupported ZIP path`. That is what rejects scripts, external references and archive-path tricks: not by detecting malice, but by refusing everything that isn't on the list.

On top of that it rejects **encrypted** archives, **non-regular members** (the symlink check, via `stat.S_ISLNK`), unsupported compression methods and duplicate entries. Extraction is bounded twice, at 25 MiB compressed and 100 MiB expanded, and the expanded size is re-checked against the bytes actually read, so a lying header can't overflow the budget.

Artifacts are addressed by SHA-256 rather than caller-supplied paths, so nothing can be smuggled in through a filename. Imported component names are returned to the model only as untrusted data (`test_injected_component_name_is_returned_only_as_untrusted_data`).

## How the geometry process is contained

Every native operation runs in its **own subprocess** with a 30 s wall limit and a 120 s parent budget. Operations and work directories are allowlisted *before* a process is spawned, not discovered after. **Credentials are stripped from the worker environment before any process starts**, and the live tool-calling smoke test scans its report, stdout and stderr for the key and asserts it is absent.

A hung or corrupt OCCT call can't take the coordinator down, and a native crash costs exactly one operation.

## How state is kept honest

Revisions are immutable, and frozen constraints, keep-outs and envelope are hashed into a revision's identity. Every evidence identity includes the full policy digest, so changing a tolerance invalidates everything derived under the old one. No candidate from a cancelled, active or superseded run can be accepted or exported, and export re-checks acceptance both before native work and again at commit.

## The three deployments

| | Local coordinator | Public `unlock-demo` | Private `unlock-judges` |
|:--|:--|:--|:--|
| Reachable from | Loopback only | Anyone, exact CORS origins | Anyone with the private code, exact Pages origin |
| Writes | Yes | None: anonymous POST returns 403 | Bounded uploads, six attempts in total |
| Engineering compute | Yes | None: serves a validated snapshot from a read-only Volume | `unlock-engineering.engineering_job` with `live=False` |
| Meta inference | When configured | No: mock provider, no credentials | No |
| Auth | None | None needed | 192-bit code, 256-bit session tokens, stored only as hashes |

The publication guard (`deployment/publication.py`) refuses to serve a gallery unless every project has one recorded offline run, a recorded license grant and its pre-registered outcome, and verified exports pass their member-hash and licensing checks.

## What we are not claiming

The **local coordinator** is a single-queue development tool with no authentication and no project ownership. Do not expose it to the public internet. The containment above is subprocess isolation, not a security sandbox. No third-party penetration test has been done.

Details: [`JUDGE_ACCESS.md`](../backend/docs/JUDGE_ACCESS.md), [`MODAL_DEPLOYMENT.md`](../backend/docs/MODAL_DEPLOYMENT.md), [`CLOUDFLARE_DEPLOYMENT.md`](../backend/docs/CLOUDFLARE_DEPLOYMENT.md). The earlier [deployment preflight](../backend/docs/PUBLIC_DEPLOYMENT_PREFLIGHT.md), which blocked publication until rights were settled, is kept as a record.
