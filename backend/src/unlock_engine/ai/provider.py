"""Hosted model adapter. Controllers see normalized turns and errors, never SDK objects or raw HTTP."""

from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol, Sequence

from .config import ProviderConfig

ErrorKind = Literal[
    "MISSING_CREDENTIALS",
    "AUTHENTICATION",
    "MODEL_UNAVAILABLE",
    "RATE_LIMITED",
    "TIMEOUT",
    "NETWORK",
    "USAGE_LIMIT",
    "BAD_REQUEST",
    "BAD_RESPONSE",
    "PROVIDER_UNAVAILABLE",
    "CANCELLED",
]

MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class ProviderError(Exception):
    def __init__(
        self,
        kind: ErrorKind,
        message: str,
        *,
        retryable: bool = False,
        retry_after_s: float | None = None,
        http_status: int | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.retry_after_s = retry_after_s
        self.http_status = http_status

    def record(self) -> dict:
        return dict(
            kind=self.kind,
            message=str(self),
            retryable=self.retryable,
            retry_after_s=self.retry_after_s,
            http_status=self.http_status,
        )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text exactly as the provider returned it


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ModelTurn:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str | None
    usage: Usage
    latency_ms: float
    request_id: str | None
    model: str | None
    provider: str
    # The assistant message to append verbatim so tool_call ids stay correlated.
    assistant_message: dict
    rate_limits: dict = field(default_factory=dict)


class ModelProvider(Protocol):
    provider: str
    model: str
    reasoning_effort: str
    live: bool

    def complete(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict],
        *,
        max_output_tokens: int,
        timeout_s: float,
        tool_choice: str | dict = "auto",
        cancel_event=None,
    ) -> ModelTurn: ...


def _int(value):
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def parse_usage(raw) -> Usage:
    if not isinstance(raw, dict):
        return Usage()
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in raw and _int(raw[key]) is None:
            raise ProviderError("BAD_RESPONSE", "invalid provider token usage")
    prompt_details = raw.get("prompt_tokens_details") or {}
    completion_details = raw.get("completion_tokens_details") or {}
    return Usage(
        input_tokens=_int(raw.get("prompt_tokens")),
        output_tokens=_int(raw.get("completion_tokens")),
        total_tokens=_int(raw.get("total_tokens")),
        cached_input_tokens=_int(prompt_details.get("cached_tokens"))
        if isinstance(prompt_details, dict)
        else None,
        reasoning_tokens=_int(completion_details.get("reasoning_tokens"))
        if isinstance(completion_details, dict)
        else None,
        raw=raw,
    )


def parse_completion(
    data, *, provider: str, latency_ms: float, request_id=None, rate_limits=None
) -> ModelTurn:
    """Validate the OpenAI-compatible response shape; anything else is BAD_RESPONSE."""
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("choices"), list)
        or not data["choices"]
    ):
        raise ProviderError("BAD_RESPONSE", "response has no choices")
    choice = data["choices"][0]
    message = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(message, dict):
        raise ProviderError("BAD_RESPONSE", "choice has no message")
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise ProviderError("BAD_RESPONSE", "message content is not text")
    if message.get("role") != "assistant":
        raise ProviderError("BAD_RESPONSE", "response role must be assistant")
    if choice.get("finish_reason") not in ("stop", "tool_calls"):
        raise ProviderError(
            "BAD_RESPONSE", "response incomplete or unsupported finish reason"
        )
    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list) or len(raw_calls) > 64:
        raise ProviderError("BAD_RESPONSE", "tool_calls must be a bounded array")
    calls = []
    normalized = []
    seen = set()
    for raw in raw_calls:
        fn = raw.get("function") if isinstance(raw, dict) else None
        if (
            not isinstance(fn, dict)
            or raw.get("type") != "function"
            or not isinstance(raw.get("id"), str)
            or not 1 <= len(raw["id"]) <= 64
            or raw["id"] in seen
            or not isinstance(fn.get("name"), str)
            or not isinstance(fn.get("arguments", ""), str)
        ):
            raise ProviderError("BAD_RESPONSE", "malformed tool call structure")
        seen.add(raw["id"])
        calls.append(ToolCall(raw["id"], fn["name"], fn.get("arguments") or ""))
        normalized.append(
            dict(
                id=raw["id"],
                type="function",
                function=dict(name=fn["name"], arguments=fn.get("arguments") or ""),
            )
        )
    finish = choice.get("finish_reason")
    if not calls and not (content or "").strip():
        raise ProviderError(
            "BAD_RESPONSE",
            "empty response"
            if finish != "length"
            else "response truncated at the token limit",
            retryable=finish != "length",
        )
    assistant = dict(role="assistant", content=content)
    if normalized:
        assistant["tool_calls"] = normalized
    # reasoning_content (private reasoning) is deliberately not carried forward or stored.
    return ModelTurn(
        content=content,
        tool_calls=tuple(calls),
        finish_reason=finish,
        usage=parse_usage(data.get("usage")),
        latency_ms=latency_ms,
        request_id=request_id or data.get("id"),
        model=data.get("model"),
        provider=provider,
        assistant_message=assistant,
        rate_limits=rate_limits or {},
    )


def _retry_after(headers) -> float | None:
    value = headers.get("Retry-After") if headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


class OpenAICompatibleProvider:
    """Fireworks (and other explicitly configured hosts) via the documented chat completions API."""

    live = True

    def __init__(self, config: ProviderConfig, *, opener: Callable | None = None):
        self.config = config
        self.provider = config.provider
        self.model = config.model
        self.reasoning_effort = config.reasoning_effort
        self._open = opener or urllib.request.urlopen

    def _request(self, path: str, body: dict | None, timeout_s: float):
        if not self.config.has_credentials:
            raise ProviderError(
                "MISSING_CREDENTIALS",
                f"{self.config.api_key_env} is not set; the model stage cannot run",
            )
        request = urllib.request.Request(
            self.config.base_url + path,
            data=json.dumps(body, allow_nan=False).encode()
            if body is not None
            else None,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST" if body is not None else "GET",
        )
        started = time.monotonic()
        try:
            with self._open(request, timeout=timeout_s) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                headers = response.headers
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", "replace") if exc.fp else ""
            raise _http_error(exc.code, detail, exc.headers) from None
        except (socket.timeout, TimeoutError):
            raise ProviderError(
                "TIMEOUT", f"no response within {timeout_s:.0f} s", retryable=True
            ) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise ProviderError(
                    "TIMEOUT", f"no response within {timeout_s:.0f} s", retryable=True
                ) from None
            raise ProviderError(
                "NETWORK", "model connection interrupted", retryable=True
            ) from None
        latency = (time.monotonic() - started) * 1000
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderError("BAD_RESPONSE", "response exceeds size limit")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ProviderError(
                "BAD_RESPONSE", "response is not JSON", retryable=True
            ) from None
        limits = {
            k.lower(): v
            for k, v in (headers.items() if headers else [])
            if k.lower().startswith("x-ratelimit")
        }
        request_id = headers.get("x-request-id") if headers else None
        return data, latency, request_id, limits

    def complete(
        self,
        messages,
        tools,
        *,
        max_output_tokens,
        timeout_s,
        tool_choice="auto",
        cancel_event=None,
    ):
        body = dict(
            model=self.model,
            messages=list(messages),
            max_tokens=int(max_output_tokens),
        )
        if tools:
            body["tools"] = list(tools)
            body["tool_choice"] = tool_choice
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        data, latency, request_id, limits = self._request(
            "/chat/completions", body, timeout_s
        )
        returned_model = data.get("model") if isinstance(data, dict) else None
        if (
            returned_model
            and returned_model != self.model
            and not returned_model.endswith(self.model.split("/")[-1])
        ):
            # Never accept a silent model substitution.
            raise ProviderError(
                "MODEL_UNAVAILABLE",
                f"provider answered with a different model: {returned_model}",
            )
        return parse_completion(
            data,
            provider=self.provider,
            latency_ms=latency,
            request_id=request_id,
            rate_limits=limits,
        )


def _http_error(status: int, detail: str, headers) -> ProviderError:
    lowered = detail.lower()
    if status in (401, 403):
        return ProviderError(
            "AUTHENTICATION", f"authentication rejected ({status})", http_status=status
        )
    if (
        status == 402
        or "quota" in lowered
        or "billing" in lowered
        or "credit" in lowered
    ):
        return ProviderError(
            "USAGE_LIMIT",
            f"account usage or credit limit ({status})",
            http_status=status,
        )
    if status == 404 or ("model" in lowered and "not found" in lowered):
        return ProviderError(
            "MODEL_UNAVAILABLE",
            f"model unavailable ({status})",
            http_status=status,
        )
    if status == 429:
        return ProviderError(
            "RATE_LIMITED",
            "rate limited (429)",
            retryable=True,
            retry_after_s=_retry_after(headers),
            http_status=status,
        )
    if status in (408, 409, 500, 502, 503, 504):
        return ProviderError(
            "PROVIDER_UNAVAILABLE",
            f"provider error ({status})",
            retryable=True,
            retry_after_s=_retry_after(headers),
            http_status=status,
        )
    return ProviderError(
        "BAD_REQUEST", f"request rejected ({status})", http_status=status
    )


Script = Callable[[list[dict]], dict | ProviderError]


class FakeProvider:
    """Scripted, offline provider for tests. Its runs are never reported as live Muse results.

    Each script step receives the conversation so far and returns either an
    OpenAI-shaped assistant message dict (content and/or tool_calls) or a
    ProviderError to raise. Steps may react to real tool results.
    """

    provider = "fake"
    model = "fake-scripted-provider"
    live = False

    def __init__(
        self,
        steps: Sequence[Script],
        *,
        reasoning_effort="medium",
        usage_per_turn=(400, 120),
    ):
        self.steps = list(steps)
        self.reasoning_effort = reasoning_effort
        self.calls: list[dict] = []
        self.usage_per_turn = usage_per_turn

    def complete(
        self,
        messages,
        tools,
        *,
        max_output_tokens,
        timeout_s,
        tool_choice="auto",
        cancel_event=None,
    ):
        self.calls.append(
            dict(
                messages=[dict(m) for m in messages],
                tools=[t["function"]["name"] for t in tools],
            )
        )
        if not self.steps:
            raise ProviderError("BAD_RESPONSE", "fake script exhausted")
        result = self.steps.pop(0)(list(messages))
        if isinstance(result, ProviderError):
            raise result
        inp, out = self.usage_per_turn
        data = dict(
            id=f"fake-{len(self.calls)}",
            model=self.model,
            choices=[
                dict(
                    message=result,
                    finish_reason="tool_calls" if result.get("tool_calls") else "stop",
                )
            ],
            usage=dict(
                prompt_tokens=inp, completion_tokens=out, total_tokens=inp + out
            ),
        )
        return parse_completion(data, provider=self.provider, latency_ms=1.0)


def tool_call_message(
    *calls: tuple[str, str, dict | str], content: str | None = None
) -> dict:
    """Helper for scripts: build an assistant message with native tool calls."""
    return dict(
        role="assistant",
        content=content,
        tool_calls=[
            dict(
                id=cid,
                type="function",
                function=dict(
                    name=name,
                    arguments=args if isinstance(args, str) else json.dumps(args),
                ),
            )
            for cid, name, args in calls
        ],
    )


def build_provider(config: ProviderConfig) -> ModelProvider:
    if config.provider == "meta":
        from .meta import MetaProvider

        return MetaProvider(config)
    if config.provider == "mock":
        from .demo import scripted_agent

        return scripted_agent()
    return OpenAICompatibleProvider(config)
