# Build log

[← Back to the README](../README.md)

UNLOCK was built for the Meta Global AI Developer Hackathon 2026 (26 October to 4 November), Indie Developer track, Push the Frontier theme. Dates below come from commit history and the release records, not memory. No history has been rewritten.

## Timeline

| Date (2026) | What landed | Record |
|:--|:--|:--|
| Oct 27 | Workspace frontend: landing, projects list, engineering workspace | `git log` |
| Oct 28 | Planner and bounded AI controller on the geometry engine, offline | [`AI_CONTROLLER.md`](../backend/docs/AI_CONTROLLER.md) |
| Oct 29 | Direct Meta Model API, native tool calling, first live checks | [`META_TOOL_CALLING_VERIFICATION.md`](../backend/docs/META_TOOL_CALLING_VERIFICATION.md) |
| Oct 29 (UTC Oct 30) | First live redesign, B02: `VERIFIED_IMPROVEMENT_FOUND` in 48.1 s | [`LIVE_B02_REDESIGN.md`](../backend/docs/LIVE_B02_REDESIGN.md) |
| Oct 30 | Browser acceptance suite; public read-only launch on Cloudflare and Modal, one project | [`BROWSER_ACCEPTANCE.md`](../backend/docs/BROWSER_ACCEPTANCE.md), [`CLOUDFLARE_DEPLOYMENT.md`](../backend/docs/CLOUDFLARE_DEPLOYMENT.md) |
| Oct 31 | Judge access with private uploads, verified on the deployed worker | [`JUDGE_ACCESS.md`](../backend/docs/JUDGE_ACCESS.md) |
| Nov 1 | Six-project gallery released; detail cut after a failed Modal run; second live redesign, B05 | [`GALLERY.md`](../backend/docs/GALLERY.md), [`LIVE_B05_REDESIGN.md`](../backend/docs/LIVE_B05_REDESIGN.md) |

## Defects worth reading

**The citation refusal.** On B02, Muse's first proposal cited only `ev_` handles and was refused before construction. The refusal did not say construction had not started or that the same parameters could be resubmitted, and the prompt said never to repeat a proposal. Muse changed the design rather than the citation. Commit `fffc1e4` fixed the prompt, the tool description and the message, and added a regression test that fails on the old code. On B05 the citation was right first time, though one run does not show the fix caused that.

**Gallery expectations.** Each gallery fixture's outcome was written down before its run, and the job runner refuses to record a mismatch. It refused several times. B05's first offset timed out during a parallel build. B07's expectation was wrong about the turn budget and was revised to the outcome the engine recorded. B08's first layout gave `unknown` because a conservative tool box overlapped the target. The first detailed geometry passed locally and failed on Modal's single CPU. All of it is recorded in [`GALLERY.md`](../backend/docs/GALLERY.md#corrections-made-on-the-way-recorded-rather-than-hidden).

**Judge access lost and restored.** PR #15 merged into a stale base, so later frontend builds from `main` dropped the judge form. PR #23 restored it. [`JUDGE_ACCESS.md`](../backend/docs/JUDGE_ACCESS.md#restored-on-main-2026-11-01).

## Scale at `6604c31`

| | |
|:--|--:|
| Commits on `main` | 209 |
| `backend/src`, Python | 15,763 lines |
| `backend/tests`, Python | 7,830 lines |
| `frontend/src`, TypeScript and CSS | 8,646 lines |
| Tests collected / default selection | 389 / 357 |
| `backend/evidence` | 9.2 MB, nine sets |
