"""Gemini 免費方案 RPM / RPD / TPM 剩餘量。

官方 rate-limits 頁已改為「到 AI Studio 查看」，不再保證固定數字。
此處採用 Google 最後公開的 Gemini 2.5 Flash 免費額度：
10 RPM、250 RPD、250,000 TPM（輸入權杖）。RPD 以太平洋時間午夜重置。
三個維度同時計，任一項額滿即 429。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
MINUTE_SECONDS = 60
EVENT_TTL_SECONDS = 48 * 3600
EVENTS_KEY = "_gemini_quota_events"

# Gemini 2.5 Flash free tier (last published table; TPM = input tokens).
DEFAULT_FREE_RPM = 10
DEFAULT_FREE_RPD = 250
DEFAULT_FREE_TPM = 250_000

STORAGE_KEY = "counseling_theory_gemini_quota"


def estimate_prompt_tokens(*parts: str) -> int:
    text = "".join(str(part or "") for part in parts)
    stripped = text.strip()
    return max(1, len(stripped)) if stripped else 1


def pacific_day(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), PACIFIC).date().isoformat()


def _as_event(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    event_id = str(raw.get("id") or "").strip()
    try:
        ts = float(raw.get("ts") or 0)
        tokens = int(raw.get("prompt_tokens") or 0)
    except (TypeError, ValueError):
        return None
    if not event_id or ts <= 0 or tokens < 0:
        return None
    return {"id": event_id, "ts": ts, "prompt_tokens": max(0, tokens)}


def merge_events(*groups: Sequence[Mapping[str, Any]] | None, now: float | None = None) -> list[dict[str, Any]]:
    cutoff = float(now or 0) - EVENT_TTL_SECONDS if now else 0
    by_id: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group or ():
            if not isinstance(raw, Mapping):
                continue
            event = _as_event(raw)
            if event is None:
                continue
            if cutoff and event["ts"] < cutoff:
                continue
            by_id[event["id"]] = event
    return sorted(by_id.values(), key=lambda item: (item["ts"], item["id"]))


def record_event(
    events: Sequence[Mapping[str, Any]] | None,
    *,
    event_id: str,
    prompt_tokens: int,
    ts: float,
) -> list[dict[str, Any]]:
    return merge_events(
        events,
        [{"id": str(event_id), "ts": ts, "prompt_tokens": int(prompt_tokens)}],
        now=ts,
    )


def format_remaining(value: int) -> str:
    amount = max(0, int(value))
    if amount >= 10_000:
        return f"{amount / 1000:.0f}K"
    return f"{amount:,}"


def snapshot(
    events: Sequence[Mapping[str, Any]] | None,
    *,
    now: float,
    rpm_limit: int = DEFAULT_FREE_RPM,
    rpd_limit: int = DEFAULT_FREE_RPD,
    tpm_limit: int = DEFAULT_FREE_TPM,
) -> dict[str, Any]:
    rpm_cap = max(1, int(rpm_limit))
    rpd_cap = max(1, int(rpd_limit))
    tpm_cap = max(1, int(tpm_limit))
    minute_start = float(now) - MINUTE_SECONDS
    today = pacific_day(now)
    rpm_used = 0
    rpd_used = 0
    tpm_used = 0
    for event in merge_events(events, now=now):
        ts = float(event["ts"])
        tokens = int(event["prompt_tokens"])
        if ts >= minute_start:
            rpm_used += 1
            tpm_used += tokens
        if pacific_day(ts) == today:
            rpd_used += 1
    rpm_remaining = max(0, rpm_cap - rpm_used)
    rpd_remaining = max(0, rpd_cap - rpd_used)
    tpm_remaining = max(0, tpm_cap - tpm_used)
    rpm_ratio = min(1.0, rpm_used / rpm_cap)
    rpd_ratio = min(1.0, rpd_used / rpd_cap)
    tpm_ratio = min(1.0, tpm_used / tpm_cap)
    limited = rpm_remaining == 0 or rpd_remaining == 0 or tpm_remaining == 0
    return {
        "rpm_limit": rpm_cap,
        "rpd_limit": rpd_cap,
        "tpm_limit": tpm_cap,
        "rpm_used": rpm_used,
        "rpd_used": rpd_used,
        "tpm_used": tpm_used,
        "rpm_remaining": rpm_remaining,
        "rpd_remaining": rpd_remaining,
        "tpm_remaining": tpm_remaining,
        "rpm_ratio": rpm_ratio,
        "rpd_ratio": rpd_ratio,
        "tpm_ratio": tpm_ratio,
        "limited": limited,
    }
