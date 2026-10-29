"""Bounded inspect → propose → construct → verify → compare loop (PRD §15, BL017-BL018).

The controller owns budgets, conversation ordering, retries and the final
outcome. The model chooses tools and parameters; the engine decides validity.
A final status is derived only from candidate evidence and the planner's
comparison, never from what the model says about itself.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone

from ..contracts import POLICY, EngineError
from ..planning.contracts import SearchPolicy
from ..verification import UNVERIFIED
from .config import PriceTable
from .prompt import SYSTEM_PROMPT, initial_context
from .report_schema import AIRunReport
from .provider import ModelProvider, ProviderError
from .schemas import Outcome
from .session import Deadline, EngineeringSession
from .toolbox import Budget, Counters, Toolbox, plan_summary

STAGE_LABELS = {
    "inspect_assembly": "Inspecting component relationships",
    "inspect_constraints": "Reviewing constraints",
    "analyze_removal": "Analyzing removal paths",
    "inspect_blocker": "Analyzing obstruction",
    "list_interventions": "Selecting supported redesign",
    "construct_candidate": "Constructing candidate geometry",
    "verify_candidate": "Checking protected interfaces and replanning removal",
    "compare_candidates": "Comparing design revisions",
}

LIMITATIONS = (
    *UNVERIFIED[:4],
    "Geometry checks cover the listed constraints, supported axis translations and annotated reusable screws only",
    "A verified improvement is a design-review result, not engineering or manufacturing release approval",
)


def now():
    return datetime.now(timezone.utc).isoformat()


class EventLog:
    def __init__(self, run_id, identity):
        self.run_id = run_id
        self.identity = identity
        self.events: list[dict] = []
        self.observer = None

    def emit(self, kind, label, **fields):
        event = dict(
            sequence=len(self.events) + 1,
            run_id=self.run_id,
            at=now(),
            kind=kind,
            stage_label=label,
            **self.identity,
            **fields,
        )
        self.events.append(event)
        if self.observer:
            self.observer(event)
        return event


def parse_final(content: str | None) -> dict:
    """The model's closing statement. Recorded, never used as evidence."""
    text = (content or "").strip()
    fenced = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(fenced.group(0) if fenced else text)
        decision = data.get("decision")
        ids = data.get("candidate_ids", [])
        summary = data.get("summary", "")
        if (
            decision in ("candidate_proposed", "no_supported_candidate", "stopped")
            and isinstance(ids, list)
            and isinstance(summary, str)
        ):
            return dict(
                decision=decision,
                candidate_ids=[str(i)[:64] for i in ids][:3],
                summary=summary[:600],
                structured=True,
            )
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return dict(
        decision="unstructured", candidate_ids=[], summary=text[:600], structured=False
    )


def estimate_cost(counters: Counters, prices: PriceTable | None) -> dict:
    if prices is None:
        return dict(estimated_usd=None, reason="no price table configured")
    if counters.usage_reported_turns < counters.provider_requests:
        return dict(
            estimated_usd=None, reason="provider did not report usage for every turn"
        )
    cached = counters.cached_input_tokens or 0
    fresh = counters.input_tokens - cached
    usd = (
        fresh * prices.input_per_mtok / 1e6
        + counters.output_tokens * prices.output_per_mtok / 1e6
    )
    if cached:
        usd += (
            cached
            * (
                prices.cached_input_per_mtok
                if prices.cached_input_per_mtok is not None
                else prices.input_per_mtok
            )
            / 1e6
        )
    return dict(
        estimated_usd=round(usd, 6),
        price_source=prices.source,
        price_retrieved_at=prices.retrieved_at,
    )


class RedesignRun:
    """One bounded run against one frozen revision and target."""

    def __init__(
        self,
        step_bytes: bytes,
        manifest: dict,
        target_id: str,
        *,
        budget: Budget = Budget(),
        search_policy: SearchPolicy = SearchPolicy(),
        cancel: threading.Event | None = None,
        run_id: str | None = None,
        on_event=None,
        session=None,
        artifact_root=None,
    ):
        self.step_bytes = step_bytes
        self.manifest = manifest
        self.target_id = target_id
        self.budget = budget
        self.search_policy = search_policy
        self.cancel = cancel
        self.run_id = run_id or "run_" + uuid.uuid4().hex[:16]
        self.counters = Counters()
        self.session: EngineeringSession | None = None
        self.toolbox: Toolbox | None = None
        self.deadline: Deadline | None = None
        self.log: EventLog | None = None
        self.on_event = on_event
        self.precomputed_session = session
        self.artifact_root = artifact_root

    # ── Stage A (shared by the model controller and deterministic selectors) ──

    def open(self, *, model_identity: dict) -> str | None:
        """Returns an early stop reason, or None when the redesign stage may run."""
        self.deadline = Deadline(self.budget.max_seconds, self.cancel)
        self.log = EventLog(
            self.run_id,
            dict(
                project_id=self.manifest.get("project_id"),
                revision_id=None,
                **model_identity,
            ),
        )
        self.log.observer = self.on_event
        self.log.emit(
            "stage",
            "Loading frozen revision and running baseline analysis",
            status="started",
        )
        try:
            self.session = self.precomputed_session or EngineeringSession.open(
                self.step_bytes,
                self.manifest,
                self.target_id,
                deadline=self.deadline,
                search_policy=self.search_policy,
            )
        except EngineError as exc:
            self.log.emit(
                "stage",
                "Loading frozen revision and running baseline analysis",
                status="failed",
                detail=f"{exc.code}: {exc}",
            )
            return (
                "cancelled"
                if self.deadline.cancelled
                else f"stage_a_{exc.code.lower()}"
            )
        if self.precomputed_session:
            from ..contracts import digest

            s = self.session
            if (
                s.package.step != self.step_bytes
                or digest(s.manifest_data) != digest(self.manifest)
                or s.target_id != self.target_id
                or s.search_policy != self.search_policy
                or s.baseline.revision_id != s.revision_hash
            ):
                raise EngineError(
                    "STALE_REVISION", "precomputed baseline does not match frozen run"
                )
        self.log.identity["revision_id"] = self.session.revision_handle
        self.session.artifact_root = self.artifact_root
        self.toolbox = Toolbox(
            self.session,
            self.budget,
            self.counters,
            self.deadline,
            origin=model_identity.get("origin", "model"),
        )
        base = self.session.baseline
        self.log.emit(
            "stage",
            "Baseline removal analysis",
            status=base.status,
            evidence_ids=[self.toolbox.issue("plan", base.id)],
            duration_ms=round(self.session.timings["baseline_ms"], 1),
            detail=f"complete={base.complete} expanded_states={base.expanded_states}",
        )
        if self.deadline.cancelled or base.status == "cancelled":
            return "cancelled"
        if base.status in ("incomplete", "invalid_input"):
            return "baseline_" + base.status
        if (
            base.status == "feasible"
            and base.optimal_within_scope
            and base.metrics
            and tuple(base.metrics.cost) == (0, 0, 0, 1)
        ):
            return "already_minimal"
        if not self.session.manifest.template_bindings:
            return "no_constructor_binding"
        return None

    # ── final derivation ─────────────────────────────────────────────────

    def derive(
        self, stop_reason: str, *, model_failed: bool = False, final: dict | None = None
    ) -> tuple[Outcome, str]:
        cands = list(self.toolbox.candidates.values()) if self.toolbox else []
        for c in cands:
            self.toolbox.assess(
                c
            )  # authoritative planner comparison, also for model-skipped compares
        improved = [c for c in cands if c.final_stage == "VERIFIED_IMPROVEMENT"]
        if stop_reason == "cancelled" or (self.deadline and self.deadline.cancelled):
            return "CANCELLED", "Run cancelled; no result was selected for acceptance."
        if improved:
            c = improved[0]
            return "VERIFIED_IMPROVEMENT_FOUND", (
                f"{c.handle} ({c.template_id} {c.parameters}) passed independent verification and the planner comparison: {c.comparison['explanation']}"
            )
        if stop_reason == "cancelled" or (self.deadline and self.deadline.cancelled):
            return "CANCELLED", "Run cancelled; no uncommitted result was promoted."
        if model_failed:
            return (
                "MODEL_UNAVAILABLE",
                "The model stage could not complete; the deterministic baseline analysis is preserved.",
            )
        if stop_reason.startswith("stage_a") or stop_reason.startswith("baseline_"):
            return (
                "INCOMPLETE_ANALYSIS",
                f"Baseline analysis did not complete ({stop_reason}); the model was not called.",
            )
        if stop_reason == "already_minimal":
            return (
                "NO_SUPPORTED_CANDIDATE",
                "The target already has the minimal supported removal route (one operation, no unrelated parts); no redesign is needed.",
            )
        if stop_reason == "no_constructor_binding":
            return (
                "NO_SUPPORTED_CANDIDATE",
                "No component in this assembly has a trusted constructor binding, so no supported intervention exists.",
            )
        pending = [
            c
            for c in cands
            if c.final_stage == "CONSTRUCTED"
            or (c.feedback or {}).get("category") == "VERIFICATION_UNKNOWN"
        ]
        if pending:
            return (
                "INCOMPLETE_ANALYSIS",
                f"{len(pending)} candidate(s) were not conclusively checked before the run stopped ({stop_reason}).",
            )
        if cands:
            return (
                "NO_VERIFIED_IMPROVEMENT",
                f"{len(cands)} candidate(s) attempted; none passed verification and the improvement rule ({stop_reason}).",
            )
        if stop_reason in (
            "time_budget",
            "turn_budget",
            "tool_call_budget",
            "output_token_budget",
            "schema_repair_exhausted",
        ):
            return (
                "INCOMPLETE_ANALYSIS",
                f"The run stopped ({stop_reason}) before any supported proposal was evaluated.",
            )
        return (
            "NO_SUPPORTED_CANDIDATE",
            "No supported proposal was justified from the evidence.",
        )

    def report(
        self,
        outcome: Outcome,
        explanation: str,
        stop_reason: str,
        *,
        provenance: str,
        model: dict | None,
        final: dict | None,
        prices: PriceTable | None,
    ) -> dict:
        s = self.session
        cands = list(self.toolbox.candidates.values()) if self.toolbox else []
        selected = next(
            (c.handle for c in cands if c.final_stage == "VERIFIED_IMPROVEMENT"), None
        )
        if outcome != "VERIFIED_IMPROVEMENT_FOUND":
            selected = None
        evidence = s.full_evidence() if s else {}
        evidence["tool_results"] = (
            [r.model_dump(mode="json") for r in self.toolbox.results]
            if self.toolbox
            else []
        )
        if self.artifact_root:
            from ..artifacts import ArtifactStore

            store = ArtifactStore(self.artifact_root)
            evidence["input_artifacts"] = {
                "assembly.step": store.put(self.step_bytes),
                "manifest.json": store.put_json(self.manifest),
            }
        if self.log:
            self.log.emit(
                "final", "Run complete", status=outcome, detail=explanation[:300]
            )
        if self.deadline:
            self.deadline.close()
        report = dict(
            run_id=self.run_id,
            outcome=outcome,
            explanation=explanation,
            stop_reason=stop_reason,
            provenance=(
                "deterministic_only"
                if provenance == "live_model" and self.counters.turns == 0
                else provenance
            ),
            live_model=bool(model and model.get("live") and self.counters.turns > 0),
            model=model,
            identity=dict(
                project_id=s.project_id,
                revision_id=s.revision_hash,
                revision_handle=s.revision_handle,
                target_id=s.target_id,
                geometry_hash=s.geometry_hash,
                constraint_hash=s.constraint_hash,
                policy_version=POLICY.version,
                search_policy=s.search_policy.model_dump(mode="json"),
            )
            if s
            else dict(
                project_id=self.manifest.get("project_id"), target_id=self.target_id
            ),
            baseline=plan_summary(s.baseline, self.toolbox) if s else None,
            candidates=[c.report() for c in cands],
            engineering_evidence=evidence,
            selected_candidate=selected,
            final_model_message=dict(
                final, authority="none: model statement, not engineering evidence"
            )
            if final
            else None,
            events=self.log.events if self.log else [],
            usage=dict(
                **self.counters.__dict__,
                source="provider_reported"
                if model and model.get("live")
                else (
                    "none"
                    if not model
                    else "synthetic: offline fake provider, not real usage"
                ),
                cost=estimate_cost(self.counters, prices),
            ),
            budget=self.budget.__dict__,
            timings=dict(
                total_s=round(self.deadline.elapsed(), 3) if self.deadline else None,
                stage_a=s.timings if s else None,
            ),
            limitations=list(LIMITATIONS),
            generated_at=now(),
        )
        # Validated against the published frontend contract before it leaves the controller.
        return AIRunReport.model_validate(report).model_dump(mode="json")


def run_with_model(
    step_bytes: bytes,
    manifest: dict,
    target_id: str,
    provider: ModelProvider,
    *,
    budget: Budget = Budget(),
    search_policy: SearchPolicy = SearchPolicy(),
    cancel: threading.Event | None = None,
    prices: PriceTable | None = None,
    request_timeout_s: float = 45.0,
    max_retries: int = 2,
    on_event=None,
    session=None,
    run_id: str | None = None,
    artifact_root=None,
) -> dict:
    run = RedesignRun(
        step_bytes,
        manifest,
        target_id,
        budget=budget,
        search_policy=search_policy,
        cancel=cancel,
        on_event=on_event,
        session=session,
        run_id=run_id,
        artifact_root=artifact_root,
    )
    model = dict(
        provider=provider.provider,
        model_id=provider.model,
        reasoning_effort=provider.reasoning_effort,
        live=provider.live,
        origin="model",
    )
    provenance = "live_model" if provider.live else "offline_fake_provider"
    early = run.open(
        model_identity=dict(
            model_id=provider.model,
            provider=provider.provider,
            reasoning_effort=provider.reasoning_effort,
            origin="model",
        )
    )
    if early:
        outcome, why = run.derive(early)
        return run.report(
            outcome,
            why,
            early,
            provenance=provenance,
            model=dict(model, called=False),
            final=None,
            prices=prices,
        )

    tb, c, b, t = run.toolbox, run.counters, budget, run.deadline
    specs = tb.specs()
    messages = [
        dict(role="developer", content=SYSTEM_PROMPT),
        dict(role="user", content=initial_context(run.session, tb, budget)),
    ]
    stop, final, model_failed = None, None, False

    def call_model(max_tokens):
        attempt = 0
        while True:
            timeout = min(request_timeout_s, t.remaining() - 1)
            if timeout < 2:
                raise ProviderError(
                    "TIMEOUT", "run time budget exhausted before the model request"
                )
            cap = min(max_tokens, b.max_output_tokens - c.output_budget_used)
            if cap < 256:
                raise ProviderError(
                    "OUTPUT_BUDGET",
                    "output budget exhausted, including uncertain billed retries",
                )
            c.provider_requests += 1
            c.output_budget_used += cap
            try:
                turn = provider.complete(
                    messages,
                    specs,
                    max_output_tokens=cap,
                    timeout_s=timeout,
                    cancel_event=t.event,
                )
                if turn.usage.output_tokens is not None:
                    c.output_budget_used += turn.usage.output_tokens - cap
                else:
                    c.uncertain_output_tokens += cap
                return turn
            except ProviderError as exc:
                c.uncertain_output_tokens += cap
                run.log.emit(
                    "provider_error",
                    "Model request failed",
                    status=exc.kind,
                    detail=str(exc)[:200],
                    retryable=exc.retryable,
                )
                if not exc.retryable or attempt >= max_retries or t.cancelled:
                    raise
                wait = (
                    exc.retry_after_s
                    if exc.retry_after_s is not None
                    else min(2.0**attempt, 4.0)
                )
                if wait >= t.remaining() - 3:
                    raise ProviderError(
                        exc.kind, f"{exc}; retry would exceed the run budget"
                    ) from None
                if t.event.wait(wait) and t.cancelled:
                    raise ProviderError(
                        "CANCELLED", "cancelled while waiting to retry"
                    ) from None
                attempt += 1
                c.retries += 1

    while stop is None:
        if t.cancelled:
            stop = "cancelled"
            break
        if t.expired:
            stop = "time_budget"
            break
        if c.turns >= b.max_turns:
            stop = "turn_budget"
            break
        remaining_tokens = b.max_output_tokens - c.output_budget_used
        if remaining_tokens < 256:
            stop = "output_token_budget"
            break
        max_tokens = min(b.per_turn_output_tokens, remaining_tokens)
        try:
            turn = call_model(max_tokens)
        except ProviderError as exc:
            stop = (
                "output_token_budget"
                if exc.kind == "OUTPUT_BUDGET"
                else "cancelled"
                if exc.kind == "CANCELLED"
                else (
                    "time_budget"
                    if exc.kind == "TIMEOUT" and t.remaining() < 3
                    else "provider_error"
                )
            )
            model_failed = stop == "provider_error"
            run.log.emit(
                "stage",
                "Model stage unavailable",
                status=exc.kind,
                detail=str(exc)[:200],
            )
            break
        c.turns += 1
        c.model_latency_ms += turn.latency_ms
        u = turn.usage
        if u.output_tokens is not None:
            if u.input_tokens is not None and u.total_tokens is not None:
                c.usage_reported_turns += 1
            c.input_tokens += u.input_tokens or 0
            c.output_tokens += u.output_tokens
            c.total_tokens += u.total_tokens or 0
            c.cached_input_tokens += u.cached_input_tokens or 0
            c.reasoning_tokens += u.reasoning_tokens or 0
        messages.append(turn.assistant_message)
        run.log.emit(
            "model_turn",
            "Model turn",
            status=turn.finish_reason,
            request_id=turn.request_id,
            duration_ms=round(turn.latency_ms, 1),
            usage=u.raw or None,
            tool_calls=[tc.name for tc in turn.tool_calls],
            note=(turn.content or "")[:400] if turn.tool_calls else None,
        )
        if t.cancelled or t.expired:
            stop = "cancelled" if t.cancelled else "time_budget"
            break
        if c.output_budget_used > b.max_output_tokens:
            stop = "output_token_budget"
            break
        if not turn.tool_calls:
            final = parse_final(turn.content)
            if not final["structured"] and not tb.candidates:
                c.schema_errors += 1
                if c.schema_errors <= b.max_schema_repairs:
                    messages.append(
                        dict(
                            role="user",
                            content="No engineering outcome is established. Use an allowed tool to investigate, or return the documented final JSON explaining why no supported candidate can be justified. Do not invent a tool call or a passing result.",
                        )
                    )
                    continue
                stop = "schema_repair_exhausted"
            else:
                stop = "model_final"
            break
        budget_hit = False
        for call in turn.tool_calls:
            if (
                budget_hit
                or c.tool_calls >= b.max_tool_calls
                or t.event.is_set()
                or c.schema_errors > b.max_schema_repairs
            ):
                budget_hit = True
                content = dict(
                    status="rejected",
                    feedback=dict(
                        category="BUDGET_EXHAUSTED",
                        message="tool call budget exhausted; not executed",
                    ),
                )
                messages.append(
                    dict(role="tool", tool_call_id=call.id, content=json.dumps(content))
                )
                run.log.emit(
                    "tool_call",
                    STAGE_LABELS.get(call.name, "Tool call refused"),
                    tool=call.name[:40],
                    tool_call_id=call.id,
                    status="not_executed",
                    detail="budget exhausted",
                )
                continue
            c.tool_calls += 1
            run.log.emit(
                "stage",
                STAGE_LABELS.get(call.name, "Tool call validation"),
                status="started",
                tool=call.name[:40],
            )
            result, schema_error = tb.execute(call)
            if schema_error:
                c.schema_errors += 1
            messages.append(
                dict(
                    role="tool",
                    tool_call_id=call.id,
                    content=json.dumps(
                        result.for_model(), separators=(",", ":"), default=str
                    ),
                )
            )
            try:
                validated = json.loads(call.arguments) if result.input_hash else None
            except json.JSONDecodeError:
                validated = None
            run.log.emit(
                "tool_call",
                STAGE_LABELS.get(call.name, "Tool call refused"),
                tool=result.tool,
                tool_call_id=call.id,
                request_id=result.request_id,
                arguments=validated,
                status=result.status,
                evidence_ids=[
                    e
                    for e in (
                        result.evidence_id,
                        (result.payload or {}).get("candidate_id"),
                        (result.feedback.evidence_id if result.feedback else None),
                    )
                    if e
                ],
                failure=result.feedback.category if result.feedback else None,
                cached=result.cached,
                duration_ms=result.duration_ms,
            )
        if c.schema_errors > b.max_schema_repairs:
            stop = "schema_repair_exhausted"
        elif budget_hit:
            stop = (
                "cancelled"
                if t.cancelled
                else "time_budget"
                if t.expired
                else "tool_call_budget"
            )
    outcome, why = run.derive(stop, model_failed=model_failed, final=final)
    return run.report(
        outcome,
        why,
        stop,
        provenance=provenance,
        model=dict(model, called=True),
        final=final,
        prices=prices,
    )
