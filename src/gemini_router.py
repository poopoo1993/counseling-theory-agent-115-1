"""Browser-side Gemini generateContent so Streamlit Cloud does not hold the Google connection."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

from .gemini_client import GeminiService, format_gemini_error

_COMPONENT_DIR = Path(__file__).resolve().parent / "frontend" / "gemini_router"
_gemini_router = components.declare_component("gemini_router", path=str(_COMPONENT_DIR))

_RESULTS_KEY = "_gemini_router_results"


class GeminiRouterPending(BaseException):
    """The iframe is calling Gemini; this script run should end without treating it as a model error."""


def _st() -> Any:
    import streamlit as st

    return st


def _results() -> dict[str, Any]:
    session_state = _st().session_state
    store = session_state.get(_RESULTS_KEY)
    if not isinstance(store, dict):
        store = {}
        session_state[_RESULTS_KEY] = store
    return store


def _unwrap(raw: Any, service: GeminiService) -> str:
    payload = dict(raw)
    error = str(payload.get("error") or "").strip()
    if error:
        raise RuntimeError(format_gemini_error(RuntimeError(error)))
    text = str(payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("Gemini 回傳空白內容。")
    model = str(payload.get("model") or service.model_name).strip()
    if model:
        service.model_name = model
        if service.on_model_used is not None:
            service.on_model_used(model)
    service.last_latency_ms = int(payload.get("latency_ms") or 0)
    return text


def generate_via_browser(
    service: GeminiService,
    prompt: str,
    *,
    call_id: str,
    system_instruction: str | None = None,
    temperature: float = 0.4,
    max_output_tokens: int = 1200,
    response_json: bool = False,
    thinking_level: str = "low",
    attempts: int = 3,
) -> str:
    st = _st()
    job_id = str(call_id or "").strip() or "gemini"
    cache = _results()
    if job_id in cache:
        return _unwrap(cache[job_id], service)

    job = {
        "request_id": job_id,
        "api_key": service.api_key,
        "models": service._models_to_try(),
        "prompt": prompt,
        "system_instruction": system_instruction or "",
        "temperature": float(temperature),
        "max_output_tokens": int(max_output_tokens),
        "response_json": bool(response_json),
        "thinking_level": thinking_level,
        "attempts": int(attempts),
    }
    spinner = getattr(st, "spinner", None)
    context = spinner("正在由這個瀏覽器呼叫 Gemini…") if callable(spinner) else nullcontext()
    with context:
        raw = _gemini_router(job=job, default=None, key=f"ct_gemini_{job_id}")
    if not isinstance(raw, dict) or str(raw.get("request_id") or "") != job_id:
        raise GeminiRouterPending()
    cache[job_id] = raw
    st.session_state[_RESULTS_KEY] = cache
    return _unwrap(raw, service)
