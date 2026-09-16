from datetime import datetime

from src.gemini_quota import (
    DEFAULT_FREE_RPD,
    DEFAULT_FREE_RPM,
    DEFAULT_FREE_TPM,
    PACIFIC,
    estimate_prompt_tokens,
    format_remaining,
    merge_events,
    pacific_day,
    record_event,
    snapshot,
)


def test_empty_usage_shows_full_remaining():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=PACIFIC).timestamp()
    view = snapshot([], now=now)
    assert view["rpm_remaining"] == DEFAULT_FREE_RPM
    assert view["rpd_remaining"] == DEFAULT_FREE_RPD
    assert view["tpm_remaining"] == DEFAULT_FREE_TPM
    assert view["rpm_ratio"] == view["rpd_ratio"] == view["tpm_ratio"] == 0
    assert not view["limited"]


def test_any_dimension_at_cap_is_limited():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=PACIFIC).timestamp()
    rpm_events = [
        {"id": f"rpm-{index}", "ts": now - 10, "prompt_tokens": 1}
        for index in range(DEFAULT_FREE_RPM)
    ]
    rpm_view = snapshot(rpm_events, now=now)
    assert rpm_view["rpm_remaining"] == 0
    assert rpm_view["rpd_remaining"] == DEFAULT_FREE_RPD - DEFAULT_FREE_RPM
    assert rpm_view["limited"]

    rpd_events = [
        {"id": f"rpd-{index}", "ts": now - 120, "prompt_tokens": 1}
        for index in range(DEFAULT_FREE_RPD)
    ]
    rpd_view = snapshot(rpd_events, now=now)
    assert rpd_view["rpd_remaining"] == 0
    assert rpd_view["rpm_used"] == 0
    assert rpd_view["limited"]

    tpm_events = [{"id": "tpm", "ts": now - 5, "prompt_tokens": DEFAULT_FREE_TPM}]
    tpm_view = snapshot(tpm_events, now=now)
    assert tpm_view["tpm_remaining"] == 0
    assert tpm_view["rpm_remaining"] == DEFAULT_FREE_RPM - 1
    assert tpm_view["limited"]


def test_rpd_resets_at_pacific_midnight():
    now = datetime(2026, 9, 17, 0, 30, tzinfo=PACIFIC).timestamp()
    yesterday = datetime(2026, 9, 16, 23, 45, tzinfo=PACIFIC).timestamp()
    assert pacific_day(yesterday) != pacific_day(now)
    view = snapshot(
        [{"id": "old", "ts": yesterday, "prompt_tokens": 9}],
        now=now,
    )
    assert view["rpd_used"] == 0
    assert view["rpd_remaining"] == DEFAULT_FREE_RPD


def test_merge_events_dedupes_and_records():
    now = 1_790_000_000.0
    first = record_event([], event_id="chat-1", prompt_tokens=12, ts=now)
    again = record_event(first, event_id="chat-1", prompt_tokens=99, ts=now)
    assert len(again) == 1
    assert again[0]["prompt_tokens"] == 99
    merged = merge_events(again, [{"id": "chat-2", "ts": now, "prompt_tokens": 3}])
    assert [item["id"] for item in merged] == ["chat-1", "chat-2"]


def test_token_estimate_and_remaining_format():
    assert estimate_prompt_tokens("你好", "個案") == 4
    assert format_remaining(8) == "8"
    assert format_remaining(248_000) == "248K"
