from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.genai import types

from src.config import AppConfig, DEFAULT_FALLBACK_MODELS
from src.gemini_client import (
    GeminiService,
    build_thinking_config,
    format_gemini_error,
    is_retryable_gemini_error,
)


HIGH_DEMAND_503 = (
    "503 UNAVAILABLE. {'error': {'code': 503, "
    "'message': 'This model is currently experiencing high demand. "
    "Spikes in demand are usually temporary. Please try again later.', "
    "'status': 'UNAVAILABLE'}}"
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


def make_service(outcomes: list[object], fallbacks=("gemini-2.5-flash", "gemini-2.0-flash")) -> GeminiService:
    service = GeminiService.__new__(GeminiService)
    service.model_name = "gemini-3.8-flash"
    service.fallback_models = fallbacks
    service.on_model_used = None
    service.client = SimpleNamespace(models=FakeModels(outcomes))
    return service


def test_thinking_config_skipped_for_non_gemini3():
    assert build_thinking_config("gemini-2.5-flash", "low") is None


def test_thinking_config_is_valid_generate_content_input():
    thinking = build_thinking_config("gemini-3.8-flash", "low")
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
    service.model_name = "gemini-3.8-flash"
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


def test_high_demand_503_is_retryable():
    assert is_retryable_gemini_error(RuntimeError(HIGH_DEMAND_503))


def test_format_gemini_error_hides_raw_503():
    message = format_gemini_error(RuntimeError(HIGH_DEMAND_503))
    assert "用量過高" in message
    assert "503" not in message
    assert "UNAVAILABLE" not in message


def test_generate_text_retries_then_falls_back_on_503():
    service = make_service([
        RuntimeError(HIGH_DEMAND_503),
        RuntimeError(HIGH_DEMAND_503),
        RuntimeError(HIGH_DEMAND_503),
        SimpleNamespace(text="  開場白  "),
    ])
    with patch("src.gemini_client.time.sleep", return_value=None):
        text = service.generate_text("開始模擬", attempts=3)
    assert text == "開場白"
    assert service.model_name == "gemini-2.5-flash"
    assert service.client.models.calls == [
        "gemini-3.8-flash",
        "gemini-3.8-flash",
        "gemini-3.8-flash",
        "gemini-2.5-flash",
    ]


def test_generate_text_does_not_fallback_on_invalid_key():
    service = make_service([
        RuntimeError("400 INVALID_ARGUMENT. API key not valid."),
        SimpleNamespace(text="OK"),
    ])
    with pytest.raises(RuntimeError, match="Gemini 呼叫失敗") as caught:
        service.generate_text("hi", attempts=3)
    assert "API key not valid" in str(caught.value)
    assert service.client.models.calls == ["gemini-3.8-flash"]


def test_generate_text_reports_friendly_error_when_all_models_unavailable():
    service = make_service([
        RuntimeError(HIGH_DEMAND_503),
        RuntimeError(HIGH_DEMAND_503),
        RuntimeError(HIGH_DEMAND_503),
        RuntimeError(HIGH_DEMAND_503),
        RuntimeError(HIGH_DEMAND_503),
        RuntimeError(HIGH_DEMAND_503),
        RuntimeError(HIGH_DEMAND_503),
    ])
    with patch("src.gemini_client.time.sleep", return_value=None):
        with pytest.raises(RuntimeError, match="用量過高") as caught:
            service.generate_text("開始模擬", attempts=3)
    assert "UNAVAILABLE" not in str(caught.value)
    assert service.client.models.calls == [
        "gemini-3.8-flash",
        "gemini-3.8-flash",
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash",
    ]


def test_config_default_fallback_models():
    cfg = AppConfig.from_secrets({})
    assert cfg.model_name == "gemini-3.8-flash"
    assert cfg.fallback_models == DEFAULT_FALLBACK_MODELS
    cfg = AppConfig.from_secrets({"app": {"fallback_models": ["gemini-2.5-flash"]}})
    assert cfg.fallback_models == ("gemini-2.5-flash",)


def test_thinking_config_skipped_for_non_gemini3():
    assert build_thinking_config("gemini-2.5-flash", "low") is None


def test_thinking_config_is_valid_generate_content_input():
    thinking = build_thinking_config("gemini-3.8-flash", "low")
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
    service.model_name = "gemini-3.8-flash"
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
