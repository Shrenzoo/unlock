"""Meta configuration is server-only, explicit and independent of the working directory."""

import json
import pytest
from unlock_engine.ai.config import load_config, load_environment, live_tests_enabled


def test_meta_defaults_and_secret_redaction():
    c = load_config({})
    assert (c.provider, c.model, c.base_url, c.api_key_env, c.reasoning_effort) == (
        "meta",
        "muse-spark-1.3",
        "https://api.meta.ai/v1",
        "MODEL_API_KEY",
        "medium",
    )
    assert not c.has_credentials
    c = load_config({"MODEL_API_KEY": "test-secret-not-a-credential"})
    assert c.has_credentials
    assert c.api_key not in repr(c) and c.api_key not in json.dumps(c.public())
    assert load_config({"META_REASONING_EFFORT": "high"}).reasoning_effort == "high"


def test_env_file_and_process_precedence(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text(
        "MODEL_API_KEY=file-secret\nAI_PROVIDER=meta\nMETA_REASONING_EFFORT=high\nRUN_META_LIVE_TESTS=1\n"
    )
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert load_config(env_file=p).api_key == "file-secret"
    monkeypatch.setenv("MODEL_API_KEY", "process-secret")
    assert load_config(env_file=p).api_key == "process-secret"
    assert live_tests_enabled(load_environment(p))
    assert not live_tests_enabled({})
    assert load_config({}).api_key is None


def test_alternatives_are_explicit_and_never_fallback():
    assert load_config({"FIREWORKS_API_KEY": "test-key"}).provider == "meta"
    assert not load_config({"FIREWORKS_API_KEY": "test-key"}).has_credentials
    assert load_config(
        {"AI_PROVIDER": "fireworks", "FIREWORKS_API_KEY": "test-key"}
    ).model.endswith("muse-spark-open")
    assert load_config({"AI_PROVIDER": "mock"}).provider == "mock"
    with pytest.raises(ValueError):
        load_config({"AI_PROVIDER": "together"})


@pytest.mark.parametrize(
    "env",
    [
        {"META_REASONING_EFFORT": "none"},
        {"UNLOCK_AI_REQUEST_TIMEOUT_S": "nan"},
        {"UNLOCK_AI_MAX_RETRIES": "9"},
        {"META_BASE_URL": "https://key@example.com/v1"},
        {"META_BASE_URL": "https://api.meta.ai/v1?key=secret"},
        {"META_BASE_URL": "http://remote.invalid/v1"},
        {"UNLOCK_AI_PRICE_PRESET": "prd_cited_2026_10_27"},
        {"UNLOCK_AI_TEMPERATURE": "0.2"},
    ],
)
def test_invalid_configuration_is_rejected_without_reflecting_secrets(env):
    with pytest.raises(ValueError) as e:
        load_config(env)
    assert "secret" not in str(e.value)
