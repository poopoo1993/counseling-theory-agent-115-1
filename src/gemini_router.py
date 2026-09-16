"""Browser-side Gemini generateContent so Streamlit Cloud does not hold the Google connection."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import streamlit.components.v1 as components

from .gemini_client import GeminiService, format_gemini_error
from .gemini_quota import EVENTS_KEY, estimate_prompt_tokens, record_event

_COMPONENT_DIR = Path(__file__).resolve().parent / "frontend" / "gemini_router"
_gemini_router = components.declare_component("gemini_router", path=str(_COMPONENT_DIR))

_RESULTS_KEY = "_gemini_router_results"
_COMPONENT_KEY = "ct_gemini_router"


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


def _record_quota(payload: Mapping[str, Any], job: Mapping[str, Any]) -> None:
    if str(payload.get("error") or "").strip():
        return
    request_id = str(payload.get("request_id") or job.get("request_id") or "").strip()
    if not request_id:
        return
    try:
        tokens = int(payload.get("prompt_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    if tokens <= 0:
        tokens = estimate_prompt_tokens(str(job.get("prompt") or ""), str(job.get("system_instruction") or ""))
    session_state = _st().session_state
    session_state[EVENTS_KEY] = record_event(
        session_state.get(EVENTS_KEY),
        event_id=request_id,
        prompt_tokens=tokens,
        ts=time.time(),
    )


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


def _normalize_results(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    items = raw.get("results")
    if isinstance(items, list):
        return {
            str(item.get("request_id") or ""): item
            for item in items
            if isinstance(item, dict) and item.get("request_id")
        }
    if raw.get("request_id"):
        return {str(raw["request_id"]): raw}
    if isinstance(items, dict):
        return {
            str(key): dict(value)
            for key, value in items.items()
            if isinstance(value, dict)
        }
    return {}


def keep_gemini_router_alive() -> None:
    st = _st()
    if st.session_state.get("_gemini_router_mounted"):
        return
    st.session_state["_gemini_router_mounted"] = True
    _gemini_router(jobs=[], default=None, key=_COMPONENT_KEY)


def _render_router(jobs: Sequence[Mapping[str, Any]]) -> Any:
    st = _st()
    if st.session_state.get("_gemini_router_mounted"):
        raise GeminiRouterPending()
    st.session_state["_gemini_router_mounted"] = True
    return _gemini_router(jobs=list(jobs), default=None, key=_COMPONENT_KEY)


def run_browser_jobs(service: GeminiService, jobs: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    st = _st()
    prepared: list[dict[str, Any]] = []
    for job in jobs:
        request_id = str(job.get("request_id") or job.get("call_id") or "").strip()
        if not request_id:
            continue
        prepared.append({
            "request_id": request_id,
            "api_key": service.api_key,
            "models": service._models_to_try(),
            "prompt": str(job.get("prompt") or ""),
            "system_instruction": str(job.get("system_instruction") or ""),
            "temperature": float(job.get("temperature", 0.4)),
            "max_output_tokens": int(job.get("max_output_tokens", 1200)),
            "response_json": bool(job.get("response_json", False)),
            "thinking_level": str(job.get("thinking_level") or "low"),
            "attempts": int(job.get("attempts") or 2),
        })
    if not prepared:
        return {}
    cache = _results()
    pending = [job for job in prepared if job["request_id"] not in cache]
    if pending:
        raw = _render_router(pending)
        received = _normalize_results(raw)
        missing = [job["request_id"] for job in pending if job["request_id"] not in received]
        if missing:
            raise GeminiRouterPending()
        for request_id, payload in received.items():
            cache[request_id] = payload
            job = next((item for item in pending if item["request_id"] == request_id), {"request_id": request_id})
            _record_quota(payload, job)
        st.session_state[_RESULTS_KEY] = cache
    return {job["request_id"]: _unwrap(cache[job["request_id"]], service) for job in prepared}


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
    attempts: int = 2,
) -> str:
    job_id = str(call_id or "").strip() or "gemini"
    texts = run_browser_jobs(service, [{
        "request_id": job_id,
        "prompt": prompt,
        "system_instruction": system_instruction or "",
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "response_json": response_json,
        "thinking_level": thinking_level,
        "attempts": attempts,
    }])
    return texts[job_id]
