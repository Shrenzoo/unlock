# Modal deployment checkpoint

This branch prepares a public read-only engineering demonstration and private
Modal engineering jobs. Public deployment still requires the account holder's
approval. The existing local interactive application remains available.

## Account safeguards

Verified after saving and reloading on October 30, 2026:

- Workspace: `shreyas-pabbathi`, Starter plan.
- Billing cycle: October 1–31, 2026.
- Available compute credits: $30.00; usage and charges: $0.00.
- Workspace usage limit: $30, set by the user.
- Workspace spend limit: $0.

The dashboard warns that volume storage charges can still accrue after workloads
stop. Modal currently includes 1 TiB of Volume storage and 1 TiB of monthly egress
on Starter. This integration must keep its own storage far below that allowance;
other workspace resources also count. Recheck the entire workspace before any
cloud run and at billing-cycle rollover. No payment details are recorded here.

## Architecture decision

The current FastAPI coordinator has a local SQLite WAL database, a serial Python
queue and bounded native subprocesses. Background threads alone are unsuitable
for a scale-to-zero web container: they are not durable Modal inputs. Sharing a
writable SQLite WAL file across Volume mounts is also unsafe.

Use a private CPU Function with one container and one input at a time. Each job
owns a local temporary SQLite database, runs the existing coordinator and saves
immutable engineering artifacts plus JSON record/event snapshots to a dedicated
directory on a Volume. A second, read-only ASGI Function serves only a separately
selected B02 demonstration snapshot. It never opens a writable SQLite database,
accepts uploads or invokes the model. Private jobs require Modal workspace SDK
authentication and never become public merely because their ID is known.

Submit private jobs with `.spawn()`, keep the returned FunctionCall ID, and poll
with `.get(timeout=0)` or inspect durable progress. CAD processing never depends
on a browser request remaining connected. The HTTP API retains existing GET
routes, resumable SSE evidence and hash-checked artifact downloads. All public
mutations are rejected before request-body processing.

The default decision policy is explicitly `mock`. Geometry construction,
independent verification and exports are real; the decision policy is scripted.
Live Meta execution requires a separate explicit operator opt-in and a Modal
Secret containing `MODEL_API_KEY`. The Meta adapter and geometry code are reused.

## Current official references

Reviewed October 30, 2026:

- https://modal.com/docs/guide/budgets
- https://modal.com/pricing
- https://modal.com/docs/guide/volumes
- https://modal.com/docs/guide/webhooks
- https://modal.com/docs/guide/webhook-timeouts
- https://modal.com/docs/guide/resources
- https://modal.com/docs/guide/scale
- https://modal.com/docs/guide/trigger-deployed-functions

Volumes do not provide distributed file locking; concurrent changes to one file
can lose data. ASGI requests time out at 150 seconds. CPU/memory are billed at
the higher of requests and actual consumption, including cold starts and idle
scaledown windows. Cost estimates must include those periods and image builds.
