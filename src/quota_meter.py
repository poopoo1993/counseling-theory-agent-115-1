"""Browser localStorage sync for Gemini free-tier quota events."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import streamlit.components.v1 as components

from .gemini_quota import merge_events

_COMPONENT_DIR = Path(__file__).resolve().parent / "frontend" / "quota_sync"
_quota_sync = components.declare_component("quota_sync", path=str(_COMPONENT_DIR))


def sync_quota_events(events: Sequence[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    raw = _quota_sync(events=list(events or ()), default=None, key="ct_quota_sync")
    if not isinstance(raw, dict):
        return merge_events(events)
    payload = raw.get("events")
    if not isinstance(payload, list):
        return merge_events(events)
    return merge_events(events, payload)
