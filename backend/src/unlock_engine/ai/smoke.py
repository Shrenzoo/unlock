"""Live provider smoke test: three bounded requests, a harmless tool, no CAD work.

Runs only when credentials exist AND RUN_META_LIVE_TESTS=1 for Meta. Results are reported
check by check; a skipped or failed check is never reported as live success.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import ProviderConfig, live_tests_enabled, load_environment
from .provider import ProviderError, build_provider

ADD_TOOL = dict(
    type="function",
    function=dict(
        name="add_integers",
        description="Return the sum of two integers.",
        parameters=dict(
            type="object",
            properties=dict(a=dict(type="integer"), b=dict(type="integer")),
            required=["a", "b"],
            additionalProperties=False,
        ),
    ),
)


def run_smoke(config: ProviderConfig, *, env=None, provider=None) -> dict:
    env = load_environment() if env is None else env
    report = dict(
        started_at=datetime.now(timezone.utc).isoformat(),
        provider=config.public(),
        live_enabled=live_tests_enabled(env)
        if config.provider == "meta"
        else env.get("UNLOCK_AI_LIVE") == "1",
        checks=[],
        requests=[],
        status="not_run",
    )

    def check(name, ok, detail=""):
        report["checks"].append(
            dict(name=name, result="pass" if ok else "fail", detail=detail)
        )
        return ok

    if not config.has_credentials:
        report["status"] = "skipped"
        report["reason"] = (
            f"{config.api_key_env} not set; live integration remains unverified"
        )
        return report
    if not report["live_enabled"]:
        report["status"] = "skipped"
        report["reason"] = (
            "set RUN_META_LIVE_TESTS=1 to allow paid Meta tests (UNLOCK_AI_LIVE=1 for an explicitly selected alternate provider)"
        )
        return report

    provider = provider or build_provider(config)

    def call(messages, tools=(), tool_choice="auto"):
        turn = provider.complete(
            messages,
            tools,
            max_output_tokens=512,
            timeout_s=config.request_timeout_s,
            tool_choice=tool_choice,
        )
        report["requests"].append(
            dict(
                request_id=turn.request_id,
                model=turn.model,
                finish_reason=turn.finish_reason,
                latency_ms=round(turn.latency_ms, 1),
                usage=turn.usage.raw,
                rate_limits=turn.rate_limits,
            )
        )
        return turn

    try:
        # 1-4: authentication, model availability, ordinary message, response format
        turn = call([dict(role="user", content="Reply with the single word: ready")])
        check("authentication", True)
        check("model_available", bool(turn.model), f"model={turn.model}")
        check(
            "ordinary_message",
            bool((turn.content or "").strip()),
            (turn.content or "")[:60],
        )
        check("response_format", turn.finish_reason is not None)
        # 5-7: native function calling, parseable arguments
        messages = [
            dict(
                role="system",
                content="Use the add_integers tool for arithmetic. Do not compute sums yourself.",
            ),
            dict(role="user", content="What is 1234 plus 4321?"),
        ]
        turn = call(
            messages,
            [ADD_TOOL],
            tool_choice="auto",
        )
        if not check(
            "native_tool_call",
            len(turn.tool_calls) >= 1,
            f"{len(turn.tool_calls)} calls",
        ):
            raise ProviderError("BAD_RESPONSE", "no structured tool call returned")
        tc = turn.tool_calls[0]
        args = json.loads(tc.arguments)
        check(
            "tool_arguments_parse",
            isinstance(args.get("a"), int) and isinstance(args.get("b"), int),
            tc.arguments,
        )
        # 8-9: correlated tool result and continued conversation
        messages.append(turn.assistant_message)
        for extra in turn.tool_calls:
            a = json.loads(extra.arguments)
            if (
                extra.name != "add_integers"
                or not isinstance(a, dict)
                or set(a) != {"a", "b"}
                or any(type(v) is not int or abs(v) > 10000 for v in a.values())
            ):
                raise ProviderError(
                    "BAD_RESPONSE", "smoke tool name or arguments are unsupported"
                )
            messages.append(
                dict(
                    role="tool",
                    tool_call_id=extra.id,
                    content=json.dumps(dict(sum=a["a"] + a["b"])),
                )
            )
        turn = call(messages, [ADD_TOOL])
        check("tool_result_correlation", True, f"tool_call_id={tc.id}")
        check(
            "conversation_continues",
            "5555" in (turn.content or ""),
            (turn.content or "")[:80],
        )
        check("usage_reported", all(r["usage"] for r in report["requests"]))
    except ProviderError as exc:
        report["error"] = exc.record()
        check("provider_error", False, f"{exc.kind}: {exc}")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        check("tool_arguments_parse", False, f"{type(exc).__name__}: {exc}")
    report["status"] = (
        "passed"
        if report["checks"] and all(c["result"] == "pass" for c in report["checks"])
        else "failed"
    )
    requests = report["requests"]
    report["usage"] = dict(
        input_tokens=sum(r["usage"].get("prompt_tokens", 0) for r in requests),
        output_tokens=sum(r["usage"].get("completion_tokens", 0) for r in requests),
        source="provider_reported"
        if requests and all(r["usage"] for r in requests)
        else "incomplete",
    )
    report["cost"] = dict(
        estimated_usd=None, reason="no verified account price table configured"
    )
    if config.prices and report["usage"]["source"] == "provider_reported":
        from .controller import estimate_cost
        from .toolbox import Counters

        c = Counters(
            provider_requests=len(requests),
            usage_reported_turns=len(requests),
            input_tokens=report["usage"]["input_tokens"],
            output_tokens=report["usage"]["output_tokens"],
            cached_input_tokens=sum(
                (r["usage"].get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                for r in requests
            ),
        )
        report["cost"] = estimate_cost(c, config.prices)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report
