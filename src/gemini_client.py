"""Gemini 呼叫封裝；學生 API Key 只留在記憶體，不寫入任何資料表。"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from google import genai
from google.genai import types


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
    if not str(model_name or "").startswith("gemini-3"):
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
    def __init__(self, api_key: str, model_name: str):
        if not api_key or not api_key.strip():
            raise ValueError("Gemini API Key 不可空白。")
        self.client = genai.Client(api_key=api_key.strip())
        self.model_name = model_name

    def _content_config(
        self,
        *,
        system_instruction: str | None,
        temperature: float,
        max_output_tokens: int,
        response_json: bool,
        thinking_level: str,
    ) -> Any:
        config_values: dict[str, Any] = dict(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json" if response_json else "text/plain",
        )
        thinking = build_thinking_config(self.model_name, thinking_level)
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
    ) -> str:
        config = self._content_config(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_json=response_json,
            thinking_level=thinking_level,
        )
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
                text = (response.text or "").strip()
                if not text:
                    raise RuntimeError("Gemini 回傳空白內容。")
                return text
            except Exception as exc:  # SDK 的錯誤型別會隨版本調整，統一在此重試
                last_error = exc
                message = str(exc).lower()
                retryable = any(token in message for token in ("429", "quota", "resource_exhausted", "timeout", "503"))
                if not retryable or attempt == attempts - 1:
                    break
                time.sleep(1.5 * (2**attempt))
        raise RuntimeError(f"Gemini 呼叫失敗：{last_error}") from last_error

    def validate_key(self) -> None:
        result = self.generate_text(
            "只回覆 OK。",
            system_instruction="這是 API 連線測試。",
            temperature=0.0,
            max_output_tokens=256,
            thinking_level="low",
            attempts=1,
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
