from google.genai import types

from src.gemini_client import GeminiService, build_thinking_config


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
