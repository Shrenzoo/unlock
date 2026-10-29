"""HTTP boundary types. Engineering records remain validated domain contracts."""

from typing import Literal
from pydantic import Field
from ..contracts import Model


class ProjectInput(Model):
    name: str = Field(min_length=1, max_length=120)


class StartRun(Model):
    target_id: str = Field(min_length=1, max_length=128)
    policy_id: Literal["policy_v1", "planner_v1"] = "planner_v1"
    constraint_hash: str = Field(pattern="^[a-f0-9]{64}$")


class DecisionInput(Model):
    decision: Literal["accept", "reject"]
    input_hash: str = Field(pattern="^[a-f0-9]{64}$")


class JobResponse(Model):
    job_id: str
    run_id: str | None = None


class ProjectSummary(Model):
    id: str
    fixture_code: str
    name: str
    description: str
    occurrences: int | None
    revision: str | None
    status: Literal["ready", "not_authored"]
    provenance: Literal["computed_earlier", "illustrative"]
    updated_at: str | None


class RevisionView(Model):
    id: str
    project_id: str
    label: str
    input_hash: str
    constraint_hash: str
    manifest: dict
    readiness: list[dict]
    preview_artifact_id: str
    provenance: dict


class RunView(Model):
    id: str
    revision_id: str
    target_id: str
    policy_version: str
    provenance: dict
    model: dict | None
    baseline: dict | None
    events: list[dict]
    candidates: list[dict]
    selected_candidate_id: str | None
    metrics: list[dict]
    state: str
    outcome: str | None = None
    explanation: str | None = None
    ai_report_artifact_id: str | None = None
    export: dict | None = None
    evidence_refs: dict[str, str] = {}
