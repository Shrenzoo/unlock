# UNLOCK technical documentation

[← Back to the README](../README.md)

## How it works

| Document | Covers |
|:--|:--|
| [The agent loop](agent-loop.md) | Eight tools, dispatcher, budgets, live decision sequences, baselines, API usage |
| [Verification](verification.md) | Every check, aggregation, independence, export, what a pass does not establish |
| [Design decisions](design-decisions.md) | Six choices and what each cost |
| [Security model](security-model.md) | Threat model, package handling, the three deployments |
| [HTTP API](api.md) | Routes, typed errors, resumable events, idempotency |
| [Performance](performance.md) | Measured timings and limits, with the load they ran under |
| [Glossary](glossary.md) | CAD and engine terms |

## Running it

| Document | Covers |
|:--|:--|
| [Five-minute walkthrough](demo-walkthrough.md) | The local offline path, screen by screen |
| [Backend README](../backend/README.md) | CLI, integration surface, supported limits |
| [Frontend README](../frontend/README.md) | Workspace, viewer, build modes |

## Checking it

| Document | Covers |
|:--|:--|
| [Claim ledger](claims.md) | Every substantive README claim, its source and how it was checked |
| [Validation report](validation-report.md) | What was executed for this documentation, and what was not |
| [README audit](readme-audit.md) | The errors found in the previous README |
| [Objections](objections.md) | Questions we would ask ourselves, and what would change our mind |
| [Build log](build-log.md) | Timeline, defects and scale |

## Engineering records

Written at the time of each milestone, and left as they were. Older records describe the system as it then stood.

| Record | Date (2026) |
|:--|:--|
| [Geometry handoff](../backend/docs/HANDOFF.md), [decisions](../backend/docs/DECISIONS.md) | Oct 27–28 |
| [Planner](../backend/docs/PLANNER.md), [planner handoff](../backend/docs/PLANNER_HANDOFF.md), [planner audit](../backend/docs/PLANNER_AUDIT.md) | Oct 28 |
| [AI controller](../backend/docs/AI_CONTROLLER.md) | Oct 28 |
| [Meta integration audit](../backend/docs/META_INTEGRATION_AUDIT.md), [handoff](../backend/docs/META_INTEGRATION_HANDOFF.md) | Oct 29 |
| [Live tool-calling verification](../backend/docs/META_TOOL_CALLING_VERIFICATION.md) | Oct 29 |
| [Live B02 redesign](../backend/docs/LIVE_B02_REDESIGN.md) | Oct 29 |
| [Browser acceptance](../backend/docs/BROWSER_ACCEPTANCE.md) | Oct 30 |
| [Deployment preflight](../backend/docs/PUBLIC_DEPLOYMENT_PREFLIGHT.md), [Modal](../backend/docs/MODAL_DEPLOYMENT.md), [Cloudflare](../backend/docs/CLOUDFLARE_DEPLOYMENT.md) | Oct 30 onward |
| [B02 provenance](../backend/docs/B02_PROVENANCE.md) | Oct 30 |
| [Judge access](../backend/docs/JUDGE_ACCESS.md) | Oct 31, Nov 1 |
| [Six-project gallery](../backend/docs/GALLERY.md) | Oct 31, Nov 1 |
| [Live B05 redesign](../backend/docs/LIVE_B05_REDESIGN.md) | Nov 1 |
| [Product requirements and sources](../backend/docs/source/UNLOCK_PRD.txt) | Oct 27 |
