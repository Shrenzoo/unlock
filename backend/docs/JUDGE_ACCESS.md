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
