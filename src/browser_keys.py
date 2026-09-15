"""Remember Gemini API keys in this browser only. Never write them to SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent / "frontend" / "saved_api_keys"
_saved_api_keys = components.declare_component("saved_api_keys", path=str(_COMPONENT_DIR))


def mask_api_key(key: str) -> str:
    value = str(key or "").strip()
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}…{value[-4:]}"


def render_saved_api_keys(*, save_key: str = "", hide: bool = False) -> dict[str, Any] | None:
    result = _saved_api_keys(
        save_key=save_key or "",
        hide=bool(hide),
        default=None,
        key="saved_gemini_api_keys",
    )
    if isinstance(result, dict):
        return result
    return None
