"""Actual SDK serialization and parsing via an in-process HTTP transport; zero API calls."""

import json
import threading
import time
import asyncio

import httpx
import pytest

from unlock_engine.ai.config import load_config
from unlock_engine.ai.meta import MetaProvider
from unlock_engine.ai.provider import (
    ProviderError,
    build_provider,
    parse_completion,
    tool_call_message,
    parse_usage,
)


def payload(message=None, **extra):
    return dict(
        id="meta-req-1",
        model="muse-spark-1.3",
        choices=[
            dict(
                message=message or dict(role="assistant", content="ready"),
                finish_reason="tool_calls"
                if message and message.get("tool_calls")
                else "stop",
            )
        ],
        usage=dict(prompt_tokens=12, completion_tokens=8, total_tokens=20),
        **extra,
    )


def provider(handler, **env):
    return MetaProvider(
        load_config({"MODEL_API_KEY": "unit-test-key", **env}),
        transport=httpx.MockTransport(handler),
    )


def test_sdk_native_multiple_calls_and_continuation():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url == "https://api.meta.ai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer unit-test-key"
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=payload(
                    tool_call_message(
                        ("a", "inspect_assembly", {}),
                        ("b", "inspect_constraints", {}),
                        content="Inspecting evidence.",
                    )
                ),
            )
        return httpx.Response(200, json=payload())

    p = provider(handler)
    msgs = [
        dict(role="developer", content="Use engineering evidence."),
        dict(role="user", content="inspect"),
    ]
    tools = [
        dict(
            type="function",
            function=dict(name="inspect_assembly", parameters=dict(type="object")),
        )
    ]
    t = p.complete(msgs, tools, max_output_tokens=400, timeout_s=2)
    assert [c.id for c in t.tool_calls] == ["a", "b"]
    assert t.usage.total_tokens == 20 and t.provider == "meta"
    msgs.append(t.assistant_message)
    msgs.extend(
        dict(role="tool", tool_call_id=c.id, content="{}") for c in t.tool_calls
    )
    p.complete(msgs, tools, max_output_tokens=400, timeout_s=2)
    assert requests[1]["messages"] == msgs
    assert set(requests[0]) == {
        "model",
        "messages",
        "tools",
        "tool_choice",
        "max_tokens",
        "reasoning_effort",
    }
    assert (
        requests[0]["tool_choice"] == "auto"
        and requests[0]["reasoning_effort"] == "medium"
    )


@pytest.mark.parametrize(
    "status,body,kind,retryable",
    [
        (401, {"error": "unit-test-key"}, "AUTHENTICATION", False),
        (403, {}, "AUTHENTICATION", False),
        (404, {}, "MODEL_UNAVAILABLE", False),
        (402, {}, "USAGE_LIMIT", False),
        (429, {}, "RATE_LIMITED", True),
        (429, {"error": {"code": "insufficient_quota"}}, "USAGE_LIMIT", False),
        (503, {}, "PROVIDER_UNAVAILABLE", True),
        (400, {}, "BAD_REQUEST", False),
    ],
)
def test_sdk_errors_never_echo_key_or_retry_internally(status, body, kind, retryable):
    calls = []

    def handler(r):
        calls.append(r)
        return httpx.Response(status, json=body, headers={"retry-after": "3"})

    with pytest.raises(ProviderError) as e:
        provider(handler).complete([], [], max_output_tokens=10, timeout_s=2)
    assert e.value.kind == kind and e.value.retryable == retryable
    assert len(calls) == 1 and "unit-test-key" not in str(e.value)
    if status == 429 and retryable:
        assert e.value.retry_after_s == 3


def test_no_key_no_forced_tools_no_bad_correlation_no_request():
    p = provider(lambda r: pytest.fail("must not send request"))
    with pytest.raises(ProviderError):
        p.complete([], [], max_output_tokens=10, timeout_s=2, tool_choice="required")
    with pytest.raises(ProviderError):
        p.complete(
            [dict(role="tool", tool_call_id="invented", content="{}")],
            [],
            max_output_tokens=10,
            timeout_s=2,
        )
    p = build_provider(load_config({}))
    with pytest.raises(ProviderError) as e:
        p.complete([], [], max_output_tokens=10, timeout_s=2)
    assert e.value.kind == "MISSING_CREDENTIALS"


@pytest.mark.parametrize(
    "message",
    [
        dict(role="assistant", tool_calls=1),
        dict(
            role="assistant",
            tool_calls=[
                dict(
                    id="same", type="function", function=dict(name="x", arguments="{}")
                )
            ]
            * 2,
        ),
        dict(role="user", content="wrong role"),
    ],
)
def test_malformed_turns_rejected(message):
    with pytest.raises(ProviderError):
        parse_completion(payload(message), provider="meta", latency_ms=0)


def test_identity_is_exact_and_usage_cannot_reduce_budget():
    for name in ["other-muse-spark-1.3", "muse-spark-open", None]:
        data = payload()
        data["model"] = name
        with pytest.raises(ProviderError) as e:
            provider(lambda r: httpx.Response(200, json=data)).complete(
                [], [], max_output_tokens=10, timeout_s=2
            )
        assert e.value.kind == "MODEL_UNAVAILABLE"
    with pytest.raises(ProviderError):
        parse_usage(dict(completion_tokens=-4))


def test_deadline_and_cancellation_interrupt_waiting_response():
    async def slow(r):
        await asyncio.sleep(5)
        return httpx.Response(200, json=payload())

    started = time.monotonic()
    with pytest.raises(ProviderError) as e:
        provider(slow).complete([], [], max_output_tokens=10, timeout_s=0.15)
    assert e.value.kind == "TIMEOUT" and time.monotonic() - started < 1
    cancel = threading.Event()
    timer = threading.Timer(0.1, cancel.set)
    timer.start()
    started = time.monotonic()
    with pytest.raises(ProviderError) as e:
        provider(slow).complete(
            [], [], max_output_tokens=10, timeout_s=3, cancel_event=cancel
        )
    timer.join()
    assert e.value.kind == "CANCELLED" and time.monotonic() - started < 1
