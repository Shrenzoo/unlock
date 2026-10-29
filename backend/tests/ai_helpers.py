"""Shared helpers for the AI controller tests: real fixtures, scripted fake-model steps."""

import dataclasses
import hashlib
import json

from unlock_engine.ai.provider import tool_call_message
from unlock_engine.ai.session import EngineeringSession
from unlock_engine.contracts import digest

_STAGE_A: dict = {}


def reuse_stage_a(monkeypatch):
    """Run the real Stage A once per (input, target); give every run a fresh session with empty caches."""
    original = EngineeringSession.open.__func__

    def cached(cls, step_bytes, manifest_data, target_id, *, deadline, search_policy):
        key = (
            hashlib.sha256(step_bytes).hexdigest(),
            digest(manifest_data),
            target_id,
            digest(search_policy),
        )
        if key not in _STAGE_A:
            _STAGE_A[key] = original(
                cls,
                step_bytes,
                manifest_data,
                target_id,
                deadline=deadline,
                search_policy=search_policy,
            )
        return dataclasses.replace(_STAGE_A[key], constructed={}, verified={})

    monkeypatch.setattr(EngineeringSession, "open", classmethod(cached))


def context(messages):
    text = messages[1]["content"]
    return json.loads(text[text.index("\n") + 1 :])


def tool_results(messages):
    """Tool messages after the most recent assistant turn, in call order."""
    out = []
    for m in reversed(messages):
        if m["role"] == "tool":
            out.append(json.loads(m["content"]))
        elif m["role"] == "assistant":
            break
    return list(reversed(out))


def ids(messages, request_id, **extra):
    run = context(messages)["run"]
    return dict(
        project_id=run["project_id"],
        revision_id=run["revision_id"],
        target_id=run["target_id"],
        request_id=request_id,
        **extra,
    )


def geometric_rejection(messages):
    return context(messages)["baseline"]["geometric_rejections"][0]["rejection_id"]


def calls(*items):
    return tool_call_message(*items)


def final(decision, candidate_ids=(), summary=""):
    return dict(
        role="assistant",
        content=json.dumps(
            dict(decision=decision, candidate_ids=list(candidate_ids), summary=summary)
        ),
    )


def relief(cx, cy, w, d):
    return dict(center_x_mm=cx, center_y_mm=cy, width_mm=w, depth_mm=d)


def proposal(request_id, params, evidence, template="T01", rationale="test proposal"):
    return dict(
        candidate_request_id=request_id,
        bracket_id="bridge",
        template_id=template,
        parameters=params,
        evidence_ids=list(evidence),
        rationale=rationale,
    )
