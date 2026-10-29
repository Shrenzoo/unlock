"""Offline tests of the hosted-model adapter against a local stub server (no network, no credentials)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from unlock_engine.ai.config import load_config
from unlock_engine.ai.provider import (
    FakeProvider,
    OpenAICompatibleProvider,
    ProviderError,
    parse_completion,
    tool_call_message,
)
from unlock_engine.ai.smoke import run_smoke

MODEL = "accounts/fireworks/models/muse-spark-open"


class Stub:
    def __init__(self):
        self.responses = []
        self.requests = []

    def __enter__(self):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.requests.append(
                    dict(
                        path=self.path,
                        body=body,
                        auth=self.headers.get("Authorization"),
                    )
                )
                status, payload, headers, delay = stub.responses.pop(0)
                time.sleep(delay)
                data = (
                    payload
                    if isinstance(payload, bytes)
                    else json.dumps(payload).encode()
                )
                try:
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except BrokenPipeError:
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        return self

    def __exit__(self, *a):
        self.server.shutdown()

    def add(self, status, payload, headers=None, delay=0):
        self.responses.append((status, payload, headers or {}, delay))


def completion(message, finish="stop", model=MODEL):
    return dict(
        id="cmpl-1",
        model=model,
        choices=[dict(message=message, finish_reason=finish)],
        usage=dict(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
            completion_tokens_details=dict(reasoning_tokens=3),
        ),
    )


def provider(url, key="test-key-not-real", **env):
    return OpenAICompatibleProvider(
        load_config({"FIREWORKS_API_KEY": key, "UNLOCK_AI_BASE_URL": url, **env})
    )


def test_config_defaults_are_documented_model_and_medium_effort():
    c = load_config({})
    assert c.model == MODEL and c.base_url == "https://api.fireworks.ai/inference/v1"
    assert c.reasoning_effort == "medium" and not c.has_credentials
    assert (
        load_config({"UNLOCK_AI_REASONING_EFFORT": "high"}).reasoning_effort == "high"
    )
    with pytest.raises(ValueError):
        load_config({"UNLOCK_AI_REASONING_EFFORT": "max"})
    with pytest.raises(ValueError):
        load_config(
            {"UNLOCK_AI_PROVIDER": "together"}
        )  # model must be explicit for a fallback host
    secret = load_config({"FIREWORKS_API_KEY": "sk-should-not-leak"})
    assert "sk-should-not-leak" not in repr(
        secret
    ) and "sk-should-not-leak" not in json.dumps(secret.public())


def test_tool_call_round_trip_request_shape_and_usage():
    with Stub() as s:
        s.add(
            200,
            completion(
                tool_call_message(("call_1", "analyze_removal", {"a": 1})),
                finish="tool_calls",
            ),
            {"x-request-id": "req-9", "x-ratelimit-remaining-requests": "99"},
        )
        p = provider(s.url)
        tools = [
            dict(
                type="function",
                function=dict(name="analyze_removal", parameters=dict(type="object")),
            )
        ]
        turn = p.complete(
            [dict(role="user", content="hi")], tools, max_output_tokens=300, timeout_s=5
        )
        sent = s.requests[0]
    assert (
        sent["path"] == "/v1/chat/completions"
        and sent["auth"] == "Bearer test-key-not-real"
    )
    assert (
        sent["body"]["model"] == MODEL and sent["body"]["reasoning_effort"] == "medium"
    )
    assert sent["body"]["tools"] == tools and sent["body"]["max_tokens"] == 300
    assert turn.tool_calls[0].id == "call_1" and json.loads(
        turn.tool_calls[0].arguments
    ) == {"a": 1}
    assert turn.assistant_message["tool_calls"][0]["id"] == "call_1"
    assert (
        turn.usage.output_tokens == 7
        and turn.usage.reasoning_tokens == 3
        and turn.usage.raw["total_tokens"] == 18
    )
    assert turn.request_id == "req-9" and turn.rate_limits == {
        "x-ratelimit-remaining-requests": "99"
    }


@pytest.mark.parametrize(
    "status,body,headers,kind,retryable",
    [
        (401, {"error": "bad key"}, {}, "AUTHENTICATION", False),
        (404, {"error": "model not found"}, {}, "MODEL_UNAVAILABLE", False),
        (429, {"error": "slow down"}, {"Retry-After": "3"}, "RATE_LIMITED", True),
        (402, {"error": "credit exhausted"}, {}, "USAGE_LIMIT", False),
        (503, {"error": "overloaded"}, {}, "PROVIDER_UNAVAILABLE", True),
        (400, {"error": "bad request"}, {}, "BAD_REQUEST", False),
    ],
)
def test_http_errors_are_normalized(status, body, headers, kind, retryable):
    with Stub() as s:
        s.add(status, body, headers)
        with pytest.raises(ProviderError) as exc:
            provider(s.url).complete(
                [dict(role="user", content="x")], [], max_output_tokens=10, timeout_s=5
            )
    assert exc.value.kind == kind and exc.value.retryable == retryable
    if status == 429:
        assert exc.value.retry_after_s == 3.0
    assert "test-key-not-real" not in str(exc.value)


def test_timeout_malformed_empty_and_substituted_responses():
    with Stub() as s:
        s.add(200, completion(dict(role="assistant", content="late")), delay=1.5)
        with pytest.raises(ProviderError) as exc:
            provider(s.url).complete(
                [dict(role="user", content="x")],
                [],
                max_output_tokens=10,
                timeout_s=0.3,
            )
        assert exc.value.kind == "TIMEOUT" and exc.value.retryable
        time.sleep(1.3)
        s.add(200, b"not json")
        s.add(
            200,
            completion(
                dict(
                    role="assistant",
                    content=None,
                    tool_calls=[dict(id="c", function=dict(name=7))],
                )
            ),
        )
        s.add(200, completion(dict(role="assistant", content="   ")))
        s.add(
            200,
            completion(
                dict(role="assistant", content="hello"),
                model="accounts/other/models/someone-else",
            ),
        )
        p = provider(s.url)
        kinds = []
        for _ in range(4):
            with pytest.raises(ProviderError) as e:
                p.complete(
                    [dict(role="user", content="x")],
                    [],
                    max_output_tokens=10,
                    timeout_s=5,
                )
            kinds.append(e.value.kind)
    assert kinds == [
        "BAD_RESPONSE",
        "BAD_RESPONSE",
        "BAD_RESPONSE",
        "MODEL_UNAVAILABLE",
    ]


def test_missing_credentials_never_sends_a_request():
    with Stub() as s:
        p = OpenAICompatibleProvider(load_config({"UNLOCK_AI_BASE_URL": s.url}))
        with pytest.raises(ProviderError) as exc:
            p.complete(
                [dict(role="user", content="x")], [], max_output_tokens=10, timeout_s=5
            )
        assert exc.value.kind == "MISSING_CREDENTIALS" and not s.requests


def test_smoke_is_skipped_without_credentials_or_opt_in():
    assert run_smoke(load_config({}), env={})["status"] == "skipped"
    assert (
        run_smoke(load_config({"FIREWORKS_API_KEY": "k"}), env={})["status"]
        == "skipped"
    )


def test_smoke_sequence_against_stub_exercises_tool_correlation():
    with Stub() as s:
        s.add(200, completion(dict(role="assistant", content="ready")))
        s.add(
            200,
            completion(
                tool_call_message(("call_7", "add_integers", {"a": 1234, "b": 4321})),
                finish="tool_calls",
            ),
        )
        s.add(200, completion(dict(role="assistant", content="The sum is 5555.")))
        report = run_smoke(
            load_config({"FIREWORKS_API_KEY": "k", "UNLOCK_AI_BASE_URL": s.url}),
            env={"UNLOCK_AI_LIVE": "1"},
        )
        followup = s.requests[2]["body"]["messages"]
    assert report["status"] == "passed", report
    assert s.requests[1]["body"]["tool_choice"] == {
        "type": "function",
        "function": {"name": "add_integers"},
    }
    assert followup[-2]["tool_calls"][0]["id"] == "call_7"
    assert followup[-1] == {
        "role": "tool",
        "tool_call_id": "call_7",
        "content": json.dumps({"sum": 5555}),
    }


def test_fake_provider_is_never_live_and_parse_rejects_missing_ids():
    fake = FakeProvider([lambda m: dict(role="assistant", content="done")])
    assert fake.live is False
    assert fake.complete([], [], max_output_tokens=1, timeout_s=1).content == "done"
    with pytest.raises(ProviderError):
        parse_completion(
            dict(
                choices=[
                    dict(
                        message=dict(
                            tool_calls=[dict(function=dict(name="x", arguments="{}"))]
                        )
                    )
                ]
            ),
            provider="t",
            latency_ms=0,
        )
