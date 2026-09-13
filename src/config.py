"""應用程式設定讀取與預設值。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _section(source: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = source.get(name, {})
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class AppConfig:
    app_title: str
    timezone: str
    model_name: str
    prompt_version: str
    rubric_version: str
    allowed_domains: tuple[str, ...]
    login_allowlist: tuple[str, ...]
    teacher_emails: tuple[str, ...]
    otp_ttl_seconds: int
    max_input_chars: int
    recent_context_turns: int

    @classmethod
    def from_secrets(cls, secrets: Mapping[str, Any]) -> "AppConfig":
        app = _section(secrets, "app")
        auth = _section(secrets, "auth")
        return cls(
            app_title=str(app.get("title", "諮商理論技巧訓練 Agent")),
            timezone=str(app.get("timezone", "Asia/Taipei")),
            model_name=str(app.get("model_name", "gemini-2.5-flash")),
            prompt_version=str(app.get("prompt_version", "theory-dialogue-v1.0")),
            rubric_version=str(app.get("rubric_version", "theory-rubric-v1.0")),
            allowed_domains=tuple(str(x).lower() for x in auth.get("allowed_domains", ["hcu.edu.tw"])),
            login_allowlist=tuple(str(x).lower() for x in auth.get("login_allowlist", [])),
            teacher_emails=tuple(str(x).lower() for x in auth.get("teacher_emails", [])),
            otp_ttl_seconds=int(auth.get("otp_ttl_seconds", 600)),
            max_input_chars=int(app.get("max_input_chars", 800)),
            recent_context_turns=int(app.get("recent_context_turns", 14)),
        )


DEFAULT_SETTINGS = {
    "system_enabled": "true",
    "open_start": "",
    "open_end": "",
    "max_sessions_per_student": "0",
    "duration_experience_min": "8",
    "duration_practice_min": "15",
    "allowed_modes": "experience,practice",
    "student_feedback_visible": "true",
    "student_score_visible": "true",
}


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
