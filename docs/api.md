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

```json
{
  "error_code": "CONSTRAINT_VIOLATION",
  "message": "editable_region: 41.2 mm³ removed outside the declared region",
  "retryable": false,
  "field_errors": [],
  "evidence_ids": ["ver_8c1a…", "rej_17a84dbaf811"],
  "run_id": "run_983d811a0f174f9a"
}
```

Fifteen error codes cover the failure surface, including `INVALID_PACKAGE`, `UNSUPPORTED_SEMANTICS`, `STALE_REVISION`, `VERIFICATION_UNKNOWN`, `MODEL_SCHEMA_ERROR` and `CANCELLED`. Every envelope carries the evidence IDs and run ID needed to trace it back to the computation that produced it.

## SSE that survives a disconnect

Stage events are ordered and **resumable**. If the stream drops mid-run, the run continues on the server, and reconnecting resumes from the last delivered sequence number rather than restarting the analysis. The client says so: *"Event stream interrupted. The run continues on the server; reconnect to resume."*

## Idempotency

Every state-changing POST accepts an `Idempotency-Key` header. Retrying a redesign request after a network blip returns the original job instead of spending another ~31,000 tokens.

## Deliberately not a platform

One serial queue, loopback clients, trusted hosts, explicit CORS origins. It is a local engineering tool with real concurrency limits, not a public multi-user scheduler. See [the security model](security-model.md) for what that does and doesn't protect against.
