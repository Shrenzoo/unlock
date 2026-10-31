# Security model

[← Back to the README](../README.md)

The threat model is not "a hostile user". It is **a language model that produces plausible nonsense with full confidence, running in a process that can modify real geometry.** Everything below follows from taking that seriously.

<p align="center">
  <img src="../assets/readme/defense-in-depth.svg" width="100%" alt="Six gates between a model token and physical geometry" />
</p>

## What the model can reach

Eight tools. Seven are read-only inspection. One, `construct_candidate`, can affect geometry, and only by choosing values from a finite server-owned grid. There is no shell tool, filesystem tool, URL tool, Python tool, acceptance tool or release tool. A tool that is not on the list returns a typed `TOOL_NOT_ALLOWED` and is never dispatched, so the capability set can be enumerated by reading one dictionary.

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

## What we are explicitly not claiming

This is a **local, single-queue engineering tool**, not a hardened multi-tenant service. The coordinator binds to loopback with trusted hosts and explicit CORS origins. There is no authentication, no project ownership, no per-user rate limiting and no sandboxing beyond the subprocess boundaries described above. **Do not expose it to the public internet in its current form.**

Read-only cloud scaffolding exists (`unlock_engine/deployment/`, `modal_app.py`, `modal_web.py`, a Vercel config for the frontend). A preflight review on 30 October 2026 decided not to publish it yet, on fixture-licensing and billing grounds rather than a security defect, and no public endpoint was created. See [the deployment preflight](../backend/docs/PUBLIC_DEPLOYMENT_PREFLIGHT.md).
