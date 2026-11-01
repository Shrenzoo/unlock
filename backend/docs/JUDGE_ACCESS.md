# Judge access for the hackathon

The public B02 demonstration remains available without a code. The separate
judge gateway accepts a private access code, uploads a supported package and
starts the existing offline engineering workflow. This follows the user's
explicit authorization to add judge uploads and fresh analysis; it does not
enable public anonymous computation or live Meta inference.

The frontend is served by the existing Cloudflare Pages project `unlock-labs`.
The judge gateway is `unlock-judges`, separate from `unlock-demo`. It invokes the
private `unlock-engineering.engineering_job` function with `live=False`, never
an arbitrary function, code, model setting or shell command supplied by a client.
The gateway does not grant judges Modal account access.

## Admission and ownership

- The access code has 192 bits of generated randomness. Only its SHA-256 hash
  is stored in the Modal Secret `unlock-judge-access`; the code is not in Git,
  the static bundle, URLs or logs. Share the owner's local code file privately.
- A valid code issues a random 256-bit session token valid for two hours. Only
  its hash is stored in the durable ledger. The browser keeps it in tab-scoped
  sessionStorage and sends it in Authorization headers. It is never placed in
  query strings, browser history or artifact links. Logout revokes the session.
- Every job, status, result record and artifact read requires the owning session.
  A separate authenticated session gets 404, even if it knows the job or blob ID.
  Private previews and downloads use authenticated fetches; downloads use local
  Blob URLs. Private responses are no-store and artifacts are nosniff octet-stream.
- Origins are restricted to the exact Pages production origin. Missing/invalid
  authentication is rejected before multipart parsing or engineering dispatch.
  The actual streamed body is bounded, even without Content-Length.
- Uploads are limited to 10 MiB, three files, safe basenames and the existing
  ZIP/STEP/manifest formats. Existing import validation independently enforces
  expanded size, supported assembly structure and native geometry limits.
- There are six attempts total across the hackathon gateway, at most two per
  session. Creating a new session does not reset the global allowance. Failed
  dispatch or failed analysis consumes an attempt. Identical idempotent retries
  do not dispatch or consume another attempt; changed input under the same key
  is rejected. One analysis is admitted at a time.
- The ledger is atomically persisted and committed before dispatch. Admission,
  session changes and volume reloads are serialized inside the gateway. The
  gateway is constrained to one container. A restart preserves reservations,
  ownership, code-attempt limits and quotas. Expired queued dispatch is reported
  as interrupted, without refunding its attempt.
- Access-code attempts are globally capped at 60/hour in the durable ledger.
  The gateway also bounds request frequency in memory per active container.

Session expiry and logout remove browser access, not durable artifact bytes.
Judges should download their result before ending the session. Uploads and
results remain private on the existing Modal Volume until operator cleanup;
there is no automatic-publication route. Do not publish private judge records
or copy their snapshots into the public B02 namespace.

## Resource and operational boundaries

The private worker retains one container, no warm containers, no automatic
retry, one CPU maximum, 2–4 GiB memory, 420-second execution timeout and
180-second startup timeout. Its internal engineering workflow has a 300-second
wall budget. The gateway has one container, 0.125–0.5 CPU, 256–512 MiB memory,
a 30-second request timeout and no warm container. Both scale down after two
idle seconds. Existing storage admission reserves 256 MiB for a job and refuses
new work if the shared 1 GiB artifact budget would be exceeded.

The workspace's $30 usage limit and $0 spend limit are retained. No billing
settings, paid service, purchased domain or live inference are part of this
release. Usage/credit observations and production evidence are recorded after
verification, rather than treating an estimate as actual billed usage.

The single-writer assumption matters. Before **future gateway redeploys**, stop
new admissions and wait for active requests to drain, then stop the old gateway
before starting its replacement. Do not run a second deployment that writes
`judge-ledger.json`, and do not raise max_containers. The private worker writes
separate per-job paths, not the ledger. Never reset or delete the ledger merely
to recover a failed request or obtain more attempts. Changing allowances or
reissuing the code is an explicit operator action requiring a new budget review.

Modal documents [per-function scaling limits](https://modal.com/docs/guide/scale),
[durable function dispatch](https://modal.com/docs/guide/functions), and
[Volume consistency and single-writer constraints](https://modal.com/docs/guide/volumes).
The code deliberately keeps SQLite inside a job's local temporary filesystem;
only immutable engineering snapshots and the bounded JSON ledger use the Volume.

## Validation

The judge tests exercise real uploaded B02 STEP/manifest files through native
import, baseline planning, redesign, independent verification, export and STEP
roundtrip. Security tests separately exercise wrong/missing credentials, origins,
logout, expiry, streamed size limits, basename traversal, owner isolation,
concurrent idempotent requests, durable quotas, dispatch failures, interrupted
admission and a gateway mounted beneath a URL prefix.

Local browser acceptance uses the resulting genuine uploaded-CAD snapshot to
check desktop/mobile forms, wrong-code errors, code entry, upload/status UI,
private comparison rendering, authenticated ZIP downloads, reload and denial to
a second session. That local UI harness reuses a completed engineering record;
it is not described as a second native-compute run. Production verification must
also submit a genuine supported package to the actual Modal worker before this
feature is reported complete.

## Published verification: 2026-10-31

Live entry: <https://unlock-labs.pages.dev/projects>. Pages deployment
`2b20b62e-d550-4a36-923b-356d7649c157` serves application commit `7e01502`;
the gateway and tests are in backend commit `88cc667`. The public B02 API and
its selected licensed snapshot were not redeployed or broadened by this feature.

The complete backend suite passed **342 tests**, with 27 opt-in tests deselected
and 17 known/dependency or deliberate-invalid-package warnings, in 826.48 seconds.
Six focused security checks passed after the final boundary changes. TypeScript,
the public build, Ruff and whitespace checks passed. The public browser assertion
was updated to require the judge-code form and absence of an anonymous upload
input, rather than the previous disabled Choose files button.

A real production browser session entered the code, uploaded newly generated B02
STEP/manifest files and invoked the deployed private worker. The job completed
with `VERIFIED_IMPROVEMENT_FOUND` in **76.325 seconds**, producing **1,784,243 bytes**
of recorded artifacts. Its independently checked, reimported export hash is
`a8d839005cba947968f4b28a4ae3b3ffbb38df16aa3a2c6cd14921894255b63e`.
The browser rendered the original/revised comparison, downloaded bytes matching
that hash, reloaded the private result and confirmed that another authenticated
session could not read it. Desktop was 1440×1000; mobile code entry and ownership
denial were checked at 390×844. Neither viewport had page errors or overflow.
One actual cloud attempt was consumed; **five shared attempts remain**.

The existing public B02 production journey also passed desktop 1600×1000 and
mobile 390×844, covering actual 3D dragging, comparison layout, evidence, route
playback, ZIP member integrity, navigation/reload and refused public mutations.
All three assertion blocks completed and the runner exited normally with code 0.
All 20 served files and all 14 public B02 artifact hashes still match; the exact
build scan found no Meta credentials, Modal tokens, judge code/hash, source maps
or private engineering source. The live URL and workspace direct routes work.

The first live browser login assertion allowed only five seconds and stopped
before a response. Increasing the browser wait handled cold startup; a separate
browser check confirmed the actual wrong-code 401. A subsequent upload test
referenced fixtures removed by pytest's temporary-directory cleanup. Fixtures
were regenerated into a stable directory, and the complete real live test then
passed. No cloud job was consumed by either earlier attempt. These were test
runner issues; they are retained here rather than counted as passing runs.

After the real job, reloaded Modal UI still displayed Starter, **$30.00 credits**,
a **$30 usage limit**, a **$0 spend limit**, and $0 current usage/charges. Those
are rounded/delayed dashboard values, not a claim that the 76-second job was
free or that an exact unrounded credit balance is known. No billing changes
were made. The B02 public demonstration and old Workers-to-Pages redirect remain
available without the judge code.

Evidence: [verification summary](judge-access/verification.json),
[actual cloud job](judge-access/cloud-job.json),
[judge browser](judge-access/production-judge-browser.json),
[public browser](judge-access/production-public-browser.json),
[served assets](judge-access/production-assets.json),
[backend tests](judge-access/backend-tests.txt),
[security tests](judge-access/security-tests.txt),
[desktop](judge-access/desktop-judge-access.png),
[mobile](judge-access/mobile-judge-access.png),
[private comparison](judge-access/private-comparison.png).

## Restored on main: 2026-11-01

PR #15 was based on `feature/light-stroke-background`, which reached `main`
through PR #14 first, so this feature never reached `main`. The 2026-11-01
gallery releases rebuilt the frontend from `main` and replaced `2b20b62e`,
removing the code form; the gateway itself stayed deployed and kept refusing
unauthenticated requests. PR #23 merged it into `main`, and Pages production
deployment `0509045b` (application commit `58e7d93`, both API origins set)
serves it again. No judge attempt was used to verify the restoration: the form
was checked in the production browser test, and the gateway answered an
unauthenticated session request with 401 and the Pages origin.
