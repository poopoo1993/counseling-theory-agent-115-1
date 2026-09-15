"""Persistent research/login store. Production uses SQLite; Sheets code remains unused.

API Key 永遠不會傳入此模組。原始逐輪內容只新增、不覆寫。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .config import DEFAULT_SETTINGS


SCHEMAS: dict[str, list[str]] = {
    "whitelist": ["email", "role", "enabled", "created_at"],
    "IdentityMap": ["participant_id", "email", "created_at", "last_login_at", "role"],
    "Sessions": [
        "session_id", "conversation_thread_id", "participant_id", "agent_type", "mode",
        "continuation_role", "started_at", "ended_at", "duration_seconds", "case_id",
        "school_id", "selected_techniques", "selected_technique_names", "model_name",
        "prompt_version", "temperature", "completion_status", "theme", "difficulty",
    ],
    "ChatLogs": [
        "turn_id", "session_id", "conversation_thread_id", "participant_id", "turn_index",
        "speaker_role", "speaker_id", "content_raw", "nonverbal_cues", "timestamp",
        "stage_at_turn", "skill_labels", "selected_skill_match", "latency_ms", "error_flag",
    ],
    "Threads": [
        "conversation_thread_id", "participant_id", "mode", "continuation_role", "school_id",
        "school_name", "selected_techniques", "selected_technique_names", "case_id", "case_data",
        "counseling_plan", "chat_analysis", "latest_snapshot", "last_session_id",
        "recent_turns", "updated_at", "status",
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
}


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
        })

    def seed_whitelist(self, login_allowlist: tuple[str, ...], teacher_emails: tuple[str, ...]) -> None:
        teachers = tuple(str(item).strip().lower() for item in teacher_emails if str(item).strip())
        allow = tuple(str(item).strip().lower() for item in login_allowlist if str(item).strip())
        for email in teachers:
            existing = self._whitelist_row(email)
            enabled = _flag_enabled(existing.get("enabled", "true")) if existing else True
            self.upsert_whitelist(email, "teacher", enabled)
        for email in allow:
            if email in teachers or self._whitelist_row(email):
                continue
            self.upsert_whitelist(email, "student", True)

    def list_whitelist(self) -> list[dict[str, Any]]:
        rows = self.all_records("whitelist")
        rows.sort(key=lambda r: str(r.get("email", "")))
        return rows


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


class GoogleSheetsStore(WhitelistMixin):
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
        self.book = client.open_by_key(spreadsheet_id)
        self.timezone = timezone
        self.worksheets: dict[str, Any] = {}
        self.ensure_schema()

    @classmethod
    def from_secrets(cls, secrets: Mapping[str, Any], timezone: str) -> "GoogleSheetsStore":
        # Preferred compatibility path: same syntax as the existing group /
        # helping-skills Agents.
        spreadsheet_id = str(secrets.get("SPREADSHEET_ID", "")).strip()
        service_json = secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        service_account: Mapping[str, Any] | dict[str, Any] = {}
        if service_json:
            if isinstance(service_json, Mapping):
                service_account = dict(service_json)
            else:
                try:
                    parsed = json.loads(str(service_json))
                except json.JSONDecodeError:
                    raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON 必須是完整 JSON。") from None
                if not isinstance(parsed, dict):
                    raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON 必須是 JSON 物件。")
                service_account = parsed

        # Current nested syntax remains supported for existing deployments.
        block = secrets.get("google_sheets", {})
        if not isinstance(block, Mapping):
            block = {}
        if not spreadsheet_id:
            spreadsheet_id = str(block.get("spreadsheet_id", "")).strip()
        if not service_account:
            nested_service = block.get("service_account", {})
            if isinstance(nested_service, Mapping):
                service_account = nested_service

        # Older deployments used a top-level [gcp_service_account] section.
        if not service_account:
            legacy_service = secrets.get("gcp_service_account", {})
            if isinstance(legacy_service, Mapping):
                service_account = legacy_service
        if not spreadsheet_id or not service_account:
            raise RuntimeError(
                "尚未設定 SPREADSHEET_ID／GOOGLE_SERVICE_ACCOUNT_JSON，"
                "或 google_sheets／gcp_service_account 相容欄位。"
            )
        return cls(spreadsheet_id, service_account, timezone)

    def now(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")

    def ensure_schema(self) -> None:
        existing = {ws.title: ws for ws in self.book.worksheets()}
        for name, headers in SCHEMAS.items():
            ws = existing.get(name)
            if ws is None:
                ws = self.book.add_worksheet(title=name, rows=1000, cols=max(20, len(headers) + 2))
                ws.append_row(headers, value_input_option="RAW")
                ws.freeze(rows=1)
            else:
                current = ws.row_values(1)
                if not current:
                    ws.append_row(headers, value_input_option="RAW")
                    ws.freeze(rows=1)
                elif current != headers:
                    missing = [h for h in headers if h not in current]
                    if missing:
                        ws.update(values=[current + missing], range_name="A1")
            self.worksheets[name] = ws
        settings = self.all_records("Settings")
        if not settings:
            for key, value in DEFAULT_SETTINGS.items():
                self.append("Settings", {"key": key, "value": value, "updated_at": self.now(), "updated_by": "system"})

    def append(self, sheet: str, record: Mapping[str, Any]) -> None:
        headers = SCHEMAS[sheet]
        values = [json_cell(record.get(key, "")) for key in headers]
        self.worksheets[sheet].append_row(values, value_input_option="RAW")

    def all_records(self, sheet: str) -> list[dict[str, Any]]:
        return self.worksheets[sheet].get_all_records(default_blank="")

    def _upsert_by_key(self, sheet: str, key: str, value: str, record: Mapping[str, Any]) -> None:
        ws = self.worksheets[sheet]
        headers = SCHEMAS[sheet]
        records = ws.get_all_records(default_blank="")
        row_index = next((i + 2 for i, row in enumerate(records) if str(row.get(key, "")) == str(value)), None)
        values = [json_cell(record.get(header, "")) for header in headers]
        if row_index is None:
            ws.append_row(values, value_input_option="RAW")
        else:
            ws.update(values=[values], range_name=f"A{row_index}")

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


class MemoryStore(WhitelistMixin):
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


class SqliteStore(WhitelistMixin):
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

