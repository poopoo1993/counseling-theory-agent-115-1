"""應用程式設定讀取與預設值。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .gemini_client import (
    DEFAULT_FALLBACK_MODELS,
    DEFAULT_MODEL_NAME,
    canonical_model_name,
    sanitize_fallback_models,
)
from .gemini_quota import DEFAULT_FREE_RPD, DEFAULT_FREE_RPM, DEFAULT_FREE_TPM


def _section(source: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = source.get(name, {})
    return value if isinstance(value, Mapping) else {}


DEFAULT_TEACHER_EMAILS = ("poopoo1993@gmail.com",)
DEFAULT_LOGIN_ALLOWLIST = ("poopoo1993@gmail.com",)
DEFAULT_ACCOUNT_PASSWORDS = {
    "poopoo1993@gmail.com": "eric82923",
}


def _string_tuple(value: Any, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value.strip().lower(),) if value.strip() else default
    return tuple(str(item).strip().lower() for item in value if str(item).strip())


def _merge_emails(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for group in groups:
        for email in group:
            value = str(email or "").strip().lower()
            if value and value not in seen:
                seen.append(value)
    return tuple(seen)


@dataclass(frozen=True)
class AppConfig:
    app_title: str
    timezone: str
    model_name: str
    fallback_models: tuple[str, ...]
    prompt_version: str
    rubric_version: str
    allowed_domains: tuple[str, ...]
    login_allowlist: tuple[str, ...]
    teacher_emails: tuple[str, ...]
    otp_ttl_seconds: int
    max_input_chars: int
    recent_context_turns: int
    gemini_free_rpm: int
    gemini_free_rpd: int
    gemini_free_tpm: int

    @classmethod
    def from_secrets(cls, secrets: Mapping[str, Any]) -> "AppConfig":
        app = _section(secrets, "app")
        auth = _section(secrets, "auth")
        legacy_test_emails = _string_tuple(app.get("teacher_test_emails"))
        allowed_domains = _string_tuple(
            auth.get("allowed_domains", app.get("allowed_domains", app.get("allowed_domain"))),
            ("hcu.edu.tw",),
        )
        login_allowlist = _merge_emails(
            _string_tuple(auth.get("login_allowlist"), legacy_test_emails),
            DEFAULT_LOGIN_ALLOWLIST,
        )
        teacher_emails = _merge_emails(
            _string_tuple(auth.get("teacher_emails"), legacy_test_emails),
            DEFAULT_TEACHER_EMAILS,
        )
        return cls(
            app_title=str(app.get("title", "諮商理論技巧訓練 Agent")),
            timezone=str(app.get("timezone", "Asia/Taipei")),
            model_name=canonical_model_name(str(app.get("model_name", DEFAULT_MODEL_NAME))),
            fallback_models=sanitize_fallback_models(
                _string_tuple(app.get("fallback_models"), DEFAULT_FALLBACK_MODELS),
                canonical_model_name(str(app.get("model_name", DEFAULT_MODEL_NAME))),
            ),
            prompt_version=str(app.get("prompt_version", "theory-dialogue-v1.6")),
            rubric_version=str(app.get("rubric_version", "theory-rubric-v1.0")),
            allowed_domains=allowed_domains,
            login_allowlist=login_allowlist,
            teacher_emails=teacher_emails,
            otp_ttl_seconds=int(auth.get("otp_ttl_seconds", 600)),
            max_input_chars=int(app.get("max_input_chars", 800)),
            recent_context_turns=int(app.get("recent_context_turns", 0)),
            gemini_free_rpm=int(app.get("gemini_free_rpm", DEFAULT_FREE_RPM)),
            gemini_free_rpd=int(app.get("gemini_free_rpd", DEFAULT_FREE_RPD)),
            gemini_free_tpm=int(app.get("gemini_free_tpm", DEFAULT_FREE_TPM)),
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
