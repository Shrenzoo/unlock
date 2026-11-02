# The API surface

[← Back to the README](../README.md)

Interactive documentation is served at **http://127.0.0.1:8000/docs** while the backend is running. Artifacts are immutable SHA-256 identifiers rather than caller-supplied filesystem paths.

| Method | Path | Purpose |
|:--|:--|:--|
| `GET` | `/health` | Provider, model, credential state (**never the key**) |
| `GET` | `/v1/projects` | Fixture and imported projects |
| `GET` | `/v1/projects/{id}` | Project detail and revision list |
| `POST` | `/v1/projects/{id}/imports` | Upload a validated package → job |
| `GET` | `/v1/revisions/{id}` | Manifest, inventory, readiness |
| `POST` | `/v1/revisions/{id}/runs` | Start a frozen-target baseline run |
| `POST` | `/v1/runs/{id}/redesign` | Bounded model loop + independent verification |
| `GET` | `/v1/runs/{id}` | Full run record with candidates and metrics |
| `GET` | `/v1/jobs/{id}/events` | **Ordered, resumable SSE** stage stream |
| `POST` | `/v1/jobs/{id}/cancel` | Cooperative cancellation |
| `GET` | `/v1/candidates/{id}` | Candidate evidence and verification report |
| `POST` | `/v1/candidates/{id}/decision` | Append-only accept / reject |
| `POST` | `/v1/candidates/{id}/exports` | Checked STEP export bundle |
| `GET` | `/v1/artifacts/{id}` | Content-addressed download |

## Typed errors

An error envelope has this shape. The values below illustrate the format; they are not from a recorded run.

```json
{
  "error_code": "CONSTRAINT_VIOLATION",
  "message": "human-readable reason",
  "retryable": false,
  "field_errors": [],
  "evidence_ids": ["ver_…", "rej_…"],
  "run_id": "run_…"
}
```

Fifteen error codes cover the failure surface: `INVALID_PACKAGE`, `INVALID_MANIFEST`, `UNSUPPORTED_SEMANTICS`, `INVALID_SOLID`, `LIMIT_EXCEEDED`, `STALE_REVISION`, `UNSUPPORTED_TEMPLATE`, `CONSTRAINT_VIOLATION`, `GEOMETRY_FAILED`, `VERIFICATION_UNKNOWN`, `MODEL_UNAVAILABLE`, `MODEL_SCHEMA_ERROR`, `NOT_FOUND`, `FORBIDDEN` and `CANCELLED` (`frontend/src/domain/types.ts`). Evidence IDs and the run ID let you trace an error back to the computation that produced it.

## SSE that survives a disconnect

Stage events are ordered and resumable through the `Last-Event-ID` header. If the stream drops mid-run, the run continues on the server, and reconnecting resumes from the last delivered sequence number rather than restarting the analysis.

## Idempotency

Every state-changing POST accepts an `Idempotency-Key` header. Retrying a redesign request after a network blip returns the original job instead of spending another ~31,000 tokens.

## Deliberately not a platform

This is the local coordinator: one serial queue, loopback clients, trusted hosts and explicit CORS origins. It is a development tool with real concurrency limits, not a multi-user scheduler.

The public deployment serves the same read routes from a read-only snapshot, and it refuses every write. The judge gateway has its own authenticated routes. See [the security model](security-model.md) and [`JUDGE_ACCESS.md`](../backend/docs/JUDGE_ACCESS.md).
