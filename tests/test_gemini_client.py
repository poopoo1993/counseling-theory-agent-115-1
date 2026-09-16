from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.genai import types

from src.config import AppConfig
from src.gemini_client import (
    DEFAULT_FALLBACK_MODELS,
    DEFAULT_MODEL_NAME,
    GeminiService,
    build_thinking_config,
    canonical_model_name,
    format_gemini_error,
    is_retryable_gemini_error,
    sanitize_fallback_models,
    should_try_next_model,
)


HIGH_DEMAND_503 = (
    "503 UNAVAILABLE. {'error': {'code': 503, "
    "'message': 'This model is currently experiencing high demand. "
    "Spikes in demand are usually temporary. Please try again later.', "
    "'status': 'UNAVAILABLE'}}"
)
RETIRED_404 = (
    "404 NOT_FOUND. {'error': {'code': 404, "
    "'message': 'This model models/gemini-2.0-flash is no longer available. "
    "Please update your code to use models/gemini-3.6-flash.', "
    "'status': 'NOT_FOUND'}}"
)


class FakeModels:
    def __init__(self, outcomes: list[object]):
        self.outcomes = list(outcomes)
        self.calls: list[str] = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if not self.outcomes:
            raise AssertionError("unexpected extra Gemini call")
        result = self.outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_service(
    outcomes: list[object],
    model_name: str = "gemini-flash-latest",
    fallbacks: tuple[str, ...] = (),
) -> GeminiService:
    service = GeminiService.__new__(GeminiService)
    service.model_name = model_name
    service.fallback_models = fallbacks
    service.on_model_used = None
    service.client = SimpleNamespace(models=FakeModels(outcomes))
    return service


def test_thinking_config_skipped_for_non_gemini3():
    assert build_thinking_config("gemini-2.5-flash", "low") is None


def test_thinking_config_is_valid_generate_content_input():
    thinking = build_thinking_config("gemini-flash-latest", "low")
    config_values = {
        "system_instruction": "這是 API 連線測試。",
        "temperature": 0.0,
        "max_output_tokens": 256,
        "response_mime_type": "text/plain",
    }
    if thinking is not None:
        config_values["thinking_config"] = thinking
        dumped = thinking.model_dump(exclude_none=True) if hasattr(thinking, "model_dump") else {}
        fields = set(getattr(types.ThinkingConfig, "model_fields", {}) or {})
        assert "thinking_level" not in dumped or "thinking_level" in fields
    types.GenerateContentConfig(**config_values)


def test_content_config_does_not_pass_forbidden_thinking_level():
    service = GeminiService.__new__(GeminiService)
    service.model_name = "gemini-flash-latest"
    config = service._content_config(
        system_instruction="test",
        temperature=0.0,
        max_output_tokens=256,
        response_json=False,
        thinking_level="low",
    )
    thinking = getattr(config, "thinking_config", None)
    if thinking is None:
        return
    dumped = thinking.model_dump(exclude_none=True) if hasattr(thinking, "model_dump") else {}
    fields = set(getattr(types.ThinkingConfig, "model_fields", {}) or {})
    for key in dumped:
        assert key in fields


def test_high_demand_503_is_retryable_but_does_not_switch_models():
    assert is_retryable_gemini_error(RuntimeError(HIGH_DEMAND_503))
    assert not should_try_next_model(RuntimeError(HIGH_DEMAND_503))


def test_retired_404_switches_models():
    assert should_try_next_model(RuntimeError(RETIRED_404))
    assert "已停用" in format_gemini_error(RuntimeError(RETIRED_404))
    assert "gemini-2.0-flash" not in format_gemini_error(RuntimeError(RETIRED_404))


def test_format_gemini_error_hides_raw_503():
    message = format_gemini_error(RuntimeError(HIGH_DEMAND_503))
    assert "用量過高" in message
    assert "503" not in message
    assert "UNAVAILABLE" not in message


def test_retired_model_is_rewritten_to_flash_latest():
    assert canonical_model_name("gemini-2.0-flash") == "gemini-flash-latest"
    assert canonical_model_name("models/gemini-2.0-flash") == "gemini-flash-latest"
    assert sanitize_fallback_models(
        ("gemini-2.5-flash", "gemini-2.0-flash"),
        "gemini-flash-latest",
    ) == ("gemini-2.5-flash",)


def test_generate_text_retries_503_on_same_model_only():
    service = make_service(
        [
            RuntimeError(HIGH_DEMAND_503),
            RuntimeError(HIGH_DEMAND_503),
            SimpleNamespace(text="  開場白  "),
        ],
        fallbacks=("gemini-3.6-flash",),
    )
    with patch("src.gemini_client.time.sleep", return_value=None):
        text = service.generate_text("開始模擬", attempts=3)
    assert text == "開場白"
    assert service.model_name == "gemini-flash-latest"
    assert service.client.models.calls == [
        "gemini-flash-latest",
        "gemini-flash-latest",
        "gemini-flash-latest",
    ]


def test_generate_text_falls_back_only_when_model_is_gone():
    service = make_service(
        [RuntimeError(RETIRED_404), SimpleNamespace(text="OK")],
        fallbacks=("gemini-3.6-flash",),
    )
    text = service.generate_text("開始模擬", attempts=3)
    assert text == "OK"
    assert service.model_name == "gemini-3.6-flash"
    assert service.client.models.calls == ["gemini-flash-latest", "gemini-3.6-flash"]


def test_generate_text_does_not_fallback_on_invalid_key():
    service = make_service(
        [
            RuntimeError("400 INVALID_ARGUMENT. API key not valid."),
            SimpleNamespace(text="OK"),
        ],
        fallbacks=("gemini-3.6-flash",),
    )
    with pytest.raises(RuntimeError, match="Gemini 呼叫失敗") as caught:
        service.generate_text("hi", attempts=3)
    assert "API key not valid" in str(caught.value)
    assert service.client.models.calls == ["gemini-flash-latest"]


def test_generate_text_reports_friendly_error_when_same_model_unavailable():
    service = make_service(
        [
            RuntimeError(HIGH_DEMAND_503),
            RuntimeError(HIGH_DEMAND_503),
            RuntimeError(HIGH_DEMAND_503),
        ],
        fallbacks=("gemini-3.6-flash",),
    )
    with patch("src.gemini_client.time.sleep", return_value=None):
        with pytest.raises(RuntimeError, match="用量過高") as caught:
            service.generate_text("開始模擬", attempts=3)
    assert "UNAVAILABLE" not in str(caught.value)
    assert service.client.models.calls == [
        "gemini-flash-latest",
        "gemini-flash-latest",
        "gemini-flash-latest",
    ]


def test_config_defaults_to_single_latest_flash_model():
    from src.gemini_quota import DEFAULT_FREE_RPD, DEFAULT_FREE_RPM, DEFAULT_FREE_TPM

    cfg = AppConfig.from_secrets({})
    assert cfg.model_name == DEFAULT_MODEL_NAME
    assert cfg.fallback_models == DEFAULT_FALLBACK_MODELS
    assert cfg.gemini_free_rpm == DEFAULT_FREE_RPM
    assert cfg.gemini_free_rpd == DEFAULT_FREE_RPD
    assert cfg.gemini_free_tpm == DEFAULT_FREE_TPM
    cfg = AppConfig.from_secrets({
        "app": {
            "model_name": "gemini-2.0-flash",
            "fallback_models": ["gemini-2.5-flash", "gemini-2.0-flash"],
        }
    })
    assert cfg.model_name == "gemini-flash-latest"
    assert cfg.fallback_models == ("gemini-2.5-flash",)
    cfg = AppConfig.from_secrets({"app": {"model_name": "gemini-3.8-flash"}})
    assert cfg.model_name == "gemini-flash-latest"
