"""逐字稿與非語言訊息處理。"""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Iterable


NONVERBAL_RE = re.compile(r"[（(]([^()（）]{1,80})[）)]")


def extract_nonverbal_cues(text: str) -> list[str]:
    return [item.strip() for item in NONVERBAL_RE.findall(text or "") if item.strip()]


def make_transcript_txt(session: dict, turns: Iterable[dict]) -> bytes:
    school_name = session.get("school_name", "")
    techniques = session.get("selected_technique_names", [])
    lines = [
        "諮商理論技巧訓練 Agent 本次晤談逐字稿",
        "",
        f"Session ID：{session.get('session_id', '')}",
        f"日期：{session.get('started_at', datetime.now().isoformat())}",
        f"模式：{'學派體驗' if session.get('mode') == 'experience' else '學生實作'}",
        f"學派：{school_name}",
        f"本次技巧：{'／'.join(techniques)}",
        "",
        "提醒：本逐字稿僅供教學複習，不是心理治療、診斷或危機處遇紀錄。",
        "",
    ]
    role_names = {
        "student_client": "學生個案",
        "student_counselor": "學生諮商師",
        "ai_client": "AI 模擬個案",
        "ai_counselor": "AI 示範諮商師",
        "system": "系統",
    }
    for turn in turns:
        role = role_names.get(turn.get("speaker_role", ""), turn.get("speaker_role", ""))
        lines.append(f"[{turn.get('turn_index', '')}] {role}：{turn.get('content_raw', '')}")
        lines.append("")
    return "\n".join(lines).encode("utf-8-sig")


def safe_filename(session_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "session")
    return f"theory_agent_transcript_{cleaned}.txt"


def transcript_text(turns: Iterable[dict]) -> str:
    buffer = io.StringIO()
    for turn in turns:
        buffer.write(f"[{turn.get('turn_index')}] {turn.get('speaker_role')}: {turn.get('content_raw')}\n")
    return buffer.getvalue()
