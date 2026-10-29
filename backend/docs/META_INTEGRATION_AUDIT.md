# Meta integration audit — October 29, 2026

The source documents were read from the three supplied DOCX files, with their
engineering sections compared against the existing text extracts in docs/source.
The later explicit integration request supersedes PRD §15's original Fireworks /
Muse Spark Open provider choice. Engineering constraints, independent checks,
limits and fail-closed outcomes remain authoritative.

The existing backend was untracked at the start. Commit c18342f preserves it as
an explicit pre-integration snapshot; it does not claim this code was newly
written for the Meta migration. Existing root README changes, skill directories
and prior evidence are preserved separately.

Initial validation of that untouched snapshot:

- Backend under the restricted sandbox: 210 passed, 10 failed solely because
  local HTTP stub sockets could not bind (`PermissionError`, socketserver.py).
- Same snapshot extracted to /private/tmp and tested with loopback permitted:
  **220 passed, 16 warnings, 175.56 seconds**. No preexisting code failure observed.
- Frontend: TypeScript and Vite build passed; emitted bundle sizes are recorded
  in the baseline frontend log.

Initial architecture: real immutable CAD engine, deterministic planner, separate
reconstruction/verifier and eight tools; stdlib Fireworks adapter; no FastAPI
coordinator; React defaults to prepared illustrative data and fixture geometry.
No Meta key or live-test flag was configured at inspection.

Independent read-only review identified retry token accounting, cancellation,
full evidence retention, actual viewport geometry/occurrence IDs, tool-call ID
validation, usage validation, stale target races, live provenance and unsupported
forced smoke tool selection. These findings drive the integration regressions.

Official protocol references checked on October 29, 2026:

- https://dev.meta.ai/docs/overview
- https://dev.meta.ai/docs/tool-calling
- https://dev.meta.ai/docs/reasoning

Chat Completions is retained for compatibility with the existing controller.
Tools use nested function definitions, tool_choice=auto and complete correlated
assistant/tool history. Medium is the default reasoning effort. No raw CAD files
or private reasoning are sent to/stored as model context. Current account pricing
is not asserted; cost remains unavailable until a sourced tariff is configured.

Final review resolution:

- Output caps reserve every retry; inconsistent/negative usage is refused.
- Meta HTTP has an absolute deadline and cancellation; SDK retries are disabled.
- Full plans/certificates/geometry and evidence-handle mappings survive workers.
- Native subprocesses do not inherit credential environment variables.
- Cancellation, active jobs, superseded selections and withdrawn acceptance block
  review/export promotion, with acceptance rechecked at export commit.
- Rejected/unknown tool stages retain their failure state; candidate metrics and
  rendered geometry use the same selected record.
- Witnesses use actual finding IDs and their removed-component context.
- Late target/project/review responses are guarded by identity/generation.
- Malformed smoke arguments and unsupported identifiers return explicit errors.

The first broader regression run caught a missing handle-index persistence field
(1 failure, 266 passes). The field was added and the frozen full suite rerun:
**267 passed, 2 paid tests deselected, 17 warnings, 243.86 seconds**. No test was
weakened to hide the failure. Browser acceptance used the explicit offline model
policy with real engineering services; live Meta remains unverified.
