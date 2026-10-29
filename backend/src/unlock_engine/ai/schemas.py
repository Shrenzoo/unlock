"""Strict tool contracts (PRD §15) and run records for the AI redesign controller.

Tool arguments are parsed from the provider's raw JSON with strict=True: extra
properties, wrong types, NaN/inf and unknown enum values are rejected before
any handler runs. Every invocation carries project_id, revision_id and
request_id; target-dependent tools also carry target_id.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

from ..contracts import Model, Proposal

Handle = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,96}$")]
RequestId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class ToolArgs(Model):
    project_id: Handle
    revision_id: Handle
    request_id: RequestId
    # Optional on inspection tools; when present it must still equal the frozen target.
    target_id: Handle | None = None


class TargetArgs(ToolArgs):
    target_id: Handle


class InspectAssemblyArgs(ToolArgs):
    component_ids: tuple[Handle, ...] = Field(min_length=1, max_length=12)


class InspectConstraintsArgs(ToolArgs):
    constraint_ids: tuple[Handle, ...] = Field(default=(), max_length=32)


class AnalyzeRemovalArgs(TargetArgs):
    policy_id: Literal["planner_v1"]


class InspectBlockerArgs(TargetArgs):
    rejection_id: Handle


class ListInterventionsArgs(TargetArgs):
    bracket_id: Handle


class ConstructCandidateArgs(TargetArgs):
    proposal: Proposal


class VerifyCandidateArgs(TargetArgs):
    candidate_id: Handle


class CompareCandidatesArgs(TargetArgs):
    candidate_ids: tuple[Handle, ...] = Field(min_length=1, max_length=3)


TOOL_ARGS: dict[str, type[ToolArgs]] = {
    "inspect_assembly": InspectAssemblyArgs,
    "inspect_constraints": InspectConstraintsArgs,
    "analyze_removal": AnalyzeRemovalArgs,
    "inspect_blocker": InspectBlockerArgs,
    "list_interventions": ListInterventionsArgs,
    "construct_candidate": ConstructCandidateArgs,
    "verify_candidate": VerifyCandidateArgs,
    "compare_candidates": CompareCandidatesArgs,
}

TOOL_DESCRIPTIONS = {
    "inspect_assembly": "Declared roles, retaining relations, movement axes and measured bounds for up to 12 components.",
    "inspect_constraints": "Frozen constraints, protected/editable regions, keep-outs and envelope (empty list = all). Read only.",
    "analyze_removal": "Authoritative baseline removal search for the frozen target. Returns status, steps and rejection IDs.",
    "inspect_blocker": "Details of one rejected action: obstacles, evidence classification and BRep witness when available.",
    "list_interventions": "Server-owned templates enabled for a bracket, with the exact finite parameter values allowed.",
    "construct_candidate": "Ask the trusted CAD constructor to build one bounded template edit. Construction is not verification.",
    "verify_candidate": "Independent reconstruction, mandatory constraint checks, removal replanning and reverse insertion.",
    "compare_candidates": "Authoritative original-versus-candidate comparison under the PRD improvement rule.",
}

FailureCategory = Literal[
    "INVALID_PROPOSAL",
    "UNSUPPORTED_TEMPLATE",
    "CONSTRUCTION_FAILED",
    "CONSTRAINT_FAILED",
    "VERIFICATION_UNKNOWN",
    "NO_REPAIR_PATH",
    "REVERSE_INSERTION_FAILED",
    "STALE_EVIDENCE",
    "PROVIDER_ERROR",
    "TOOL_NOT_ALLOWED",
    "SCHEMA_ERROR",
    "DUPLICATE_CANDIDATE",
    "BUDGET_EXHAUSTED",
]


class Feedback(Model):
    """Structured failure the model can act on. Measurements are copied, never estimated."""

    category: FailureCategory
    message: str
    candidate_id: str | None = None
    constraint_id: str | None = None
    parameter: str | None = None
    measured: Any = None
    allowed: Any = None
    evidence_id: str | None = None
    retry_permitted: bool = False


class ToolResult(Model):
    tool: str
    call_id: str
    request_id: str | None
    status: Literal["ok", "rejected", "failed"]
    evidence_id: str | None
    input_hash: str | None
    policy_version: str
    payload: dict = {}
    feedback: Feedback | None = None
    cached: bool = False
    duration_ms: float = 0.0

    def for_model(self) -> dict:
        """Compact JSON returned to the model as the tool message content."""
        out: dict = dict(
            status=self.status,
            evidence_id=self.evidence_id,
            policy_version=self.policy_version,
        )
        if self.payload:
            out["payload"] = self.payload
        if self.feedback:
            out["feedback"] = self.feedback.model_dump(exclude_none=True)
        if self.cached:
            out["cached"] = True
        return out


CandidateStage = Literal[
    "PROPOSED", "REJECTED", "CONSTRUCTED", "CHECKED", "VERIFIED_IMPROVEMENT"
]
Outcome = Literal[
    "VERIFIED_IMPROVEMENT_FOUND",
    "NO_VERIFIED_IMPROVEMENT",
    "NO_SUPPORTED_CANDIDATE",
    "INCOMPLETE_ANALYSIS",
    "MODEL_UNAVAILABLE",
    "CANCELLED",
]
