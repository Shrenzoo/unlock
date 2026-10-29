"""Direct Meta Model API through the official SDK, with one attempt per call.

The controller owns retries. Async HTTP gives the synchronous domain interface
an absolute deadline and cancellation even while the server is sending bytes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time

import httpx
import openai

from .config import ProviderConfig
from .provider import MAX_RESPONSE_BYTES, ProviderError, _http_error, parse_completion


def validate_history(messages):
    pending = set()
    seen = set()
    for message in messages:
        role = message.get("role")
        if role == "tool":
            cid = message.get("tool_call_id")
            if cid not in pending:
                raise ProviderError(
                    "BAD_REQUEST", "tool result does not match an outstanding call"
                )
            pending.remove(cid)
        else:
            if pending:
                raise ProviderError(
                    "BAD_REQUEST",
                    "all tool results must precede the next conversation turn",
                )
            calls = message.get("tool_calls") or []
            if calls and role != "assistant":
                raise ProviderError(
                    "BAD_REQUEST", "only assistant messages may contain tool calls"
                )
            for call in calls:
                cid = call.get("id")
                if not isinstance(cid, str) or not 1 <= len(cid) <= 64 or cid in seen:
                    raise ProviderError(
                        "BAD_REQUEST",
                        "tool call IDs must be unique and 1–64 characters",
                    )
                seen.add(cid)
                pending.add(cid)
    if pending:
        raise ProviderError("BAD_REQUEST", "conversation has unanswered tool calls")


class MetaProvider:
    live = True
    provider = "meta"

    def __init__(self, config: ProviderConfig, *, transport=None):
        if config.provider != "meta":
            raise ValueError("MetaProvider requires AI_PROVIDER=meta")
        self.config = config
        self.model = config.model
        self.reasoning_effort = config.reasoning_effort
        self.transport = transport

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
        if not self.config.has_credentials:
            raise ProviderError(
                "MISSING_CREDENTIALS",
                "MODEL_API_KEY is not set in backend/.env or the server environment",
            )
        if tool_choice != "auto":
            raise ProviderError(
                "BAD_REQUEST", "Meta Chat Completions supports only tool_choice=auto"
            )
        if timeout_s <= 0 or (cancel_event and cancel_event.is_set()):
            raise ProviderError(
                "CANCELLED" if cancel_event and cancel_event.is_set() else "TIMEOUT",
                "model request stopped before sending",
            )
        validate_history(messages)
        body = dict(
            model=self.model,
            messages=list(messages),
            max_tokens=int(max_output_tokens),
            reasoning_effort=self.reasoning_effort,
        )
        if tools:
            body.update(tools=list(tools), tool_choice="auto")
        return asyncio.run(self._complete(body, timeout_s, cancel_event))

    async def _complete(self, body, timeout_s, cancel_event):
        started = time.monotonic()

        async def request():
            http = httpx.AsyncClient(
                transport=self.transport, timeout=timeout_s, follow_redirects=False
            )
            async with openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                max_retries=0,
                timeout=timeout_s,
                http_client=http,
            ) as client:
                async with client.chat.completions.with_streaming_response.create(
                    **body
                ) as response:
                    raw = bytearray()
                    async for part in response.iter_bytes():
                        raw.extend(part)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise ProviderError(
                                "BAD_RESPONSE", "response exceeds size limit"
                            )
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        raise ProviderError(
                            "BAD_RESPONSE", "provider returned invalid JSON"
                        ) from None
                    if not isinstance(data, dict) or data.get("model") != self.model:
                        raise ProviderError(
                            "MODEL_UNAVAILABLE",
                            "provider response does not identify the configured model",
                        )
                    return parse_completion(
                        data,
                        provider="meta",
                        latency_ms=(time.monotonic() - started) * 1000,
                        request_id=response.headers.get("x-request-id"),
                        rate_limits={
                            k: v
                            for k, v in response.headers.items()
                            if k.lower().startswith("x-ratelimit")
                        },
                    )

        task = asyncio.create_task(request())
        try:
            while not task.done():
                if cancel_event and cancel_event.is_set():
                    raise ProviderError("CANCELLED", "model request cancelled")
                remaining = timeout_s - (time.monotonic() - started)
                if remaining <= 0:
                    raise ProviderError(
                        "TIMEOUT",
                        "absolute model request deadline exceeded",
                        retryable=True,
                    )
                await asyncio.wait({task}, timeout=min(0.05, remaining))
            return task.result()
        except openai.APITimeoutError:
            raise ProviderError(
                "TIMEOUT", "model request timed out", retryable=True
            ) from None
        except openai.APIConnectionError:
            raise ProviderError(
                "NETWORK", "model connection interrupted", retryable=True
            ) from None
        except openai.APIStatusError as exc:
            # Raw provider errors can echo credentials or uploaded text. Never log them.
            detail = json.dumps(exc.body) if isinstance(exc.body, (dict, list)) else ""
            raise _http_error(exc.status_code, detail, exc.response.headers) from None
        except (openai.APIError, ValueError, TypeError):
            raise ProviderError(
                "BAD_RESPONSE", "unrecognized provider response"
            ) from None
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
