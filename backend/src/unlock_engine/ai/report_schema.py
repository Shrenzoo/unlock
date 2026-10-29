"""Typed, frontend-facing record of one AI redesign run (schema unlock.ai_run.v1).

Every report leaving the controller is validated against this model, and the
JSON Schema is published next to the engine's other contracts. Private model
reasoning is never part of the record.
"""

from __future__ import annotations

from typing import Any, Literal

from ..contracts import Model
from .schemas import CandidateStage, Outcome


class AIEvent(Model):
    sequence: int
    run_id: str
    at: str
    kind: Literal["stage", "model_turn", "tool_call", "provider_error", "final"]
    stage_label: str
    project_id: str | None = None
    revision_id: str | None = None
    model_id: str | None = None
    provider: str | None = None
    reasoning_effort: str | None = None
    # "model" or "deterministic:<rule>": who chose the tool call
    origin: str | None = None
    status: str | None = None
    detail: str | None = None
    retryable: bool | None = None
    request_id: str | None = None
    tool: str | None = None
    tool_call_id: str | None = None
    arguments: dict | None = None
    evidence_ids: list[str] = []
    failure: str | None = None
    cached: bool = False
    duration_ms: float | None = None
    usage: dict | None = None
    tool_calls: list[str] | None = None
    note: str | None = None


class StageMark(Model):
    stage: CandidateStage
    at_s: float
    detail: str


class CandidateReport(Model):
    handle: str
    attempt: int
    origin: str
    request_id: str
    proposal: dict
    final_stage: CandidateStage
    stages: list[StageMark]
    candidate_id: str | None
    construction: dict | None
    verification: dict | None
    revised_plan: dict | None
    comparison: dict | None
    feedback: dict | None


class AIRunReport(Model):
    schema_version: Literal["unlock.ai_run.v1"] = "unlock.ai_run.v1"
    run_id: str
    outcome: Outcome
    explanation: str
    stop_reason: str
    provenance: str
    live_model: bool
    model: dict | None
    identity: dict
    baseline: dict | None
    candidates: list[CandidateReport]
    selected_candidate: str | None
    final_model_message: dict | None
    events: list[AIEvent]
    usage: dict[str, Any]
    budget: dict[str, Any]
    timings: dict[str, Any]
    limitations: list[str]
    generated_at: str
