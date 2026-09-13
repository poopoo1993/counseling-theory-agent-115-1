"""Gemini 呼叫封裝；學生 API Key 只留在記憶體，不寫入任何資料表。"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from google import genai
from google.genai import types


class GeminiService:
    def __init__(self, api_key: str, model_name: str):
        if not api_key or not api_key.strip():
            raise ValueError("Gemini API Key 不可空白。")
        self.client = genai.Client(api_key=api_key.strip())
        self.model_name = model_name

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
        config_values: dict[str, Any] = dict(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json" if response_json else "text/plain",
        )
        # Gemini 3 uses dynamic thinking and defaults to high.  Explicit low
        # thinking prevents short responses from spending the whole output
        # allowance before producing visible text.
        if self.model_name.startswith("gemini-3"):
            config_values["thinking_config"] = {"thinking_level": thinking_level}
        config = types.GenerateContentConfig(**config_values)
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
