"""Session 與逐輪紀錄物件的建立函式。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .theory_library import get_school, get_techniques
from .transcript import extract_nonverbal_cues


def now_iso(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).isoformat(timespec="seconds")


def new_session(
    *,
    participant_id: str,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    model_name: str,
    prompt_version: str,
    timezone: str,
    theme: str,
    difficulty: str,
    thread_id: str | None = None,
    case_id: str = "",
) -> dict[str, Any]:
    school = get_school(school_id)
    technique_names = [t["name"] for t in get_techniques(school_id, selected_ids)]
    return {
        "session_id": str(uuid.uuid4()),
        "conversation_thread_id": thread_id or str(uuid.uuid4()),
        "participant_id": participant_id,
        "agent_type": "theory",
        "mode": mode,
        "continuation_role": "ai_client" if mode == "practice" else "ai_counselor",
        "started_at": now_iso(timezone),
        "ended_at": "",
        "duration_seconds": "",
        "case_id": case_id,
        "school_id": school_id,
        "school_name": school["name"],
        "selected_techniques": selected_ids,
        "selected_technique_names": technique_names,
        "model_name": model_name,
        "prompt_version": prompt_version,
        "temperature": 0.4,
        "completion_status": "in_progress",
        "theme": theme,
        "difficulty": difficulty,
    }


def new_turn(
    *,
    session: dict[str, Any],
    turn_index: int,
    speaker_role: str,
    content: str,
    timezone: str,
    latency_ms: int | str = "",
    error_flag: str = "",
) -> dict[str, Any]:
    return {
        "turn_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "conversation_thread_id": session["conversation_thread_id"],
        "participant_id": session["participant_id"],
        "turn_index": turn_index,
        "speaker_role": speaker_role,
        "speaker_id": "",
        "content_raw": content,
        "nonverbal_cues": extract_nonverbal_cues(content),
        "timestamp": now_iso(timezone),
        "stage_at_turn": "",
        "skill_labels": [],
        "selected_skill_match": "",
        "latency_ms": latency_ms,
        "error_flag": error_flag,
    }


def finish_session(session: dict[str, Any], timezone: str, status: str = "completed") -> dict[str, Any]:
    result = dict(session)
    ended = datetime.now(ZoneInfo(timezone))
    started = datetime.fromisoformat(str(session["started_at"]))
    result["ended_at"] = ended.isoformat(timespec="seconds")
    result["duration_seconds"] = max(0, int((ended - started).total_seconds()))
    result["completion_status"] = status
    return result
