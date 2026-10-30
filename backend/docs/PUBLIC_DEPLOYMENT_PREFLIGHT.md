# Public read-only deployment preflight

Reviewed 2026-10-30 at approximately 23:38 UTC on `codex/modal-deployment`,
starting from `aa7f295280d4b16627a0ddcc31c8b88023ae4f2d` (PR #7).

**Disposition: blocked. No public Modal endpoint or Vercel deployment was
created. PR #7 remains open and unmerged.** The account holder authorized
publication only after rights, billing protection, security and Hobby eligibility
pass. Publication permission and Hobby eligibility could not be established.

## Fixture origin and rights

B02 is generated deterministically by
`src/unlock_engine/fixtures.py:generate_fixture`, using CadQuery primitives and
the repository's bridge constructor in `templates.py`. It is an eight-occurrence
synthetic assembly, with simplified mating and assumed workholding. The source
does not import an external appliance CAD model. Git history traces this fixture
to `c18342f` (2026-10-29, commit author Shreyas Pabbathi). A commit author is not
by itself an agreed redistribution license or confirmation of all rightsholders.

Both the source at `fixtures.py:198` and the **actual selected cloud snapshot**
state:

> Redistribution license pending author approval; local engineering fixture

The snapshot identifies its source as
`unlock_engine.fixtures.generate_fixture(B02, held_out=False); deterministic seed 0`.
The source requirements at `docs/source/UNLOCK_PRD.txt:675` propose releasing
fixture code under a permissive code license and geometry under an explicit
license such as CC BY 4.0 **once the authors agree**. They expressly prohibit
describing that proposed license as already granted. No root or fixture license
grant was found in the tracked repository.

**Required before publication:** rightsholder confirmation of ownership and
permission to publicly display and redistribute B02, its original and revised
geometry, and the associated downloadable engineering evidence. Record the
agreed license, attribution and covered assets. Then update source provenance
and regenerate and verify the public bundle so the immutable export accurately
contains the granted terms. Do not simply relabel the existing hashed evidence.

## Billing protection and observed usage

The Modal dashboard was reloaded during this review. Workspace
`shreyas-pabbathi` remains on **Starter**, with a **$30 usage limit set by the
account holder** and **$0 spend limit**. It displays **$30.00 credits** and
**$0.00 total spend** for Oct 1–31, 2026. These displayed balances are rounded;
an exact remaining-credit ledger was not exposed by the reviewed interfaces.
No billing setting, payment method or subscription was changed.

Authenticated read-only CLI queries returned:

| Resource | Reported cost before adjustments |
| --- | ---: |
| Smoke app CPU | $0.00208921 |
| Smoke app memory | $0.00038853 |
| Separate persistence-check app CPU | $0.00000982 |
| Separate persistence-check app memory | $0.00000222 |
| Smoke app network egress | $0.00005184 |

The monthly summary reports `ephemeral_apps: 0.00248979`,
`network_egress: 0.00005184`, `llm_tokens: 0`, `volumes: 0`, and **billed_cost: 0**.
The egress allowance adjustment is `-0.00005184`. The summary's top-level
`metered_cost` is `0.00005184`; it does not sum to the listed ephemeral-app
breakdown. Preserve the raw values instead of using this discrepancy to infer an
exact remaining credit balance. The detailed compute rows sum to $0.00248978,
one hundred-millionth of a dollar below the summary's rounded aggregate.

Commands: `modal billing summary --for 2026-10 --json` and
`modal billing report --start 2026-10-30 --end 2026-10-31 --resolution h --show-resources --json`.
The report was queried during the current hour and billing data may arrive late.
These figures cover existing smoke and persistence tests, not a public deployment.
The prior $0.00157 body estimate is not the actual total resource report.

The observed engineering workflow lasted **71.443 seconds** and recorded
**1,791,109 artifact bytes**. The Volume contains only the selected B02 job.
Both ephemeral apps are stopped and `modal container list --json` returned `[]`.
No new cloud workload was started for this review. Vercel usage from this task
is zero because no project or deployment was created.

Modal's [budget documentation](https://modal.com/docs/guide/budgets) distinguishes
usage caps from net out-of-pocket spend limits. The dashboard warns that Volume
storage can continue after workloads stop. This small Volume is below the
[current 1 TiB free storage allowance](https://modal.com/pricing); the application
also bounds its own retained artifacts to 1 GiB. The $0 cap must not be described
as a universal promise covering unlimited storage or unrelated services.

## Security and exposure review

No blocking security finding was identified in the reviewed local read-only
deployment path. This is a local review of the actual cloud-generated snapshot,
not a production endpoint attestation.

- The public function mounts only `/selected-job-id` from the Volume, read-only.
  It attaches no Modal Secret. Its image includes backend `src/` and pinned
  dependencies, not `.env`, the Modal credential configuration, development
  evidence directories, SQLite, or the user's engineering workspace.
- The selected snapshot contains exactly one project, revision and run, two
  candidates, four completed jobs and one automated acceptance record. All are
  from synthetic B02 with `live_model=false`. Every artifact in that subdirectory
  is potentially public through its hash, including full downloadable evidence.
- Read-only middleware rejects mutations before request-body parsing. The
  gateway does not import the CAD engine, native worker, coordinator or model
  provider. No upload, AI request, redesign or export computation can be started
  through its public routes.
- Local ASGI checks denied **42 requests** across seven write routes using POST,
  PUT, PATCH, DELETE, TRACE and CONNECT. **15 read routes** succeeded. All **14
  artifact responses** matched their SHA-256 IDs and ETags and used `nosniff`.
- Unknown projects/artifacts, traversal-shaped artifact IDs, `.env`, Modal
  configuration, source paths and raw snapshot/status paths returned 404.
  An unapproved origin returned 403, an unapproved host 400, and an oversized
  declared body 413. Approved-origin reads and preflights succeeded.
- The real limiter admitted 120 requests and returned 429 with `Retry-After: 60`
  on the next request. It is global per container and resets on cold restart;
  it is not authentication or a durable monthly traffic quota. The existing
  max-container, scale-to-zero, timeout and workspace billing limits remain
  necessary outer bounds.
- A fresh production frontend build used an HTTPS placeholder API origin and
  non-public credential canaries. A local scan compared known credentials,
  canaries and common token/private-key signatures against tracked files,
  image source, snapshot files, API responses, built assets and ZIP members:
  **388 scanned payloads, zero findings**. Credential values were never logged.
  The static output contains no source maps, CAD inputs, Python source, database
  or credential files. `frontend/public` contains only `favicon.svg`.
- Frontend configuration exposes only the intended API URL/mode. API public
  provider metadata omits the credential value. CORS is an origin restriction,
  not authentication: anyone can read this intentionally public B02 data.

The review used the existing completed cloud snapshot locally. It did not run
new CAD or model work, submit uploads, or make requests to a production service.
The safe result summary is in `evidence/modal/public-preflight.json`.

## Vercel Hobby eligibility

The proposed static Vite frontend fits the hosting architecture and needs no
paid Vercel Functions, domain, storage or add-on. A local production build passed.
That establishes technical compatibility, not commercial-use eligibility.

Vercel's [Hobby plan documentation](https://vercel.com/docs/plans/hobby),
[terms](https://vercel.com/legal/terms#hobby-plan), and
[fair-use guidelines](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage)
restrict Hobby to personal/noncommercial use. The fair-use definition includes
deployments intended for financial gain and advertising the sale of a product or
service. Lack of a checkout is insufficient to prove eligibility. The guidelines
direct uncertain cases to Vercel Support.

UNLOCK is being prepared as a hackathon project with potential future commercial
use. No project-specific eligibility confirmation or official hackathon-prize
exception was found. **Hobby eligibility remains unconfirmed**, rather than a
finding that all hackathon demos are prohibited. Clarify that this deployment's
purpose meets the published personal/noncommercial restriction, or obtain
Vercel clarification for this specific use. Do not upgrade to Pro to bypass this
checkpoint without separate authorization.

## Deployment and browser testing

There is **no live URL** from this task. Production checks of the 3D viewer,
comparison, engineering evidence, ZIP integrity, mobile layouts and navigation
were not run because the publication gates did not pass. Earlier local browser
results remain documented in `MODAL_DEPLOYMENT.md`; they must not be reported as
production validation. Public CAD uploads, live AI and public engineering compute
remain disabled. PR #7 must remain unmerged.
