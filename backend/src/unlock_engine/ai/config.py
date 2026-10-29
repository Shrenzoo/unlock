"""Provider configuration. Every value comes from the server environment; nothing is hardcoded secret."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

ReasoningEffort = Literal["low", "medium", "high", "xhigh"]

# Documented in PRD §15 / Meta deployment guide; overridable, never silently replaced.
FIREWORKS = dict(
    provider="fireworks",
    base_url="https://api.fireworks.ai/inference/v1",
    model="accounts/fireworks/models/muse-spark-open",
    api_key_env="FIREWORKS_API_KEY",
)
# Same model at another documented host. Usable only when explicitly selected
# and after its own tool-calling smoke test passes; the model string must be set.
TOGETHER = dict(
    provider="together",
    base_url="https://api.together.xyz/v1",
    model=None,
    api_key_env="TOGETHER_API_KEY",
)


@dataclass(frozen=True)
class PriceTable:
    """USD per million tokens. Provenance is mandatory: prices change."""

    input_per_mtok: float
    cached_input_per_mtok: float | None
    output_per_mtok: float
    source: str
    retrieved_at: str


# Figures cited in PRD §15 [S26-S27] on 2026-10-27. Opt-in only, and labelled as
# unverified against the account: they must be rechecked before cost claims.
PRD_CITED_FIREWORKS_PRICES = PriceTable(
    input_per_mtok=1.25,
    cached_input_per_mtok=0.15,
    output_per_mtok=4.25,
    source="Fireworks public listing as cited in UNLOCK PRD §15 (not re-verified)",
    retrieved_at="2026-10-27",
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
    # Never part of repr, logs or reports.
    api_key: str | None = field(default=None, repr=False, compare=False)

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key)

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


def load_config(env: dict | None = None) -> ProviderConfig:
    """Read UNLOCK_AI_* variables. xhigh effort must be requested explicitly."""
    env = os.environ if env is None else env
    name = env.get("UNLOCK_AI_PROVIDER", "fireworks")
    if name not in ("fireworks", "together"):
        raise ValueError(f"unsupported provider {name!r}")
    base = dict(FIREWORKS if name == "fireworks" else TOGETHER)
    model = env.get("UNLOCK_AI_MODEL") or base["model"]
    if not model:
        raise ValueError(f"UNLOCK_AI_MODEL is required for provider {name}")
    effort = env.get("UNLOCK_AI_REASONING_EFFORT", "medium")
    if effort not in ("low", "medium", "high", "xhigh"):
        raise ValueError(f"unsupported reasoning effort {effort!r}")
    prices = None
    if env.get("UNLOCK_AI_PRICE_PRESET") == "prd_cited_2026_10_27":
        prices = PRD_CITED_FIREWORKS_PRICES
    elif env.get("UNLOCK_AI_PRICE_INPUT_PER_MTOK"):
        prices = PriceTable(
            input_per_mtok=float(env["UNLOCK_AI_PRICE_INPUT_PER_MTOK"]),
            cached_input_per_mtok=float(env["UNLOCK_AI_PRICE_CACHED_INPUT_PER_MTOK"])
            if env.get("UNLOCK_AI_PRICE_CACHED_INPUT_PER_MTOK")
            else None,
            output_per_mtok=float(env["UNLOCK_AI_PRICE_OUTPUT_PER_MTOK"]),
            source=env.get("UNLOCK_AI_PRICE_SOURCE", "operator supplied"),
            retrieved_at=env.get("UNLOCK_AI_PRICE_RETRIEVED_AT", "unspecified"),
        )
    temperature = env.get("UNLOCK_AI_TEMPERATURE")
    return ProviderConfig(
        provider=name,
        base_url=env.get("UNLOCK_AI_BASE_URL", base["base_url"]).rstrip("/"),
        model=model,
        api_key_env=base["api_key_env"],
        reasoning_effort=effort,
        request_timeout_s=float(env.get("UNLOCK_AI_REQUEST_TIMEOUT_S", 45)),
        max_retries=int(env.get("UNLOCK_AI_MAX_RETRIES", 2)),
        temperature=float(temperature) if temperature else None,
        prices=prices,
        api_key=env.get(base["api_key_env"]) or None,
    )
