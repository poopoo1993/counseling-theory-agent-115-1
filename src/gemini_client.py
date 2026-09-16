"""Gemini 呼叫封裝；學生 API Key 只留在記憶體，不寫入任何資料表。"""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable, Sequence
from typing import Any

from google import genai
from google.genai import types

RETRYABLE_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "quota",
    "resource_exhausted",
    "timeout",
    "unavailable",
    "high demand",
    "overloaded",
    "try again later",
    "temporarily unavailable",
    "空白內容",
)
# 過載時只重試同一個模型，避免一次連打多個模型 ID。
# 只有模型已下架／找不到時才改走備援。
NEXT_MODEL_MARKERS = (
    "404",
    "not found",
    "not_found",
    "no longer available",
    "not supported",
)
DEFAULT_MODEL_NAME = "gemini-flash-latest"
DEFAULT_FALLBACK_MODELS: tuple[str, ...] = ()
CONGESTED_ALIASES = {
    "gemini-3.8-flash": DEFAULT_MODEL_NAME,
}
RETIRED_MODELS = frozenset(
    {
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-lite",
        "gemini-2.0-pro-exp",
    }
)


def is_retryable_gemini_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(token in message for token in RETRYABLE_MARKERS)


def should_try_next_model(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(token in message for token in NEXT_MODEL_MARKERS)


def _strip_models_prefix(name: str) -> str:
    value = str(name or "").strip()
    if value.lower().startswith("models/"):
        return value[7:]
    return value


def is_retired_model(name: str) -> bool:
    return _strip_models_prefix(name).lower() in RETIRED_MODELS


def canonical_model_name(name: str, default: str = DEFAULT_MODEL_NAME) -> str:
    value = _strip_models_prefix(name)
    if not value or is_retired_model(value):
        return default
    return CONGESTED_ALIASES.get(value, value)


def sanitize_fallback_models(models: Sequence[str], primary: str) -> tuple[str, ...]:
    primary_name = canonical_model_name(primary)
    ordered: list[str] = []
    for item in models:
        value = _strip_models_prefix(item)
        if not value or is_retired_model(value) or value == primary_name or value in ordered:
            continue
        ordered.append(value)
    return tuple(ordered)


def uses_gemini3_thinking(model_name: str) -> bool:
    name = _strip_models_prefix(model_name).lower()
    return name.startswith("gemini-3") or name in {
        "gemini-flash-latest",
        "gemini-pro-latest",
        "gemini-flash-lite-latest",
    }


def format_gemini_error(exc: BaseException) -> str:
    message = str(exc).lower()
    if any(token in message for token in ("503", "unavailable", "high demand", "overloaded")):
        return "Gemini 目前用量過高，暫時無法回應。這通常很快會恢復，請稍候再試一次。"
    if any(token in message for token in ("429", "quota", "resource_exhausted")):
        return "Gemini API 用量或配額已達上限。請稍候再試，或到 Google AI Studio 檢查用量。"
    if any(token in message for token in ("404", "not_found", "no longer available", "not found")):
        return "指定的 Gemini 模型已停用或找不到。請改用最新 Flash 模型後再試。"
    return f"Gemini 呼叫失敗：{exc}"


def _backoff_seconds(attempt: int) -> float:
    base = min(12.0, 1.5 * (2**attempt))
    return base * (0.75 + 0.5 * random.random())


def _thinking_field_names() -> set[str]:
    thinking_cls = getattr(types, "ThinkingConfig", None)
    if thinking_cls is None:
        return set()
    fields = getattr(thinking_cls, "model_fields", None) or getattr(thinking_cls, "__fields__", {}) or {}
    return set(fields)


def build_thinking_config(model_name: str, thinking_level: str = "low") -> Any | None:
    """Gemini 3 needs low thinking so short replies are not empty.

    Installed google-genai versions disagree on the field name:
    newer SDKs use thinking_level; older ones only accept thinking_budget.
    """
    if not uses_gemini3_thinking(model_name):
        return None
    names = _thinking_field_names()
    thinking_cls = getattr(types, "ThinkingConfig", None)
    kwargs: dict[str, Any] = {}
    if "thinking_level" in names:
        kwargs["thinking_level"] = thinking_level
    elif "thinking_budget" in names:
        kwargs["thinking_budget"] = 0 if str(thinking_level).lower() == "low" else 1024
    if thinking_cls is None or not kwargs:
        return None
    try:
        return thinking_cls(**kwargs)
    except Exception:
        if "thinking_budget" in names:
            try:
                return thinking_cls(thinking_budget=0 if str(thinking_level).lower() == "low" else 1024)
            except Exception:
                return None
        return None


class GeminiService:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        fallback_models: Sequence[str] = (),
        on_model_used: Callable[[str], None] | None = None,
        use_browser_router: bool = False,
    ):
        if not api_key or not api_key.strip():
            raise ValueError("Gemini API Key 不可空白。")
        self.client = genai.Client(api_key=api_key.strip())
        self.api_key = api_key.strip()
        self.model_name = canonical_model_name(model_name)
        self.fallback_models = sanitize_fallback_models(fallback_models, self.model_name)
        self.on_model_used = on_model_used
        self.use_browser_router = bool(use_browser_router)
        self.last_latency_ms = 0

    def _models_to_try(self) -> list[str]:
        ordered: list[str] = []
        for name in (self.model_name, *self.fallback_models):
            value = str(name or "").strip()
            if value and value not in ordered:
                ordered.append(value)
        return ordered or [self.model_name]

    def _content_config(
        self,
        *,
        system_instruction: str | None,
        temperature: float,
        max_output_tokens: int,
        response_json: bool,
        thinking_level: str,
        model_name: str | None = None,
    ) -> Any:
        config_values: dict[str, Any] = dict(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json" if response_json else "text/plain",
        )
        thinking = build_thinking_config(model_name or self.model_name, thinking_level)
        if thinking is not None:
            config_values["thinking_config"] = thinking
        try:
            return types.GenerateContentConfig(**config_values)
        except Exception:
            config_values.pop("thinking_config", None)
            return types.GenerateContentConfig(**config_values)

    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        temperature: float = 0.4,
        max_output_tokens: int = 1200,
        response_json: bool = False,
        thinking_level: str = "low",
        attempts: int = 3,
        call_id: str | None = None,
    ) -> str:
        if getattr(self, "use_browser_router", False):
            from .gemini_router import generate_via_browser
            return generate_via_browser(
                self,
                prompt,
                call_id=str(call_id or "gemini"),
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_json=response_json,
                thinking_level=thinking_level,
                attempts=attempts,
            )
        started = time.perf_counter()
        last_error: Exception | None = None
        models = self._models_to_try()
        for model_index, model_name in enumerate(models):
            config = self._content_config(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_json=response_json,
                thinking_level=thinking_level,
                model_name=model_name,
            )
            model_attempts = attempts if model_index == 0 else min(2, attempts)
            for attempt in range(model_attempts):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    text = (response.text or "").strip()
                    if not text:
                        raise RuntimeError("Gemini 回傳空白內容。")
                    self.model_name = model_name
                    if self.on_model_used is not None:
                        self.on_model_used(model_name)
                    self.last_latency_ms = int((time.perf_counter() - started) * 1000)
                    return text
                except Exception as exc:  # SDK 的錯誤型別會隨版本調整，統一在此重試
                    last_error = exc
                    last_for_model = attempt == model_attempts - 1
                    can_retry_same = is_retryable_gemini_error(exc) and not last_for_model
                    can_switch = should_try_next_model(exc) and model_index < len(models) - 1
                    if can_retry_same:
                        time.sleep(_backoff_seconds(attempt))
                        continue
                    if can_switch:
                        break
                    raise RuntimeError(format_gemini_error(exc)) from exc
        raise RuntimeError(format_gemini_error(last_error or RuntimeError("未知錯誤"))) from last_error

    def validate_key(self, call_id: str | None = None) -> None:
        result = self.generate_text(
            "只回覆 OK。",
            system_instruction="這是 API 連線測試。",
            temperature=0.0,
            max_output_tokens=256,
            thinking_level="low",
            attempts=3,
            call_id=call_id or "validate",
        )
        if "OK" not in result.upper():
            raise RuntimeError("API Key 可呼叫，但模型未完成預期的連線測試。")


def parse_json_response(raw: str) -> dict[str, Any]:
    value = (raw or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("模型輸出不是 JSON 物件。")
    return parsed
