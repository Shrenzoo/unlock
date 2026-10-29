"""PRD section 20 planning records. Native geometry never enters these contracts."""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from ..contracts import Axis, Check, Model, POLICY, Transform, digest
from ..motion import PathResult

Kind = Literal["REMOVE_FASTENER", "TRANSLATE_PART"]
PlanStatus = Literal[
    "feasible", "no_path_supported", "incomplete", "invalid_input", "cancelled"
]
Cost = tuple[int, int, int, int]


class SearchPolicy(Model):
    version: Literal["planner_v1"] = "planner_v1"
    max_expanded_states: int = Field(default=4096, ge=1, le=4096)
    max_seconds: float = Field(default=30, gt=0, le=30)
    clearance_mm: float = Field(default=POLICY.clearance_mm, ge=POLICY.clearance_mm)
    endpoint_rule: Literal["explicit_path_else_nearest_stage_interior_v1"] = (
        "explicit_path_else_nearest_stage_interior_v1"
    )
    objective: tuple[str, ...] = (
        "unrelated_parts",
        "fasteners",
        "tool_changes",
        "operations",
    )

    @model_validator(mode="after")
    def frozen_objective(self):
        if self.objective != (
            "unrelated_parts",
            "fasteners",
            "tool_changes",
            "operations",
        ):
            raise ValueError("the lexicographic objective is fixed")
        return self


@dataclass(frozen=True)
class State:
    removed: frozenset[str] = frozenset()
    last_tool: str | None = None

    def __post_init__(self):
        if not isinstance(self.removed, frozenset) or any(
            not isinstance(k, str) for k in self.removed
        ):
            raise ValueError(
                "removed IDs must be an immutable frozenset of occurrence strings"
            )

    def identity(self, input_hash: str) -> str:
        return digest([input_hash, sorted(self.removed), self.last_tool])


class Action(Model):
    kind: Kind
    component_id: str
    axis: Axis
    distance_mm: float = Field(gt=0)
    tool_id: str | None = None


class Certificate(Model):
    id: str
    revision_id: str
    input_hash: str
    geometry_hash: str
    constraint_hash: str
    tool_hash: str
    policy_hash: str
    before_state_hash: str
    action: Action
    mode: Literal["removal", "insertion"]
    status: Literal["clear", "blocked", "unknown"]
    paths: tuple[PathResult, ...]
    subchecks: tuple[str, ...]
    assumptions: str = "Rigid original placements; reusable screw rotation and torque abstracted; identical replacement geometry"


class Rejection(Model):
    id: str
    revision_id: str
    state_hash: str
    removed_ids: tuple[str, ...]
    action: Action
    remaining_obstacle_ids: tuple[str, ...]
    constraint_ids: tuple[str, ...]
    reason: str
    category: Literal[
        "SEMANTICALLY_BLOCKED",
        "CONFIRMED_GEOMETRIC_OBSTRUCTION",
        "INSUFFICIENT_CLEARANCE",
        "TOOL_ACCESS_BLOCKED",
        "UNKNOWN_GEOMETRY",
        "UNSUPPORTED_OPERATION",
    ]
    geometry_evidence_level: str
    witness_certificate_ids: tuple[str, ...] = ()
    policy_version: str = POLICY.version


class Step(Model):
    action_id: str
    kind: Kind
    component_id: str
    prerequisite_ids: tuple[str, ...]
    tool_id: str | None
    start_transform: Transform
    end_transform: Transform
    axis: Axis
    distance_mm: float = Field(gt=0)
    certificate_ids: tuple[str, ...] = Field(min_length=1)
    before_state_hash: str
    after_state_hash: str

    def action(self):
        return Action(
            kind=self.kind,
            component_id=self.component_id,
            axis=self.axis,
            distance_mm=self.distance_mm,
            tool_id=self.tool_id,
        )


class Metrics(Model):
    unrelated_parts_removed: int = Field(ge=0)
    fasteners_removed: int = Field(ge=0)
    tool_changes: int = Field(ge=0)
    operations: int = Field(ge=0)
    unique_tools: int = Field(ge=0)
    cost: Cost
    noncontact_clearance_lower_bound_mm: float | None
    has_contact_exemptions: bool


class ValidationReport(Model):
    status: Literal["passed", "failed", "unknown", "not_run"]
    explanation: str
    checked_steps: int = 0
    certificates: tuple[Certificate, ...] = ()
    final_removed_ids: tuple[str, ...] = ()
    geometric_insertion: str = "not_run"
    fastener_reinsertion: str = "not_run"
    tool_access: str = "not_run"
    connection_restoration: str = "not_run"
    elapsed_ms: float = 0


class SearchStats(Model):
    generated_actions: int = 0
    admitted_transitions: int = 0
    rejected_transitions: int = 0
    unknown_transitions: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    geometry_validation_calls: int = 0
    peak_frontier: int = 0
    frontier_size: int = 0
    frontier_status: str = "not_started"
    termination: str = "not_started"


class FieldError(Model):
    field: str
    message: str
    expected_type: str | None = None


class ErrorEnvelope(Model):
    error_code: Literal[
        "INVALID_PACKAGE",
        "INVALID_MANIFEST",
        "UNSUPPORTED_SEMANTICS",
        "INVALID_SOLID",
        "LIMIT_EXCEEDED",
        "STALE_REVISION",
        "UNSUPPORTED_TEMPLATE",
        "CONSTRAINT_VIOLATION",
        "GEOMETRY_FAILED",
        "VERIFICATION_UNKNOWN",
        "MODEL_UNAVAILABLE",
        "MODEL_SCHEMA_ERROR",
        "NOT_FOUND",
        "FORBIDDEN",
        "CANCELLED",
    ]
    message: str
    retryable: bool
    field_errors: tuple[FieldError, ...]
    evidence_ids: tuple[str, ...]
    run_id: str | None

    def __getitem__(self, key):
        return getattr(self, key)


class PlanResult(Model):
    id: str
    status: PlanStatus
    revision_id: str
    original_revision_id: str | None = None
    modified_occurrence_ids: tuple[str, ...] = ()
    target_id: str
    input_hash: str
    geometry_hash: str
    constraint_hash: str
    comparison_hash: str
    policy_version: str = POLICY.version
    search_policy: SearchPolicy
    complete: bool
    optimal_within_scope: bool
    expanded_states: int = 0
    elapsed_ms: float = 0
    limits: SearchPolicy
    unresolved_transition_count: int = 0
    steps: tuple[Step, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    certificates: tuple[Certificate, ...] = ()
    metrics: Metrics | None = None
    stats: SearchStats = SearchStats()
    replay: ValidationReport = ValidationReport(
        status="not_run", explanation="No checked goal route"
    )
    reverse: ValidationReport = ValidationReport(
        status="not_run", explanation="No checked goal route"
    )
    constraint_checks: tuple[tuple[str, str], ...] = ()
    static_verification_id: str | None = None
    static_checks: tuple[Check, ...] = ()
    replacement_verified: bool = False
    error: ErrorEnvelope | None = None
    provenance: Literal["computed", "retrieved"] = "computed"
    scope: str = "Finite rigid axis translations and annotated reusable screws; no physical repair or manufacturing certification"

    @model_validator(mode="after")
    def honest_result(self):
        if self.status == "no_path_supported" and (
            not self.complete or self.unresolved_transition_count or self.steps
        ):
            raise ValueError("no-path requires exhaustive, conclusive exploration")
        if self.optimal_within_scope and (
            self.status != "feasible"
            or not self.complete
            or self.unresolved_transition_count
        ):
            raise ValueError(
                "optimality requires a complete conclusive feasible search"
            )
        if self.status == "feasible" and (
            not self.steps or self.replay.status != "passed" or self.metrics is None
        ):
            raise ValueError(
                "feasibility requires steps, independent replay and actual metrics"
            )
        if self.status != "feasible" and (
            self.steps or self.metrics or self.replacement_verified
        ):
            raise ValueError(
                "unfinished or invalid results cannot carry successful steps"
            )
        if self.replacement_verified and (
            self.reverse.status != "passed"
            or any(v != "pass" for _, v in self.constraint_checks)
        ):
            raise ValueError(
                "replacement requires reverse restoration and every mandatory constraint"
            )
        return self
