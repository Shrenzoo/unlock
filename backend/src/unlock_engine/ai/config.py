"""Server-only provider settings. Explicit environment wins over backend/.env."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values

ReasoningEffort = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
BACKEND_ROOT = Path(__file__).resolve().parents[3]
META = dict(
    provider="meta",
    base_url="https://api.meta.ai/v1",
    model="muse-spark-1.3",
    api_key_env="MODEL_API_KEY",
)
FIREWORKS = dict(
    provider="fireworks",
    base_url="https://api.fireworks.ai/inference/v1",
    model="accounts/fireworks/models/muse-spark-open",
    api_key_env="FIREWORKS_API_KEY",
)
TOGETHER = dict(
    provider="together",
    base_url="https://api.together.xyz/v1",
    model=None,
    api_key_env="TOGETHER_API_KEY",
)
MOCK = dict(
    provider="mock",
    base_url="mock://offline",
    model="fake-scripted-provider",
    api_key_env="",
)


@dataclass(frozen=True)
class PriceTable:
    """Operator-configured USD per million tokens with retrieval provenance."""

    input_per_mtok: float
    cached_input_per_mtok: float | None
    output_per_mtok: float
    source: str
    retrieved_at: str

    def __post_init__(self):
        for value in (
            self.input_per_mtok,
            self.cached_input_per_mtok,
            self.output_per_mtok,
        ):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError("prices must be finite and nonnegative")
        if not self.source or not self.retrieved_at:
            raise ValueError("price source and retrieval date are required")


PRD_CITED_FIREWORKS_PRICES = PriceTable(
    1.25, 0.15, 4.25, "Fireworks listing cited in PRD (not re-verified)", "2026-10-27"
)
# Public Standard-mode list price; used only to label smoke-test estimates.
META_LIST_PRICES = PriceTable(
    1.25,
    0.15,
    4.25,
    "https://dev.meta.ai/docs/pricing-rate-limits (muse-spark-1.3 Standard list price, not account-verified)",
    "2026-10-29",
)


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    model: str
    api_key_env: str
    reasoning_effort: ReasoningEffort = "medium"
    request_timeout_s: float = 45.0
    max_retries: int = 2
    temperature: float | None = None
    prices: PriceTable | None = None
    api_key: str | None = field(default=None, repr=False, compare=False)

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def public(self) -> dict:
        return dict(
            provider=self.provider,
            base_url=self.base_url,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            request_timeout_s=self.request_timeout_s,
            max_retries=self.max_retries,
            temperature=self.temperature,
            credentials="configured" if self.has_credentials else "missing",
            price_source=self.prices.source if self.prices else None,
        )


def load_environment(env_file: Path | None = None) -> dict:
    """Never search the current directory or mutate the process environment."""
    path = Path(env_file) if env_file is not None else BACKEND_ROOT / ".env"
    values = dotenv_values(path, interpolate=False) if path.is_file() else {}
    return {**{k: v for k, v in values.items() if v is not None}, **os.environ}


def live_tests_enabled(env: dict | None = None) -> bool:
    return (load_environment() if env is None else env).get(
        "RUN_META_LIVE_TESTS"
    ) == "1"


def load_config(
    env: dict | None = None, *, env_file: Path | None = None
) -> ProviderConfig:
    env = load_environment(env_file) if env is None else env
    name = env.get("AI_PROVIDER", env.get("UNLOCK_AI_PROVIDER", "meta")).lower()
    providers = {
        "meta": META,
        "fireworks": FIREWORKS,
        "together": TOGETHER,
        "mock": MOCK,
    }
    if name not in providers:
        raise ValueError("AI_PROVIDER must be meta, fireworks, together, or mock")
    base = providers[name]
    prefix = "META" if name == "meta" else "UNLOCK_AI"
    model = env.get(prefix + "_MODEL") or base["model"]
    if not model:
        raise ValueError(f"{prefix}_MODEL is required for provider {name}")
    effort = env.get(prefix + "_REASONING_EFFORT", "medium")
    allowed = (
        ("minimal", "low", "medium", "high", "xhigh", "max")
        if name == "meta"
        else ("low", "medium", "high", "xhigh")
    )
    if effort not in allowed:
        raise ValueError("unsupported reasoning effort for selected provider")
    url = env.get(prefix + "_BASE_URL", base["base_url"]).rstrip("/")
    parsed = urlsplit(url)
    if name != "mock" and (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or (
            parsed.scheme != "https"
            and not (
                parsed.scheme == "http"
                and parsed.hostname in ("127.0.0.1", "localhost", "::1")
            )
        )
    ):
        raise ValueError(
            "provider URL must be HTTPS without credentials or query parameters (HTTP loopback is allowed for offline tests)"
        )
    timeout = float(env.get("UNLOCK_AI_REQUEST_TIMEOUT_S", 45))
    retries = int(env.get("UNLOCK_AI_MAX_RETRIES", 2))
    if not math.isfinite(timeout) or not 0 < timeout <= 120 or not 0 <= retries <= 3:
        raise ValueError("request timeout must be in (0,120] and retries in [0,3]")
    prices = None
    if env.get("UNLOCK_AI_PRICE_PRESET"):
        if (
            name != "fireworks"
            or env["UNLOCK_AI_PRICE_PRESET"] != "prd_cited_2026_10_27"
        ):
            raise ValueError("historical price preset applies only to Fireworks")
        prices = PRD_CITED_FIREWORKS_PRICES
    elif env.get("UNLOCK_AI_PRICE_INPUT_PER_MTOK"):
        prices = PriceTable(
            float(env["UNLOCK_AI_PRICE_INPUT_PER_MTOK"]),
            float(env["UNLOCK_AI_PRICE_CACHED_INPUT_PER_MTOK"])
            if env.get("UNLOCK_AI_PRICE_CACHED_INPUT_PER_MTOK")
            else None,
            float(env["UNLOCK_AI_PRICE_OUTPUT_PER_MTOK"]),
            env.get("UNLOCK_AI_PRICE_SOURCE", ""),
            env.get("UNLOCK_AI_PRICE_RETRIEVED_AT", ""),
        )
    temperature = env.get("UNLOCK_AI_TEMPERATURE")
    if name == "meta" and temperature:
        raise ValueError(
            "Meta transport does not send temperature; remove UNLOCK_AI_TEMPERATURE"
        )
    return ProviderConfig(
        provider=name,
        base_url=url,
        model=model,
        api_key_env=base["api_key_env"],
        reasoning_effort=effort,
        request_timeout_s=timeout,
        max_retries=retries,
        temperature=float(temperature) if temperature else None,
        prices=prices,
        api_key=env.get(base["api_key_env"]) or None,
    )
