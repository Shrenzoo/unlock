"""Offline checks of the two-request Meta tool-calling smoke; zero API calls.

Requests pass through the real OpenAI SDK into an in-process httpx transport and
the tool executes on a real B01 import. Passing here is never live Meta evidence.
"""

import asyncio
import json
import logging

import httpx
import pytest

from unlock_engine.ai.__main__ import main
from unlock_engine.ai.config import load_config
from unlock_engine.ai.meta import MetaProvider
from unlock_engine.ai.provider import ProviderError, tool_call_message
from unlock_engine.ai.smoke import prepare_tool_fixture, run_tool_smoke

KEY = "unit-test-key-7f3a9c2e51"
LIVE = {"RUN_META_LIVE_TESTS": "1"}
ALL = ["base", "target", "cover", "screw1", "screw2"]
GOOD_ANSWER = json.dumps(
    dict(
        replaceable_component_ids=["target"],
        roles={"target": "service_module"},
        summary="target is the declared replaceable service_module.",
    )
)


@pytest.fixture(scope="module")
def b01(tmp_path_factory):
    fixture = prepare_tool_fixture("B01", tmp_path_factory.mktemp("tool-smoke"))
    yield fixture
    fixture.close()


def config(**env):
    return load_config({"MODEL_API_KEY": KEY, **env})


def reply(message, prompt=40, completion=20):
    return httpx.Response(
        200,
        json=dict(
            id="req-abcdef123456789",
            model="muse-spark-1.3",
            choices=[
                dict(
                    message=message,
                    finish_reason="tool_calls" if message.get("tool_calls") else "stop",
                )
            ],
            usage=dict(
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=prompt + completion,
            ),
        ),
    )


def text(content):
    return reply(dict(role="assistant", content=content))


def args(session, **extra):
    return dict(
        project_id=session.project_id,
        revision_id=session.revision_handle,
        request_id="r1",
        **extra,
    )


class Endpoint:
    """Scripted Chat Completions endpoint that records every request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.bodies = []
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        self.bodies.append(json.loads(request.content))
        return self.replies[len(self.bodies) - 1]


def run(b01, endpoint, cfg=None, env=LIVE):
    return run_tool_smoke(
        cfg or config(), env=env, transport=httpx.MockTransport(endpoint), fixture=b01
    )


def checks(report):
    return {c["name"]: c["result"] for c in report["checks"]}


def test_complete_cycle_executes_real_tool_and_preserves_call_ids(b01):
    s = b01.session
    endpoint = Endpoint(
        reply(
            tool_call_message(
                ("call_9f2c", "inspect_assembly", args(s, component_ids=ALL))
            )
        ),
        text(GOOD_ANSWER),
    )
    report = run(b01, endpoint)
    assert report["status"] == "passed", report["checks"]
    first, second = endpoint.bodies
    assert [str(r.url) for r in endpoint.requests] == [
        "https://api.meta.ai/v1/chat/completions"
    ] * 2
    assert all(r.headers["authorization"] == f"Bearer {KEY}" for r in endpoint.requests)
    assert first["model"] == "muse-spark-1.3" and first["reasoning_effort"] == "low"
    assert first["tool_choice"] == "auto" and first["parallel_tool_calls"] is False
    assert first["max_completion_tokens"] == 2048 and "max_tokens" not in first
    (tool,) = first["tools"]
    assert tool["type"] == "function" and tool["function"]["name"] == "inspect_assembly"
    assert tool["function"]["parameters"]["additionalProperties"] is False
    assert "strict" not in tool["function"]
    # The continuation carries the original assistant call and its correlated result.
    assert second["messages"][:2] == first["messages"]
    assistant, result = second["messages"][2:]
    assert assistant["tool_calls"][0]["id"] == "call_9f2c"
    assert result["role"] == "tool" and result["tool_call_id"] == "call_9f2c"
    payload = json.loads(result["content"])
    target = next(c for c in payload["payload"]["components"] if c["id"] == "target")
    assert payload["status"] == "ok" and payload["evidence_id"].startswith("ev_")
    assert target["replaceable"] and target["role"] == "service_module"
    assert target["bounds_mm"]
    assert report["usage"] == dict(
        requests_sent=2,
        input_tokens=80,
        output_tokens=40,
        total_tokens=120,
        reasoning_tokens=0,
        cached_input_tokens=0,
        source="provider_reported",
    )
    assert report["cost"]["estimated_usd"] > 0
    assert "not account-verified" in report["cost"]["price_source"]


def test_user_prompt_gives_identifiers_not_the_answer(b01):
    endpoint = Endpoint(text("I cannot inspect it."))
    run(b01, endpoint)
    user = endpoint.bodies[0]["messages"][1]["content"]
    assert b01.session.project_id in user and b01.session.revision_handle in user
    assert "service_module" not in user and "replaceable: target" not in user


def test_plain_text_is_never_reported_as_a_tool_call(b01):
    endpoint = Endpoint(text("The replaceable part is probably the target."))
    report = run(b01, endpoint)
    assert report["status"] == "failed" and len(endpoint.bodies) == 1
    assert checks(report)["structured_tool_call"] == "fail"
    assert report["tool_calls"] == [] and "first_response_text" in report


@pytest.mark.parametrize(
    "arguments, category",
    [
        ("{not json", "SCHEMA_ERROR"),
        ("[]", "SCHEMA_ERROR"),
        ("extra", "SCHEMA_ERROR"),
        ("project", "STALE_EVIDENCE"),
        ("revision", "STALE_EVIDENCE"),
        ("component", "STALE_EVIDENCE"),
    ],
)
def test_invalid_arguments_return_a_typed_failure_under_the_same_id(
    b01, arguments, category
):
    s = b01.session
    good = args(s, component_ids=["target"])
    arguments = dict(
        extra=dict(good, path="/etc/passwd"),
        project=dict(good, project_id="other_project"),
        revision=dict(good, revision_id="rev_0000000000000000"),
        component=dict(good, component_ids=["battery"]),
    ).get(arguments, arguments)
    endpoint = Endpoint(
        reply(tool_call_message(("bad_1", "inspect_assembly", arguments))),
        text(GOOD_ANSWER),
    )
    report = run(b01, endpoint)
    assert report["status"] == "failed"
    assert checks(report)["tool_arguments_valid"] == "fail"
    assert checks(report)["tool_result_correlation"] == "pass"
    sent = endpoint.bodies[1]["messages"][-1]
    result = json.loads(sent["content"])
    assert sent["tool_call_id"] == "bad_1" and result["status"] == "rejected"
    assert result["feedback"]["category"] == category and "payload" not in result


def test_unexposed_tools_are_refused_without_dispatch(b01):
    s = b01.session
    proposal = dict(
        bracket_id="bridge",
        template_id="T01",
        parameters=dict(center_x=0, center_y=-20, width=24, depth=12),
    )
    endpoint = Endpoint(
        reply(
            tool_call_message(
                (
                    "c_build",
                    "construct_candidate",
                    args(s, target_id="target", proposal=proposal),
                ),
                ("c_shell", "run_shell", {"command": "rm -rf /"}),
            )
        ),
        text(GOOD_ANSWER),
    )
    report = run(b01, endpoint)
    result = checks(report)
    assert report["status"] == "failed" and result["tool_name_allowed"] == "fail"
    assert result["no_geometry_mutation"] == "pass"
    assert not b01.session.constructed and not b01.session.verified
    assert [c["failure"] for c in report["tool_calls"]] == ["TOOL_NOT_ALLOWED"] * 2
    tool_messages = [m for m in endpoint.bodies[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["c_build", "c_shell"]


def test_multiple_calls_are_each_answered_in_order(b01):
    s = b01.session
    endpoint = Endpoint(
        reply(
            tool_call_message(
                ("a1", "inspect_assembly", args(s, component_ids=["target"])),
                (
                    "a2",
                    "inspect_assembly",
                    dict(args(s, component_ids=["base"]), request_id="r2"),
                ),
            )
        ),
        text(GOOD_ANSWER),
    )
    report = run(b01, endpoint)
    assert report["status"] == "passed", report["checks"]
    roles = [m["role"] for m in endpoint.bodies[1]["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "tool"]
    assert [m["tool_call_id"] for m in endpoint.bodies[1]["messages"][3:]] == [
        "a1",
        "a2",
    ]


def test_missing_tool_results_are_rejected_before_sending():
    endpoint = Endpoint()
    provider = MetaProvider(config(), transport=httpx.MockTransport(endpoint))
    history = [
        dict(role="user", content="inspect"),
        tool_call_message(
            ("x1", "inspect_assembly", {}), ("x2", "inspect_assembly", {})
        ),
        dict(role="tool", tool_call_id="x1", content="{}"),
    ]
    with pytest.raises(ProviderError) as e:
        provider.complete(history, [], max_output_tokens=64, timeout_s=2)
    assert e.value.kind == "BAD_REQUEST" and endpoint.bodies == []


def test_a_third_request_is_never_sent(b01):
    s = b01.session
    call = ("t1", "inspect_assembly", args(s, component_ids=["target"]))
    again = (
        "t2",
        "inspect_assembly",
        dict(args(s, component_ids=ALL), request_id="r9"),
    )
    endpoint = Endpoint(reply(tool_call_message(call)), reply(tool_call_message(again)))
    report = run(b01, endpoint)
    assert report["status"] == "failed" and len(endpoint.bodies) == 2
    assert checks(report)["final_answer"] == "fail"
    assert report["usage"]["requests_sent"] == 2


@pytest.mark.parametrize(
    "answer",
    [
        dict(replaceable_component_ids=["cover"], roles={}, summary="cover"),
        dict(
            replaceable_component_ids=["target", "battery"],
            roles={"target": "service_module"},
            summary="target",
        ),
        dict(
            replaceable_component_ids=["target"],
            roles={"target": "battery_pack"},
            summary="target",
        ),
        "The target is replaceable.",
    ],
)
def test_answers_that_disagree_with_the_tool_result_fail(b01, answer):
    s = b01.session
    endpoint = Endpoint(
        reply(
            tool_call_message(("g1", "inspect_assembly", args(s, component_ids=ALL)))
        ),
        text(answer if isinstance(answer, str) else json.dumps(answer)),
    )
    report = run(b01, endpoint)
    assert report["status"] == "failed"
    assert checks(report)["final_answer_grounded"] == "fail"


def test_timeout_fails_safely_without_retry(b01):
    calls = []

    async def slow(request):
        calls.append(request)
        await asyncio.sleep(5)
        return text("late")

    report = run_tool_smoke(
        config(UNLOCK_AI_REQUEST_TIMEOUT_S="0.2"),
        env=LIVE,
        transport=httpx.MockTransport(slow),
        fixture=b01,
    )
    assert report["status"] == "failed" and len(calls) == 1
    assert report["error"]["kind"] == "TIMEOUT"
    assert report["requests"][0]["status"] == "error"


@pytest.mark.parametrize(
    "cfg, env, outcome",
    [
        (dict(), LIVE, "skipped"),
        (dict(MODEL_API_KEY=KEY), {}, "skipped"),
        (
            dict(MODEL_API_KEY=KEY, META_MODEL="muse-spark-1.3-contributor"),
            LIVE,
            "failed",
        ),
        (
            dict(MODEL_API_KEY=KEY, META_BASE_URL="https://example.com/v1"),
            LIVE,
            "failed",
        ),
    ],
)
def test_configuration_is_checked_before_any_request(b01, cfg, env, outcome):
    endpoint = Endpoint()
    report = run(b01, endpoint, cfg=load_config(cfg), env=env)
    assert report["status"] == outcome and endpoint.bodies == []
    if not cfg:
        assert "MODEL_API_KEY is not set" in report["reason"]


def test_credentials_never_reach_reports_logs_or_output(b01, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    s = b01.session
    echo = httpx.Response(401, json=dict(error=dict(message=f"bad key {KEY}")))
    for endpoint in (
        Endpoint(
            reply(
                tool_call_message(
                    ("k1", "inspect_assembly", args(s, component_ids=ALL))
                )
            ),
            text(GOOD_ANSWER),
        ),
        Endpoint(echo),
    ):
        report = run(b01, endpoint)
        assert KEY not in json.dumps(report, default=str)
        assert checks(report)["no_secret_in_report"] == "pass"
    assert report["error"]["kind"] == "AUTHENTICATION"
    out = capsys.readouterr()
    assert KEY not in caplog.text and KEY not in out.out + out.err


def test_cli_without_credentials_is_skipped_and_offline(monkeypatch, capsys):
    monkeypatch.setenv("MODEL_API_KEY", "")
    monkeypatch.setenv("RUN_META_LIVE_TESTS", "0")
    monkeypatch.setenv("AI_PROVIDER", "meta")
    assert main(["smoke", "--tool", "inspect_assembly"]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["status"] == "skipped"
    assert "SKIPPED" in out.err and "MODEL_API_KEY is not set" in out.err
