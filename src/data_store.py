"""Persistent research/login store. Production uses SQLite; Sheets code remains unused.

API Key 永遠不會傳入此模組。原始逐輪內容只新增、不覆寫；體驗模式若學生不同意作為研究素材，則刪除該 Session 的 ChatLogs。若願意但勾選匿名，晤談過程另存 AnonymousSessions／AnonymousChatLogs，不含帳號或 thread 關聯。正式課務以 Google 試算表持久化（Cloud reboot 不會清掉）；本機未設定試算表時才用 SQLite。
"""

from __future__ import annotations

import atexit
import base64
import binascii
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .config import (
    DEFAULT_ACCOUNT_PASSWORDS,
    DEFAULT_LOGIN_ALLOWLIST,
    DEFAULT_SETTINGS,
    DEFAULT_TEACHER_EMAILS,
)


SCHEMAS: dict[str, list[str]] = {
    "whitelist": ["email", "role", "enabled", "created_at", "password_hash"],
    "IdentityMap": ["participant_id", "email", "created_at", "last_login_at", "role"],
    "Sessions": [
        "session_id", "conversation_thread_id", "participant_id", "agent_type", "mode",
        "continuation_role", "started_at", "ended_at", "duration_seconds", "case_id",
        "school_id", "selected_techniques", "selected_technique_names", "model_name",
        "prompt_version", "temperature", "completion_status", "theme", "difficulty",
        "research_consent",
    ],
    "ChatLogs": [
        "turn_id", "session_id", "conversation_thread_id", "participant_id", "turn_index",
        "speaker_role", "speaker_id", "content_raw", "nonverbal_cues", "timestamp",
        "stage_at_turn", "skill_labels", "selected_skill_match", "latency_ms", "error_flag",
    ],
    "AnonymousSessions": [
        "anonymous_session_id", "started_at", "ended_at", "duration_seconds", "mode",
        "school_id", "selected_techniques", "selected_technique_names", "theme",
        "difficulty", "model_name", "prompt_version", "created_at",
    ],
    "AnonymousChatLogs": [
        "turn_id", "anonymous_session_id", "turn_index", "speaker_role", "content_raw",
        "nonverbal_cues", "timestamp", "latency_ms", "error_flag",
    ],
    "Threads": [
        "conversation_thread_id", "participant_id", "mode", "continuation_role", "school_id",
        "school_name", "selected_techniques", "selected_technique_names", "case_id", "case_data",
        "counseling_plan", "chat_analysis", "latest_snapshot", "last_session_id",
        "recent_turns", "difficulty", "updated_at", "status",
    ],
    "Assessments": [
        "assessment_id", "session_id", "participant_id", "mode", "school_id", "rubric_version",
        "total_score", "dimension_scores", "skill_events", "strengths", "improvement_points",
        "quoted_examples", "next_practice_focus", "encouragement", "raw_model_output",
        "parsed_json", "created_at",
    ],
    "SkillEvents": [
        "assessment_id", "session_id", "participant_id", "technique_id", "status",
        "turn_index", "quality", "evidence_quote", "effect",
    ],
    "TeacherGrades": [
        "grade_id", "session_id", "participant_id", "teacher_email", "teacher_score",
        "teacher_comment", "created_at",
    ],
    "Settings": ["key", "value", "updated_at", "updated_by"],
    "RiskEvents": [
        "risk_event_id", "session_id", "participant_id", "timestamp", "event_type",
        "action_taken", "content_redacted",
    ],
    "AuthSessions": [
        "token_hash", "email", "participant_id", "role", "created_at", "expires_at",
        "last_seen_at",
    ],
}


def require_sheets_enabled(secrets: Mapping[str, Any]) -> bool:
    return str(secrets.get("REQUIRE_SHEETS", "")).strip().lower() in {"1", "true", "yes", "on"}


def load_sheets_credentials(secrets: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    spreadsheet_id = str(secrets.get("SPREADSHEET_ID", "")).strip()
    service_json = secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    service_account: Mapping[str, Any] | dict[str, Any] = {}
    if service_json:
        if isinstance(service_json, Mapping):
            service_account = dict(service_json)
        else:
            parsed = json.loads(str(service_json))
            if not isinstance(parsed, dict):
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON 必須是 JSON 物件。")
            service_account = parsed

    block = secrets.get("google_sheets", {})
    if not isinstance(block, Mapping):
        block = {}
    if not spreadsheet_id:
        spreadsheet_id = str(block.get("spreadsheet_id", "")).strip()
    if not service_account:
        nested_service = block.get("service_account", {})
        if isinstance(nested_service, Mapping):
            service_account = nested_service

    if not service_account:
        legacy_service = secrets.get("gcp_service_account", {})
        if isinstance(legacy_service, Mapping):
            service_account = legacy_service
    if not spreadsheet_id or not service_account:
        raise RuntimeError(
            "尚未設定 SPREADSHEET_ID／GOOGLE_SERVICE_ACCOUNT_JSON，"
            "或 google_sheets／gcp_service_account 相容欄位。"
        )
    return spreadsheet_id, dict(service_account)


def sheets_secrets_present(secrets: Mapping[str, Any]) -> bool:
    try:
        spreadsheet_id, service_account = load_sheets_credentials(secrets)
    except (RuntimeError, ValueError, json.JSONDecodeError, TypeError):
        return False
    return bool(spreadsheet_id and service_account)


def choose_store_backend(secrets: Mapping[str, Any]) -> str:
    if require_sheets_enabled(secrets) or sheets_secrets_present(secrets):
        return "sheets"
    return "sqlite"


_TRANSIENT_SHEETS_TOKENS = (
    "429",
    "quota",
    "rate limit",
    "rate_limit",
    "resource_exhausted",
    "backenderror",
    "internal error",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "unavailable",
)

SHEETS_USER_ERROR = (
    "無法讀取 Google 試算表，因此登入畫面無法開啟。"
    "常見原因是試算表 API 暫時忙碌，或一分鐘內請求次數過多。"
    "請等待約一分鐘後重新整理。"
    "若持續失敗，請確認試算表已分享給服務帳戶 Email（編輯者），且已啟用 Google Sheets API。"
)

SERVICE_ACCOUNT_USER_ERROR = (
    "Google 服務帳戶金鑰格式不正確，無法連線試算表。"
    "請檢查 Streamlit Secrets 的 GOOGLE_SERVICE_ACCOUNT_JSON。"
)

SHEETS_FLUSH_ROW_THRESHOLD = 80
SHEETS_FLUSH_INTERVAL_SECONDS = 15.0
IMMEDIATE_SHEETS = frozenset({
    "whitelist",
    "AuthSessions",
    "IdentityMap",
    "Settings",
    "RiskEvents",
})


def is_transient_sheets_error(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)
    try:
        if int(status) in {429, 500, 502, 503, 504}:
            return True
    except (TypeError, ValueError):
        pass
    text = str(exc).lower()
    return any(token in text for token in _TRANSIENT_SHEETS_TOKENS)


def sheets_retry_delay(exc: BaseException, fallback: float) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("Retry-After") or headers.get("retry-after")
    try:
        if raw is not None:
            return min(max(float(raw), 0.5), 16.0)
    except (TypeError, ValueError):
        pass
    return fallback


def retry_sheets_call(operation: Callable[[], Any], attempts: int = 5) -> Any:
    delay = 1.0
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not is_transient_sheets_error(exc):
                raise
            time.sleep(sheets_retry_delay(exc, delay))
            delay = min(delay * 2, 8.0)
    assert last_exc is not None
    raise last_exc


def public_store_error_message(exc: BaseException) -> str:
    raw = str(exc).strip()
    if any("\u4e00" <= ch <= "\u9fff" for ch in raw):
        return raw
    if isinstance(exc, (
        ServiceAccountFieldsMissingError,
        PrivateKeyIncompleteError,
        PrivateKeyEncodingError,
        PrivateKeyParseError,
    )):
        return SERVICE_ACCOUNT_USER_ERROR
    text = f"{type(exc).__name__} {exc}".lower()
    if any(token in text for token in ("apierror", "gspread", "spreadsheet", "quota", "429", "sheets")):
        return SHEETS_USER_ERROR
    return (
        "資料儲存初始化失敗，因此登入畫面無法開啟。"
        "請稍候再重新整理；若持續發生，請到 Streamlit Manage app 查看 logs。"
    )


class ServiceAccountFieldsMissingError(ValueError):
    """Required service-account fields are absent."""


class PrivateKeyIncompleteError(ValueError):
    """The PEM body is empty or shorter than its DER length header declares."""


class PrivateKeyEncodingError(ValueError):
    """The PEM body contains characters that are not valid Base64."""


class PrivateKeyParseError(ValueError):
    """The decoded value is not a usable PKCS#8 private key."""


def json_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def parse_json_cell(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _flag_enabled(value: Any) -> bool:
    return str(value or "true").strip().lower() not in {"", "0", "false", "no", "off"}


class WhitelistMixin:
    def _whitelist_row(self, email: str) -> dict[str, Any] | None:
        value = str(email or "").strip().lower()
        return next(
            (r for r in self.all_records("whitelist") if str(r.get("email", "")).lower() == value),
            None,
        )

    def is_whitelisted(self, email: str) -> bool:
        row = self._whitelist_row(email)
        return bool(row) and _flag_enabled(row.get("enabled", "true"))

    def get_whitelist_role(self, email: str) -> str:
        row = self._whitelist_row(email)
        if not row or not _flag_enabled(row.get("enabled", "true")):
            return ""
        return str(row.get("role", "student")).strip().lower() or "student"

    def upsert_whitelist(self, email: str, role: str, enabled: bool = True) -> None:
        value = str(email or "").strip().lower()
        existing = self._whitelist_row(value) or {}
        stored_role = (role or existing.get("role") or "student")
        self._upsert_by_key("whitelist", "email", value, {
            "email": value,
            "role": str(stored_role).strip().lower() or "student",
            "enabled": "true" if enabled else "false",
            "created_at": existing.get("created_at") or self.now(),
            "password_hash": existing.get("password_hash", ""),
        })

    def has_login_password(self, email: str) -> bool:
        row = self._whitelist_row(email)
        return bool(row and str(row.get("password_hash", "")).strip())

    def get_password_hash(self, email: str) -> str:
        row = self._whitelist_row(email) or {}
        return str(row.get("password_hash", "")).strip()

    def set_password_hash(self, email: str, password_hash: str) -> None:
        value = str(email or "").strip().lower()
        existing = self._whitelist_row(value)
        if not existing:
            raise KeyError(value)
        self._upsert_by_key("whitelist", "email", value, {
            **existing,
            "email": value,
            "password_hash": str(password_hash or ""),
        })

    def seed_whitelist(self, login_allowlist: tuple[str, ...] = (), teacher_emails: tuple[str, ...] = ()) -> None:
        teachers = tuple(dict.fromkeys(
            str(item).strip().lower()
            for item in (*teacher_emails, *DEFAULT_TEACHER_EMAILS)
            if str(item).strip()
        ))
        allow = tuple(dict.fromkeys(
            str(item).strip().lower()
            for item in (*login_allowlist, *DEFAULT_LOGIN_ALLOWLIST)
            if str(item).strip()
        ))
        fingerprint = (teachers, allow)
        if getattr(self, "_whitelist_seed_key", None) == fingerprint:
            return
        rows = {
            str(item.get("email", "")).strip().lower(): item
            for item in self.all_records("whitelist")
            if str(item.get("email", "")).strip()
        }
        for email in teachers:
            existing = rows.get(email)
            if existing and str(existing.get("role", "")).strip().lower() == "teacher":
                continue
            enabled = _flag_enabled(existing.get("enabled", "true")) if existing else True
            self.upsert_whitelist(email, "teacher", enabled)
            rows[email] = self._whitelist_row(email) or {"email": email, "role": "teacher"}
        for email in allow:
            if email in teachers or email in rows:
                continue
            self.upsert_whitelist(email, "student", True)
            rows[email] = {"email": email, "role": "student"}
        from .auth import seed_default_account_passwords
        needs_password = False
        for email in DEFAULT_ACCOUNT_PASSWORDS:
            row = rows.get(str(email).strip().lower())
            if row is not None and not str(row.get("password_hash", "")).strip():
                needs_password = True
                break
        if needs_password:
            seed_default_account_passwords(self)
        self._whitelist_seed_key = fingerprint

    def list_whitelist(self) -> list[dict[str, Any]]:
        rows = self.all_records("whitelist")
        rows.sort(key=lambda r: str(r.get("email", "")))
        return rows


class LoginSessionMixin:
    """Browser login tokens. Never store Gemini API keys here."""

    online_window_seconds = 180

    def create_login_session(
        self,
        token_hash: str,
        email: str,
        participant_id: str,
        role: str,
        ttl_seconds: int = 43200,
    ) -> None:
        now = self.now()
        expires = datetime.now(ZoneInfo(self.timezone)) + timedelta(seconds=int(ttl_seconds))
        self.append("AuthSessions", {
            "token_hash": token_hash,
            "email": str(email or "").strip().lower(),
            "participant_id": participant_id,
            "role": role,
            "created_at": now,
            "expires_at": expires.isoformat(timespec="seconds"),
            "last_seen_at": now,
        })

    def get_login_session(self, token_hash: str) -> dict[str, Any] | None:
        digest = str(token_hash or "")
        if not digest:
            return None
        now = datetime.now(ZoneInfo(self.timezone))
        for row in self.all_records("AuthSessions"):
            if str(row.get("token_hash", "")) != digest:
                continue
            try:
                expires = datetime.fromisoformat(str(row.get("expires_at", "")))
            except ValueError:
                continue
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=ZoneInfo(self.timezone))
            if expires >= now:
                return dict(row)
            self._delete_by_key("AuthSessions", "token_hash", digest)
        return None

    def delete_login_session(self, token_hash: str) -> None:
        self._delete_by_key("AuthSessions", "token_hash", str(token_hash or ""))

    def touch_login_session(self, token_hash: str) -> None:
        row = self.get_login_session(token_hash)
        if not row:
            return
        row["last_seen_at"] = self.now()
        self._upsert_by_key("AuthSessions", "token_hash", str(row["token_hash"]), row)

    def list_online_users(self, within_seconds: int | None = None) -> list[dict[str, str]]:
        window = int(within_seconds if within_seconds is not None else self.online_window_seconds)
        now = datetime.now(ZoneInfo(self.timezone))
        cutoff = now - timedelta(seconds=window)
        found: dict[str, dict[str, str]] = {}
        for row in self.all_records("AuthSessions"):
            email = str(row.get("email") or "").strip().lower()
            raw_seen = str(row.get("last_seen_at") or "").strip()
            raw_expires = str(row.get("expires_at") or "").strip()
            if not email or not raw_seen:
                continue
            try:
                seen = datetime.fromisoformat(raw_seen)
                expires = datetime.fromisoformat(raw_expires) if raw_expires else seen
            except ValueError:
                continue
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=ZoneInfo(self.timezone))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=ZoneInfo(self.timezone))
            if seen < cutoff or expires < now:
                continue
            stamp = seen.isoformat(timespec="seconds")
            previous = found.get(email)
            if previous is None or stamp > previous.get("last_seen_at", ""):
                found[email] = {
                    "email": email,
                    "role": str(row.get("role") or "student"),
                    "participant_id": str(row.get("participant_id") or ""),
                    "last_seen_at": stamp,
                }
        people = list(found.values())
        people.sort(key=lambda item: (0 if item.get("role") == "teacher" else 1, item.get("email", "")))
        return people


def normalize_private_key(value: Any) -> str:
    """Accept either a complete PEM key or the body-only legacy format."""
    key = str(value or "").strip().replace("\\n", "\n")
    if not key:
        return key

    if "-----BEGIN PRIVATE KEY-----" in key and "-----END PRIVATE KEY-----" in key:
        return key

    # The earlier group Agent stored only the Base64 body. Reconstruct the
    # standard PKCS#8 PEM wrapper required by google-auth/cryptography.
    body = "".join(key.split())
    return (
        "-----BEGIN PRIVATE KEY-----\n"
        f"{body}\n"
        "-----END PRIVATE KEY-----\n"
    )


def validate_private_key_structure(pem: str) -> None:
    """Validate PEM/Base64/DER structure without logging any credential text."""
    begin = "-----BEGIN PRIVATE KEY-----"
    end = "-----END PRIVATE KEY-----"
    if begin not in pem or end not in pem:
        raise PrivateKeyIncompleteError

    body = pem.split(begin, 1)[1].split(end, 1)[0]
    compact = "".join(body.split())
    if not compact:
        raise PrivateKeyIncompleteError

    try:
        der = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        raise PrivateKeyEncodingError from None

    # DER begins with a SEQUENCE whose encoded length describes the whole key.
    if len(der) < 4 or der[0] != 0x30:
        raise PrivateKeyParseError
    first_length = der[1]
    if first_length & 0x80:
        length_octets = first_length & 0x7F
        if length_octets == 0 or len(der) < 2 + length_octets:
            raise PrivateKeyIncompleteError
        payload_length = int.from_bytes(der[2:2 + length_octets], "big")
        expected_length = 2 + length_octets + payload_length
    else:
        expected_length = 2 + first_length
    if expected_length != len(der):
        raise PrivateKeyIncompleteError


class GoogleSheetsStore(WhitelistMixin, LoginSessionMixin):
    def __init__(self, spreadsheet_id: str, service_account: Mapping[str, Any], timezone: str):
        import gspread

        credentials = dict(service_account)
        required = {"client_email", "token_uri", "private_key"}
        if any(not str(credentials.get(field, "")).strip() for field in required):
            raise ServiceAccountFieldsMissingError
        if "private_key" in credentials:
            credentials["private_key"] = normalize_private_key(credentials["private_key"])
            validate_private_key_structure(credentials["private_key"])
        try:
            client = gspread.service_account_from_dict(credentials)
        except ValueError:
            raise PrivateKeyParseError from None
        self.book = retry_sheets_call(lambda: client.open_by_key(spreadsheet_id))
        self.timezone = timezone
        self.worksheets: dict[str, Any] = {}
        self._init_write_buffer()
        self.ensure_schema()

    @classmethod
    def from_secrets(cls, secrets: Mapping[str, Any], timezone: str) -> "GoogleSheetsStore":
        spreadsheet_id, service_account = load_sheets_credentials(secrets)
        return cls(spreadsheet_id, service_account, timezone)

    def now(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")

    def ensure_schema(self) -> None:
        if getattr(self, "_schema_ready", False) and set(self.worksheets) >= set(SCHEMAS):
            return
        existing = {ws.title: ws for ws in retry_sheets_call(self.book.worksheets)}
        present = [name for name in SCHEMAS if name in existing]
        headers_by_name = self._header_rows(existing, present)
        for name, headers in SCHEMAS.items():
            ws = existing.get(name)
            if ws is None:
                ws = retry_sheets_call(partial(
                    self.book.add_worksheet,
                    title=name,
                    rows=5000,
                    cols=max(20, len(headers) + 2),
                ))
                retry_sheets_call(partial(ws.append_row, headers, value_input_option="RAW"))
                retry_sheets_call(partial(ws.freeze, rows=1))
                existing[name] = ws
            else:
                current = headers_by_name.get(name) or []
                if not current:
                    retry_sheets_call(partial(ws.append_row, headers, value_input_option="RAW"))
                    retry_sheets_call(partial(ws.freeze, rows=1))
                elif current != headers:
                    missing = [h for h in headers if h not in current]
                    if missing:
                        filled = current + missing
                        retry_sheets_call(partial(ws.update, values=[filled], range_name="A1"))
            self.worksheets[name] = ws
        settings = self.all_records("Settings")
        if not settings:
            for key, value in DEFAULT_SETTINGS.items():
                self.append("Settings", {"key": key, "value": value, "updated_at": self.now(), "updated_by": "system"})
        self._schema_ready = True

    def _header_rows(self, sheets: Mapping[str, Any], names: Sequence[str]) -> dict[str, list[str]]:
        if not names:
            return {}
        book = self.book
        if hasattr(book, "values_batch_get"):
            ranges = [f"'{name}'!1:1" for name in names]
            payload = retry_sheets_call(lambda: book.values_batch_get(ranges))
            blocks = payload.get("valueRanges") if isinstance(payload, Mapping) else None
            if isinstance(blocks, list) and len(blocks) == len(names):
                result: dict[str, list[str]] = {}
                for name, block in zip(names, blocks):
                    values = block.get("values") if isinstance(block, Mapping) else None
                    row = values[0] if values else []
                    result[name] = [str(cell) for cell in row]
                return result
        result = {}
        for name in names:
            row = retry_sheets_call(partial(sheets[name].row_values, 1))
            result[name] = [str(cell) for cell in row]
        return result

    def _init_write_buffer(self) -> None:
        if getattr(self, "_buffer_lock", None) is not None:
            return
        self._buffer_lock = threading.Lock()
        self._pending_appends: dict[str, list[dict[str, Any]]] = {}
        self._pending_upserts: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._buffer_since = time.monotonic()
        self._flush_timer: threading.Timer | None = None
        atexit.register(self._atexit_flush)

    def _atexit_flush(self) -> None:
        try:
            self.flush()
        except Exception:
            pass

    def _pending_count_locked(self) -> int:
        return sum(len(rows) for rows in self._pending_appends.values()) + len(self._pending_upserts)

    def _arm_flush_timer_locked(self) -> None:
        if self._pending_count_locked() == 1:
            self._buffer_since = time.monotonic()
        if self._flush_timer is not None:
            return
        delay = float(SHEETS_FLUSH_INTERVAL_SECONDS)
        if delay <= 0:
            return
        timer = threading.Timer(delay, self._atexit_flush)
        timer.daemon = True
        self._flush_timer = timer
        timer.start()

    def _cancel_flush_timer_locked(self) -> None:
        timer = self._flush_timer
        self._flush_timer = None
        if timer is not None:
            timer.cancel()

    def _maybe_flush_locked(self) -> None:
        if self._pending_count_locked() <= 0:
            return
        due = (time.monotonic() - self._buffer_since) >= float(SHEETS_FLUSH_INTERVAL_SECONDS)
        if self._pending_count_locked() >= int(SHEETS_FLUSH_ROW_THRESHOLD) or due:
            self._flush_locked()

    def flush(self) -> None:
        self._init_write_buffer()
        with self._buffer_lock:
            self._flush_locked()

    def _append_rows_now(self, sheet: str, records: Sequence[Mapping[str, Any]]) -> None:
        if not records:
            return
        headers = SCHEMAS[sheet]
        rows = [[json_cell(record.get(header, "")) for header in headers] for record in records]
        ws = self.worksheets[sheet]
        append_rows = getattr(ws, "append_rows", None)
        if callable(append_rows):
            retry_sheets_call(partial(append_rows, rows, value_input_option="RAW"))
            return
        for row in rows:
            retry_sheets_call(partial(ws.append_row, row, value_input_option="RAW"))

    def _append_now(self, sheet: str, record: Mapping[str, Any]) -> None:
        self._append_rows_now(sheet, [record])

    def _upsert_now(self, sheet: str, key: str, value: str, record: Mapping[str, Any]) -> None:
        self._flush_upserts_now(sheet, [(key, value, dict(record))])

    def _flush_upserts_now(self, sheet: str, items: Sequence[tuple[str, str, Mapping[str, Any]]]) -> None:
        if not items:
            return
        ws = self.worksheets[sheet]
        headers = SCHEMAS[sheet]
        records = retry_sheets_call(partial(ws.get_all_records, default_blank=""))
        updates: list[dict[str, Any]] = []
        new_rows: list[Mapping[str, Any]] = []
        for key, value, record in items:
            values = [json_cell(record.get(header, "")) for header in headers]
            row_index = next(
                (i + 2 for i, row in enumerate(records) if str(row.get(key, "")) == str(value)),
                None,
            )
            if row_index is None:
                new_rows.append(record)
                records.append({header: json_cell(record.get(header, "")) for header in headers})
            else:
                updates.append({"range": f"A{row_index}", "values": [values]})
        if updates:
            batch_update = getattr(ws, "batch_update", None)
            if callable(batch_update):
                retry_sheets_call(partial(batch_update, updates))
            else:
                for item in updates:
                    retry_sheets_call(partial(
                        ws.update, values=item["values"], range_name=item["range"]
                    ))
        self._append_rows_now(sheet, new_rows)

    def _flush_locked(self) -> None:
        appends = self._pending_appends
        upserts = self._pending_upserts
        self._pending_appends = {}
        self._pending_upserts = {}
        self._cancel_flush_timer_locked()
        self._buffer_since = time.monotonic()
        for sheet, records in appends.items():
            self._append_rows_now(sheet, records)
        by_sheet: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
        for (sheet, key, value), record in upserts.items():
            by_sheet.setdefault(sheet, []).append((key, value, record))
        for sheet, items in by_sheet.items():
            self._flush_upserts_now(sheet, items)

    def _drop_buffered_session(self, session_id: str) -> None:
        sid = str(session_id or "")
        if not sid:
            return
        self._init_write_buffer()
        with self._buffer_lock:
            for sheet in ("ChatLogs", "Assessments", "SkillEvents"):
                rows = self._pending_appends.get(sheet) or []
                self._pending_appends[sheet] = [
                    row for row in rows if str(row.get("session_id", "")) != sid
                ]
                for item_key in [
                    key for key, record in self._pending_upserts.items()
                    if key[0] == sheet and str(record.get("session_id", "")) == sid
                ]:
                    self._pending_upserts.pop(item_key, None)

    def append(self, sheet: str, record: Mapping[str, Any]) -> None:
        payload = dict(record)
        if sheet in IMMEDIATE_SHEETS:
            self._append_now(sheet, payload)
            return
        self._init_write_buffer()
        with self._buffer_lock:
            self._pending_appends.setdefault(sheet, []).append(payload)
            self._arm_flush_timer_locked()
            self._maybe_flush_locked()

    def all_records(self, sheet: str) -> list[dict[str, Any]]:
        rows = retry_sheets_call(partial(
            self.worksheets[sheet].get_all_records, default_blank=""
        ))
        merged = [dict(row) for row in rows]
        lock = getattr(self, "_buffer_lock", None)
        if lock is None:
            return merged
        with lock:
            for record in self._pending_appends.get(sheet, []):
                merged.append(dict(record))
            for (pending_sheet, key, value), record in self._pending_upserts.items():
                if pending_sheet != sheet:
                    continue
                index = next(
                    (i for i, row in enumerate(merged) if str(row.get(key, "")) == str(value)),
                    None,
                )
                if index is None:
                    merged.append(dict(record))
                else:
                    merged[index] = dict(record)
        return merged

    def _upsert_by_key(self, sheet: str, key: str, value: str, record: Mapping[str, Any]) -> None:
        payload = dict(record)
        if sheet in IMMEDIATE_SHEETS:
            self._upsert_now(sheet, key, str(value), payload)
            return
        self._init_write_buffer()
        with self._buffer_lock:
            self._pending_upserts[(sheet, str(key), str(value))] = payload
            self._arm_flush_timer_locked()
            self._maybe_flush_locked()

    def _delete_by_key(self, sheet: str, key: str, value: str) -> None:
        ws = self.worksheets[sheet]
        records = retry_sheets_call(partial(ws.get_all_records, default_blank=""))
        for index in range(len(records), 0, -1):
            if str(records[index - 1].get(key, "")) == str(value):
                retry_sheets_call(partial(ws.delete_rows, index + 1))

    def delete_login_session(self, token_hash: str) -> None:
        self.flush()
        LoginSessionMixin.delete_login_session(self, token_hash)

    def purge_session_transcript(self, session_id: str) -> None:
        sid = str(session_id or "")
        if not sid:
            return
        dropper = getattr(self, "_drop_buffered_session", None)
        if callable(dropper):
            dropper(sid)
        flusher = getattr(self, "flush", None)
        if callable(flusher):
            flusher()
        self._delete_by_key("ChatLogs", "session_id", sid)
        self._delete_by_key("Assessments", "session_id", sid)
        self._delete_by_key("SkillEvents", "session_id", sid)

    def save_anonymous_transcript(self, session: Mapping[str, Any], turns: Sequence[Mapping[str, Any]]) -> str:
        anon_id = str(uuid.uuid4())
        self.append("AnonymousSessions", {
            "anonymous_session_id": anon_id,
            "started_at": session.get("started_at", ""),
            "ended_at": session.get("ended_at", ""),
            "duration_seconds": session.get("duration_seconds", ""),
            "mode": session.get("mode", ""),
            "school_id": session.get("school_id", ""),
            "selected_techniques": session.get("selected_techniques", []),
            "selected_technique_names": session.get("selected_technique_names", []),
            "theme": session.get("theme", ""),
            "difficulty": session.get("difficulty", ""),
            "model_name": session.get("model_name", ""),
            "prompt_version": session.get("prompt_version", ""),
            "created_at": self.now(),
        })
        for turn in turns:
            self.append("AnonymousChatLogs", {
                "turn_id": str(uuid.uuid4()),
                "anonymous_session_id": anon_id,
                "turn_index": turn.get("turn_index", ""),
                "speaker_role": turn.get("speaker_role", ""),
                "content_raw": turn.get("content_raw", ""),
                "nonverbal_cues": turn.get("nonverbal_cues", []),
                "timestamp": turn.get("timestamp", ""),
                "latency_ms": turn.get("latency_ms", ""),
                "error_flag": turn.get("error_flag", ""),
            })
        flusher = getattr(self, "flush", None)
        if callable(flusher):
            flusher()
        return anon_id

    def anonymous_session_turns(self, anonymous_session_id: str) -> list[dict[str, Any]]:
        sid = str(anonymous_session_id or "")
        rows = [
            row for row in self.all_records("AnonymousChatLogs")
            if str(row.get("anonymous_session_id")) == sid
        ]
        return sorted(rows, key=lambda row: int(row.get("turn_index", 0) or 0))

    def get_or_create_participant(self, email: str, role: str, participant_salt: str) -> str:
        normalized = email.strip().lower()
        records = self.all_records("IdentityMap")
        existing = next((r for r in records if str(r.get("email", "")).lower() == normalized), None)
        if existing:
            participant_id = str(existing["participant_id"])
            self._upsert_by_key("IdentityMap", "participant_id", participant_id, {
                **existing, "last_login_at": self.now(), "role": role,
            })
            return participant_id
        digest = hashlib.sha256(f"{participant_salt}:{normalized}".encode("utf-8")).hexdigest()[:12]
        participant_id = f"P-{digest.upper()}"
        self.append("IdentityMap", {
            "participant_id": participant_id,
            "email": normalized,
            "created_at": self.now(),
            "last_login_at": self.now(),
            "role": role,
        })
        return participant_id

    def start_session(self, session: Mapping[str, Any]) -> None:
        self.append("Sessions", session)

    def finish_session(self, session: Mapping[str, Any]) -> None:
        self._upsert_by_key("Sessions", "session_id", str(session["session_id"]), session)
        flusher = getattr(self, "flush", None)
        if callable(flusher):
            flusher()

    def append_turn(self, turn: Mapping[str, Any]) -> None:
        self.append("ChatLogs", turn)

    def save_thread(self, thread: Mapping[str, Any]) -> None:
        self._upsert_by_key(
            "Threads", "conversation_thread_id", str(thread["conversation_thread_id"]), thread
        )

    def list_threads(self, participant_id: str) -> list[dict[str, Any]]:
        rows = [
            r for r in self.all_records("Threads")
            if str(r.get("participant_id")) == participant_id and str(r.get("status", "active")) == "active"
        ]
        rows.sort(key=lambda r: str(r.get("updated_at", "")), reverse=True)
        return rows

    def save_assessment(self, record: Mapping[str, Any]) -> None:
        self.append("Assessments", record)
        for event in parse_json_cell(record.get("skill_events"), []):
            self.append("SkillEvents", {
                "assessment_id": record.get("assessment_id", ""),
                "session_id": record.get("session_id", ""),
                "participant_id": record.get("participant_id", ""),
                **event,
            })
        flusher = getattr(self, "flush", None)
        if callable(flusher):
            flusher()

    def get_settings(self) -> dict[str, str]:
        return {str(r.get("key")): str(r.get("value")) for r in self.all_records("Settings")}

    def save_setting(self, key: str, value: Any, updated_by: str) -> None:
        self._upsert_by_key("Settings", "key", key, {
            "key": key, "value": json_cell(value), "updated_at": self.now(), "updated_by": updated_by,
        })

    def count_sessions(self, participant_id: str) -> int:
        return sum(1 for r in self.all_records("Sessions") if str(r.get("participant_id")) == participant_id)

    def session_turns(self, session_id: str) -> list[dict[str, Any]]:
        rows = [r for r in self.all_records("ChatLogs") if str(r.get("session_id")) == session_id]
        return sorted(rows, key=lambda r: int(r.get("turn_index", 0) or 0))

    def get_assessment(self, session_id: str) -> dict[str, Any] | None:
        rows = [r for r in self.all_records("Assessments") if str(r.get("session_id")) == session_id]
        return rows[-1] if rows else None

    def add_teacher_grade(self, session_id: str, participant_id: str, teacher_email: str, score: int | None, comment: str) -> None:
        self.append("TeacherGrades", {
            "grade_id": str(uuid.uuid4()),
            "session_id": session_id,
            "participant_id": participant_id,
            "teacher_email": teacher_email,
            "teacher_score": "" if score is None else score,
            "teacher_comment": comment,
            "created_at": self.now(),
        })


class MemoryStore(WhitelistMixin, LoginSessionMixin):
    """僅供單元測試；重新整理或換使用者後資料不保留。"""

    def __init__(self, timezone: str):
        self.timezone = timezone
        self.rows = {name: [] for name in SCHEMAS}
        for key, value in DEFAULT_SETTINGS.items():
            self.rows["Settings"].append({"key": key, "value": value, "updated_at": self.now(), "updated_by": "system"})

    def now(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")

    def append(self, sheet: str, record: Mapping[str, Any]) -> None:
        self.rows[sheet].append(dict(record))

    def all_records(self, sheet: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows[sheet]]

    def _upsert_by_key(self, sheet: str, key: str, value: str, record: Mapping[str, Any]) -> None:
        for i, row in enumerate(self.rows[sheet]):
            if str(row.get(key)) == str(value):
                self.rows[sheet][i] = dict(record)
                return
        self.append(sheet, record)

    def _delete_by_key(self, sheet: str, key: str, value: str) -> None:
        self.rows[sheet] = [row for row in self.rows[sheet] if str(row.get(key)) != str(value)]

    get_or_create_participant = GoogleSheetsStore.get_or_create_participant
    start_session = GoogleSheetsStore.start_session
    finish_session = GoogleSheetsStore.finish_session
    append_turn = GoogleSheetsStore.append_turn
    save_thread = GoogleSheetsStore.save_thread
    list_threads = GoogleSheetsStore.list_threads
    save_assessment = GoogleSheetsStore.save_assessment
    get_settings = GoogleSheetsStore.get_settings
    save_setting = GoogleSheetsStore.save_setting
    count_sessions = GoogleSheetsStore.count_sessions
    session_turns = GoogleSheetsStore.session_turns
    get_assessment = GoogleSheetsStore.get_assessment
    add_teacher_grade = GoogleSheetsStore.add_teacher_grade
    purge_session_transcript = GoogleSheetsStore.purge_session_transcript
    save_anonymous_transcript = GoogleSheetsStore.save_anonymous_transcript
    anonymous_session_turns = GoogleSheetsStore.anonymous_session_turns


class SqliteStore(WhitelistMixin, LoginSessionMixin):
    """Persistent login list and account chat. API keys must never be written here."""

    def __init__(self, path: str, timezone: str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.timezone = timezone
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def now(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")

    def _quoted(self, name: str) -> str:
        if name not in SCHEMAS:
            raise KeyError(name)
        return '"' + name.replace('"', "") + '"'

    def ensure_schema(self) -> None:
        with self.conn:
            for name, headers in SCHEMAS.items():
                cols = ", ".join(f'"{header}" TEXT' for header in headers)
                self.conn.execute(f"CREATE TABLE IF NOT EXISTS {self._quoted(name)} ({cols})")
                existing = {
                    str(row[1]) for row in self.conn.execute(f"PRAGMA table_info({self._quoted(name)})")
                }
                for header in headers:
                    if header not in existing:
                        self.conn.execute(
                            f"ALTER TABLE {self._quoted(name)} ADD COLUMN \"{header}\" TEXT"
                        )
        settings = self.all_records("Settings")
        if not settings:
            for key, value in DEFAULT_SETTINGS.items():
                self.append("Settings", {
                    "key": key, "value": value, "updated_at": self.now(), "updated_by": "system",
                })

    def append(self, sheet: str, record: Mapping[str, Any]) -> None:
        headers = SCHEMAS[sheet]
        placeholders = ", ".join("?" for _ in headers)
        columns = ", ".join(f'"{header}"' for header in headers)
        values = [json_cell(record.get(key, "")) for key in headers]
        with self.conn:
            self.conn.execute(
                f"INSERT INTO {self._quoted(sheet)} ({columns}) VALUES ({placeholders})",
                values,
            )

    def all_records(self, sheet: str) -> list[dict[str, Any]]:
        headers = SCHEMAS[sheet]
        rows = self.conn.execute(f"SELECT * FROM {self._quoted(sheet)}").fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            mapping = dict(row)
            results.append({header: mapping.get(header, "") if mapping.get(header) is not None else "" for header in headers})
        return results

    def _upsert_by_key(self, sheet: str, key: str, value: str, record: Mapping[str, Any]) -> None:
        headers = SCHEMAS[sheet]
        existing = self.conn.execute(
            f"SELECT 1 FROM {self._quoted(sheet)} WHERE \"{key}\" = ? LIMIT 1",
            (str(value),),
        ).fetchone()
        payload = {header: json_cell(record.get(header, "")) for header in headers}
        payload[key] = json_cell(value) if key in headers else payload.get(key, json_cell(value))
        if existing is None:
            self.append(sheet, record)
            return
        assignments = ", ".join(f'"{header}" = ?' for header in headers if header != key)
        values = [payload[header] for header in headers if header != key]
        values.append(str(value))
        with self.conn:
            self.conn.execute(
                f"UPDATE {self._quoted(sheet)} SET {assignments} WHERE \"{key}\" = ?",
                values,
            )

    def _delete_by_key(self, sheet: str, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                f"DELETE FROM {self._quoted(sheet)} WHERE \"{key}\" = ?",
                (str(value),),
            )

    get_or_create_participant = GoogleSheetsStore.get_or_create_participant
    start_session = GoogleSheetsStore.start_session
    finish_session = GoogleSheetsStore.finish_session
    append_turn = GoogleSheetsStore.append_turn
    save_thread = GoogleSheetsStore.save_thread
    list_threads = GoogleSheetsStore.list_threads
    save_assessment = GoogleSheetsStore.save_assessment
    get_settings = GoogleSheetsStore.get_settings
    save_setting = GoogleSheetsStore.save_setting
    count_sessions = GoogleSheetsStore.count_sessions
    session_turns = GoogleSheetsStore.session_turns
    get_assessment = GoogleSheetsStore.get_assessment
    add_teacher_grade = GoogleSheetsStore.add_teacher_grade
    purge_session_transcript = GoogleSheetsStore.purge_session_transcript
    save_anonymous_transcript = GoogleSheetsStore.save_anonymous_transcript
    anonymous_session_turns = GoogleSheetsStore.anonymous_session_turns

