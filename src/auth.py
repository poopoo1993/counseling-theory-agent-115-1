"""電子郵件 OTP 登入。OTP 僅存於當前 Streamlit session；瀏覽器 sid 只存雜湊。"""

from __future__ import annotations

import hashlib
import secrets
import smtplib
import time
from email.message import EmailMessage
from typing import Any, Mapping


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    value = normalize_email(email)
    return bool(value) and "@" in value and "." in value.rsplit("@", 1)[-1]


def is_email_allowed(email: str, store: Any) -> bool:
    """Login is SQLite whitelist only; school-domain shortcut is not used."""
    value = normalize_email(email)
    if not is_valid_email(value):
        return False
    return bool(store.is_whitelisted(value))


def is_teacher(email: str, store: Any, fallback_teacher_emails: tuple[str, ...] = ()) -> bool:
    role = store.get_whitelist_role(email)
    if role:
        return role == "teacher"
    return normalize_email(email) in fallback_teacher_emails


BROWSER_SESSION_QUERY_KEY = "sid"
BROWSER_SESSION_TTL_SECONDS = 12 * 3600


def new_browser_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_browser_session_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def create_otp(ttl_seconds: int = 600) -> tuple[str, str, float]:
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()
    return code, f"{salt}:{digest}", time.time() + ttl_seconds


def verify_otp(code: str, stored: str, expires_at: float) -> bool:
    if time.time() > float(expires_at or 0):
        return False
    try:
        salt, expected = stored.split(":", 1)
    except ValueError:
        return False
    actual = hashlib.sha256(f"{salt}:{(code or '').strip()}".encode("utf-8")).hexdigest()
    return secrets.compare_digest(actual, expected)


def send_otp_email(recipient: str, code: str, smtp_config: Mapping[str, Any]) -> None:
    host = str(smtp_config.get("host", "smtp.gmail.com"))
    port = int(smtp_config.get("port", 587))
    sender = str(smtp_config.get("sender_email", "")).strip()
    password = str(smtp_config.get("app_password", "")).strip().replace(" ", "")
    if not sender or not password:
        raise RuntimeError("尚未設定 SMTP 寄件帳號或應用程式密碼。")

    message = EmailMessage()
    message["Subject"] = "諮商理論技巧訓練 Agent 登入驗證碼"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "你的登入驗證碼是：\n\n"
        f"{code}\n\n"
        "驗證碼僅於短時間內有效。若非本人操作，請忽略本信。"
    )
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(message)
