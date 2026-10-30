# Meta Muse Spark 1.3 native tool calling — verification

Executed October 29, 2026 on `feature/meta-tool-calling-verification`.
**Result: PASSED.** One live, two-request cycle through the direct Meta Model
API. Muse Spark 1.3 requested UNLOCK's real read-only `inspect_assembly` tool.
The backend validated and executed the call, returned the actual result under
the provider's tool-call ID, and the model answered from that result. No CAD
geometry was changed.

This is the narrow protocol milestone. It does **not** demonstrate a live
redesign: construction, verification and comparison were deliberately not
exposed to the model in this test.

## What the test does

`python -m unlock_engine.ai smoke --tool inspect_assembly` extends the existing
smoke command (`ai/smoke.py: run_tool_smoke`). Nothing is sent until every
precondition holds:

1. **Configuration:**
   - `AI_PROVIDER=meta`;
   - `MODEL_API_KEY` present (never printed);
   - `RUN_META_LIVE_TESTS=1`;
   - model exactly `muse-spark-1.3`;
   - base URL exactly `https://api.meta.ai/v1`.
2. **Fixture:** B01 (accessible cartridge) comes from the repository's fixture
   generator and is imported through the isolated engine worker and Stage A
   planner, giving the real `fixture_B01` project and `rev_…` revision
   identifiers.
3. **Tool definition:** the model receives only `inspect_assembly`, derived from
   the production tool schema. It is a closed JSON object with
   `additionalProperties: false`, and the required project, revision, request
   and component identifiers are all declared.
4. **Request 1:**
   - developer instructions plus the task;
   - the component IDs, but not their roles;
   - `tool_choice="auto"` and `parallel_tool_calls=false`;
   - `reasoning_effort="low"` and `max_completion_tokens=2048`;
   - SDK retries off and a 45 s absolute deadline.
5. **Validation and execution:** every returned call goes through the existing
   strict dispatcher (`Toolbox.execute`). That means an allowlist, strict JSON,
   no extra properties, an identity check against the frozen project and
   revision, and known component IDs. A tool that is not exposed gets a typed
   `TOOL_NOT_ALLOWED` result and is never dispatched.
6. **Request 2:** the original assistant message with its `tool_calls` is sent
   back, followed by one `tool` message per call carrying the exact
   provider-issued `tool_call_id`. A third request is impossible: the harness
   refuses it.
7. **Outcome checks:**
   - the final JSON answer is compared field by field with the actual tool
     payload;
   - fixture STEP and manifest hashes are re-checked;
   - no candidate was constructed or verified;
   - the report is scanned for the credential.

A run is `passed` only if every check passes. Plain text instead of a tool call,
a schema failure, a provider error or an ungrounded answer all give `failed`.
Missing credentials or a missing flag give `skipped`, never success.

## Live result

| Item | Observed |
|---|---|
| Provider / endpoint | Meta Model API, `https://api.meta.ai/v1/chat/completions` |
| Model (configured and echoed by the API) | `muse-spark-1.3` |
| Tool requested | `inspect_assembly` (1 structured call, `finish_reason=tool_calls`) |
| Validated arguments | `project_id=fixture_B01`, `revision_id=rev_47c607418e24a536`, `request_id=req_abc123`, `component_ids=[base, target, cover, screw1, screw2]` |
| Tool-call ID | `call_28a...385a` (41 characters, preserved verbatim) |
| Tool execution | `ok`, evidence `ev_0ea1a6dc61f8`, 7.2 ms, 5 component records from the real import |
| Continuation | `finish_reason=stop`, no further tool request |
| Final response | `{"replaceable_component_ids": ["target"], "roles": {"target": "service_module"}, "summary": "Target is declared as a service_module and is the only replaceable component. It is not fixed and lists removal axis Z+ with staging region above."}` |
| Grounding | Matches the tool payload: `target` is the only `replaceable` record, role `service_module`, `fixed=false`, `removal_axes=["Z+"]`, `staging_region_id="above"`. No invented components. |
| Geometry | Input STEP and manifest SHA-256 unchanged; no candidate constructed or verified |
| Secrets | Key absent from the report, stdout and stderr |

All 15 checks passed:
- configured model and configured base URL;
- fixture loaded and tool definition;
- initial request and structured tool call;
- tool name allowed, arguments parse, arguments valid and tool executed;
- result correlation and continuation request;
- final answer grounded;
- no geometry mutation and no secret in the report.

The full report is
[`../evidence/meta-tool-smoke/live_report.json`](../evidence/meta-tool-smoke/live_report.json).
In it, `provider` records the backend's configured defaults (`medium`, 2 retries)
used by the redesign controller. `settings` records what this test actually sent
(`low`, 0 retries).

## API usage

| Request | Input tokens | Output tokens (reasoning) | Total | Latency |
|---|---:|---:|---:|---:|
| 1 — tool request | 920 | 214 (65) | 1,134 | 2.92 s |
| 2 — final answer | 1,983 | 197 (134) | 2,180 | 2.84 s |
| **Total** | **2,903** | **411 (199)** | **3,314** | **5.77 s** model, 15.1 s wall |

- **Requests:** 2 live requests, within the 2-request budget, with no retries.
- **Token counts:** reported by the provider on both responses.
- **Cached input:** 0.
- **Estimated cost:** **$0.0054**. This uses Meta's public Standard list price for
  `muse-spark-1.3` ($1.25 input, $4.25 output per million tokens), from
  <https://dev.meta.ai/docs/pricing-rate-limits> retrieved 2026-10-29. It is a
  list-price estimate, not an account-verified charge.
- **Balance and spending cap:** the API does not report remaining credit, and
  this application-side request budget is not an account-level spending cap.
- **Rate limits:** the response headers reported 3,000 requests and 4,000,000
  tokens per minute.

## Change found during inspection

The adapter previously sent `max_tokens`. Meta's Chat Completions reference marks
it deprecated in favour of `max_completion_tokens`, which bounds reasoning and
visible output together. The adapter now sends `max_completion_tokens`, plus
`parallel_tool_calls` when a caller pins it. The production controller's
behaviour is otherwise unchanged. It still uses `tool_choice="auto"` and handles
multiple calls per turn.

## Running it again

The command spends credits, so run it only when that is intended:

```sh
cd backend
RUN_META_LIVE_TESTS=1 .venv/bin/python -m unlock_engine.ai smoke --tool inspect_assembly --output .work/meta-tool-smoke/live.json
```

- **Output:** the full JSON report goes to stdout, and the check summary
  (starting `UNLOCK Meta tool-calling smoke: PASSED`) goes to stderr.
- **Exit code:** `0` means passed or skipped; read `status` to tell them apart.
  `2` means failed.
- **Gated pytest equivalent:** `test_live_meta_engineering_tool_call_cycle`.
  `RUN_META_LIVE_TESTS=1 .venv/bin/python -m pytest -m meta_live tests/test_meta_live.py`
  also runs the two older live cases, which use more requests.

Ordinary `pytest` never selects `meta_live` tests, and without the flag they skip
even when a key is present.

## Offline coverage

`tests/test_meta_tool_smoke.py` has 24 cases. They use the real OpenAI SDK, an
in-process `httpx` transport and a real B01 import, and make no API calls. They
cover:
- request shape: model, URL, effort, `max_completion_tokens`, `auto`, and no
  parallel calls;
- ID preservation and the continuation history;
- multiple calls answered in order;
- invalid JSON, non-object arguments and extra properties (`SCHEMA_ERROR`);
- foreign project, stale revision and unknown component (`STALE_EVIDENCE`);
- unexposed `construct_candidate` and `run_shell` calls (never dispatched);
- missing tool results rejected before sending;
- plain text not reported as a tool call;
- ungrounded answers;
- the third-request refusal and a timeout without retry;
- configuration gating, credential redaction (including a 401 that echoes the
  key) and the CLI.

These are protocol tests, not live evidence.

## Remaining scope

- Only `inspect_assembly` has been exercised live. The other seven tools, the
  bounded controller loop and a live redesign on B02 remain unverified against
  the real model.
- The model chose its own `request_id` (`req_abc123`) and inspected all five
  components. Behaviour under other prompts or reasoning efforts was not
  sampled: one run is a protocol check, not a reliability measure.
- Chat Completions redacts reasoning content between turns for external keys
  (Meta reasoning guide). Multi-turn redesign runs therefore depend on the
  structured tool results, which the controller already supplies.
