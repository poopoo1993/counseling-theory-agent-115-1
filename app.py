from __future__ import annotations

import io
import time
import uuid
import zipfile
from datetime import datetime
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from src.auth import (
    BROWSER_SESSION_QUERY_KEY,
    BROWSER_SESSION_TTL_SECONDS,
    MIN_PASSWORD_LENGTH,
    create_otp,
    hash_browser_session_token,
    hash_password,
    is_email_allowed,
    is_teacher,
    new_browser_session_token,
    normalize_email,
    send_otp_email,
    verify_otp,
    verify_password,
)
from src.config import AppConfig, DEFAULT_SETTINGS, as_bool
from src.data_store import (
    SCHEMAS,
    GoogleSheetsStore,
    SqliteStore,
    choose_store_backend,
    load_sheets_credentials,
    parse_json_cell,
    public_store_error_message,
    require_sheets_enabled,
)
from src.browser_keys import render_saved_api_keys
from src.quota_meter import sync_quota_events
from src.gemini_client import GeminiService, parse_json_response
from src.gemini_quota import EVENTS_KEY, merge_events, snapshot as quota_snapshot
from src.gemini_router import GeminiRouterPending, keep_gemini_router_alive, run_browser_jobs
from src.llm_pipeline import (
    build_analyze_job,
    build_chat_job,
    build_eval_snapshot_job,
    build_plan_job,
    build_thought_job,
)
from src.prompts import (
    case_data_from_plan,
    live_plan_visible,
    thought_coach_visible,
    turn_review_visible,
    uses_planner_llm,
)
from src import session_flow as flow
from src.safety import detect_immediate_risk, detect_pii, redact_for_preview, safety_message
from src.session_service import finish_session, new_session, new_turn
from src.theory_library import PRACTICE_THEMES, SCHOOLS, get_school, get_techniques, validate_selected_techniques
from src.transcript import make_transcript_txt, safe_filename
from src.ui import (
    ROLE_LABELS,
    apply_theme,
    mode_label,
    render_chips,
    render_coaching_panel,
    render_empty_state,
    render_masthead,
    render_meta_grid,
    render_online_badge,
    render_quote,
    render_role_callout,
    render_safety_notice,
    render_technique_cards,
    render_thought_log,
    render_transcript,
    render_user_card,
)

st.set_page_config(
    page_title="諮商理論技巧訓練 Agent",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


def secrets_dict() -> dict[str, Any]:
    try:
        return st.secrets.to_dict()
    except Exception:
        return {}


SECRETS = secrets_dict()
CONFIG = AppConfig.from_secrets(SECRETS)


def initialize_state() -> None:
    defaults = {
        "authenticated": False,
        "email": "",
        "participant_id": "",
        "view": "student",
        "api_key": "",
        "api_validated": False,
        "active_session": None,
        "turns": [],
        "case_data": None,
        "counseling_plan": None,
        "chat_analysis": None,
        "turn_reviews": [],
        "coach_thoughts": [],
        "continuation_snapshot": None,
        "prior_turns_context": [],
        "assessment": None,
        "raw_assessment": "",
        "otp_hash": "",
        "otp_expires": 0.0,
        "otp_email": "",
        "otp_last_sent": 0.0,
        "pending_password_email": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()
st.session_state["_gemini_router_mounted"] = False


STORE_SCHEMA_VERSION = "anonymous-tables-1"
ONLINE_TOUCH_INTERVAL_SECONDS = 60


@st.cache_resource(show_spinner=False)
def build_sqlite_store(sqlite_path: str, timezone: str, schema_version: str):
    return SqliteStore(sqlite_path, timezone)


@st.cache_resource(show_spinner=False)
def build_sheets_store(spreadsheet_id: str, timezone: str, schema_version: str):
    return GoogleSheetsStore.from_secrets(SECRETS, timezone)


def get_store():
    backend = choose_store_backend(SECRETS)
    store = st.session_state.get("data_store")
    if backend == "sheets":
        try:
            spreadsheet_id, _ = load_sheets_credentials(SECRETS)
        except Exception as exc:
            if require_sheets_enabled(SECRETS):
                raise RuntimeError(
                    "REQUIRE_SHEETS 已開啟，但尚未設定可用的試算表 Secrets。"
                ) from exc
            backend = "sqlite"
        else:
            needs_new = (
                store is None
                or not isinstance(store, GoogleSheetsStore)
                or not hasattr(store, "save_anonymous_transcript")
                or not hasattr(store, "create_login_session")
            )
            if needs_new:
                try:
                    store = build_sheets_store(spreadsheet_id, CONFIG.timezone, STORE_SCHEMA_VERSION)
                    if not hasattr(store, "save_anonymous_transcript") or not hasattr(store, "create_login_session"):
                        build_sheets_store.clear()
                        store = build_sheets_store(spreadsheet_id, CONFIG.timezone, STORE_SCHEMA_VERSION)
                except Exception as exc:
                    if require_sheets_enabled(SECRETS):
                        raise RuntimeError(public_store_error_message(exc)) from exc
                    st.session_state.store_error = public_store_error_message(exc)
                    backend = "sqlite"
                    store = None
            if backend == "sheets" and store is not None:
                try:
                    store.ensure_schema()
                    store.seed_whitelist(CONFIG.login_allowlist, CONFIG.teacher_emails)
                except Exception as exc:
                    if require_sheets_enabled(SECRETS):
                        raise RuntimeError(public_store_error_message(exc)) from exc
                    st.session_state.store_error = public_store_error_message(exc)
                    backend = "sqlite"
                    store = None
                else:
                    st.session_state.store_mode = "sheets"
                    st.session_state.store_error = ""
                    st.session_state.data_store = store
                    return store

    app = SECRETS.get("app", {}) if isinstance(SECRETS.get("app"), dict) else {}
    sqlite_path = str(app.get("sqlite_path", "data/app.sqlite")).strip() or "data/app.sqlite"
    store = st.session_state.get("data_store")
    if store is None or not isinstance(store, SqliteStore) or not hasattr(store, "save_anonymous_transcript"):
        store = build_sqlite_store(sqlite_path, CONFIG.timezone, STORE_SCHEMA_VERSION)
        if not hasattr(store, "save_anonymous_transcript"):
            build_sqlite_store.clear()
            store = build_sqlite_store(sqlite_path, CONFIG.timezone, STORE_SCHEMA_VERSION)
    store.ensure_schema()
    store.seed_whitelist(CONFIG.login_allowlist, CONFIG.teacher_emails)
    st.session_state.store_mode = "sqlite"
    st.session_state.data_store = store
    return store


STORE = None
try:
    STORE = get_store()
except Exception as exc:
    st.error(public_store_error_message(exc))
    st.info("這不是帳號或密碼錯誤；是 App 讀取登入／研究資料表失敗。請稍候約一分鐘後重新整理。")
    st.stop()


def _browser_sid() -> str:
    raw = st.query_params.get(BROWSER_SESSION_QUERY_KEY)
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return str(raw or "").strip()


def _clear_browser_sid() -> None:
    try:
        del st.query_params[BROWSER_SESSION_QUERY_KEY]
    except (KeyError, Exception):
        pass


def restore_browser_session() -> None:
    """Refresh wipes Streamlit memory; a hashed URL token restores login only."""
    if st.session_state.authenticated:
        return
    token = _browser_sid()
    if not token:
        return
    digest = hash_browser_session_token(token)
    row = STORE.get_login_session(digest)
    if not row:
        _clear_browser_sid()
        return
    email = normalize_email(str(row.get("email", "")))
    if not is_email_allowed(email, STORE):
        STORE.delete_login_session(digest)
        _clear_browser_sid()
        return
    role = STORE.get_whitelist_role(email) or str(row.get("role") or "student")
    participant_id = STORE.get_or_create_participant(email, role, participant_salt())
    st.session_state.authenticated = True
    st.session_state.email = email
    st.session_state.participant_id = participant_id
    st.session_state.view = "teacher" if role == "teacher" else "student"


def participant_salt() -> str:
    auth = SECRETS.get("auth", {})
    app = SECRETS.get("app", {})
    value = str(auth.get("participant_salt", app.get("participant_salt", ""))).strip()
    return value or "local-demo-change-this-salt"


def smtp_secrets() -> dict[str, Any]:
    """Support both the new [smtp] and existing Agent [email] syntax."""
    value = SECRETS.get("smtp") or SECRETS.get("email") or {}
    return dict(value) if isinstance(value, dict) else value


def local_demo_enabled() -> bool:
    return as_bool(SECRETS.get("app", {}).get("local_demo_mode", False))


def account_is_teacher(email: str | None = None) -> bool:
    value = email if email is not None else str(st.session_state.get("email", ""))
    return is_teacher(value, STORE, CONFIG.teacher_emails)


def persist_thread_state(status: str = "in_progress", *, include_turns: bool = True) -> None:
    session = st.session_state.active_session
    if not session:
        return
    last_session_id = session["session_id"]
    if include_turns:
        recent = (st.session_state.prior_turns_context + st.session_state.turns)[-6:]
        analysis = st.session_state.chat_analysis or {}
        case_data = st.session_state.case_data or {}
        plan = st.session_state.counseling_plan or {}
    else:
        recent = list(st.session_state.prior_turns_context or [])[-6:]
        analysis = {}
        case_data = {}
        plan = {}
        last_session_id = ""
        existing = _find_thread(str(session["conversation_thread_id"]))
        previous = str((existing or {}).get("last_session_id") or "")
        if previous and previous != str(session["session_id"]):
            last_session_id = previous
    STORE.save_thread({
        "conversation_thread_id": session["conversation_thread_id"],
        "participant_id": session["participant_id"],
        "mode": session["mode"],
        "continuation_role": session["continuation_role"],
        "school_id": session["school_id"],
        "school_name": session["school_name"],
        "selected_techniques": session["selected_techniques"],
        "selected_technique_names": session["selected_technique_names"],
        "case_id": session.get("case_id", ""),
        "case_data": case_data,
        "counseling_plan": plan,
        "chat_analysis": analysis,
        "latest_snapshot": st.session_state.continuation_snapshot or {},
        "last_session_id": last_session_id,
        "recent_turns": recent,
        "difficulty": session.get("difficulty", ""),
        "updated_at": STORE.now(),
        "status": status,
    })


def logout() -> None:
    flusher = getattr(STORE, "flush", None)
    if callable(flusher):
        try:
            flusher()
        except Exception:
            pass
    token = _browser_sid()
    if token:
        STORE.delete_login_session(hash_browser_session_token(token))
    _clear_browser_sid()
    for key in list(st.session_state.keys()):
        if key not in {"data_store", "store_mode", "store_error"}:
            del st.session_state[key]
    st.rerun()


def render_header(show_notice: bool = True) -> None:
    render_masthead(CONFIG.app_title, "11 學派 · 體驗與實作 · 跨次續談 · 形成性回饋")
    if show_notice:
        render_safety_notice()


def show_online_people() -> None:
    if st.session_state.get("authenticated"):
        token = _browser_sid()
        if token:
            now = time.time()
            last = float(st.session_state.get("_online_touch_at") or 0)
            if now - last >= ONLINE_TOUCH_INTERVAL_SECONDS:
                STORE.touch_login_session(hash_browser_session_token(token))
                st.session_state._online_touch_at = now
    try:
        people = STORE.list_online_users()
    except Exception:
        people = []
    local_events = st.session_state.get(EVENTS_KEY) or []
    synced = sync_quota_events(local_events)
    st.session_state[EVENTS_KEY] = merge_events(local_events, synced, now=time.time())
    quota = quota_snapshot(
        st.session_state[EVENTS_KEY],
        now=time.time(),
        rpm_limit=CONFIG.gemini_free_rpm,
        rpd_limit=CONFIG.gemini_free_rpd,
        tpm_limit=CONFIG.gemini_free_tpm,
    )
    render_online_badge(
        people,
        show_people=bool(st.session_state.get("authenticated")),
        quota=quota,
    )


if hasattr(st, "fragment"):
    show_online_people = st.fragment(run_every=15)(show_online_people)


def complete_login(email: str) -> None:
    role = STORE.get_whitelist_role(email) or (
        "teacher" if account_is_teacher(email) else "student"
    )
    participant_id = STORE.get_or_create_participant(email, role, participant_salt())
    token = new_browser_session_token()
    STORE.create_login_session(
        hash_browser_session_token(token),
        email,
        participant_id,
        role,
        BROWSER_SESSION_TTL_SECONDS,
    )
    st.query_params[BROWSER_SESSION_QUERY_KEY] = token
    st.session_state.authenticated = True
    st.session_state.email = email
    st.session_state.participant_id = participant_id
    st.session_state.view = "teacher" if role == "teacher" else "student"
    st.session_state.pending_password_email = ""
    st.rerun()


def password_setup_page() -> None:
    apply_theme("login")
    show_online_people()
    render_header()
    email = normalize_email(st.session_state.pending_password_email)
    with st.container(border=True):
        st.markdown('<p class="ct-kicker">設定密碼</p>', unsafe_allow_html=True)
        st.markdown("**首次登入請設定密碼，之後即可用密碼登入。**")
        st.caption(f"帳號：{email}")
        password = st.text_input("新密碼", type="password")
        confirm = st.text_input("再次輸入密碼", type="password")
        if st.button("儲存密碼並進入", type="primary", use_container_width=True):
            if len(password or "") < MIN_PASSWORD_LENGTH:
                st.error(f"密碼至少 {MIN_PASSWORD_LENGTH} 個字元。")
            elif password != confirm:
                st.error("兩次輸入的密碼不一致。")
            elif not is_email_allowed(email, STORE):
                st.error("此信箱不在登入白名單中。")
                st.session_state.pending_password_email = ""
                st.rerun()
            else:
                STORE.set_password_hash(email, hash_password(password))
                complete_login(email)


def login_page() -> None:
    apply_theme("login")
    show_online_people()
    render_header()
    with st.container(border=True):
        st.markdown('<p class="ct-kicker">白名單登入</p>', unsafe_allow_html=True)
        st.markdown("**已設定密碼者可直接登入；首次請先用驗證碼。**")
        st.caption("僅白名單信箱可登入。若尚未列入，請先向授課教師申請。")
        email = normalize_email(st.text_input("登入 Email", value=st.session_state.otp_email))
        password = st.text_input("密碼", type="password")
        if st.button("使用密碼登入", type="primary", use_container_width=True):
            if not is_email_allowed(email, STORE):
                st.error("此信箱不在登入白名單中。請向授課教師申請。")
            elif not STORE.has_login_password(email):
                st.error("此帳號尚未設定密碼。請先用驗證碼登入並設定密碼。")
            elif not verify_password(password, STORE.get_password_hash(email)):
                st.error("密碼不正確。")
            else:
                complete_login(email)
        st.divider()
        st.markdown("**首次登入或忘記密碼：寄送驗證碼**")
        if st.button("寄送驗證碼", use_container_width=True):
            if not is_email_allowed(email, STORE):
                st.error("此信箱不在登入白名單中。請向授課教師申請。")
            elif time.time() - float(st.session_state.otp_last_sent or 0) < 60:
                st.error("請等待 60 秒後再重新寄送驗證碼。")
            else:
                code, digest, expires = create_otp(CONFIG.otp_ttl_seconds)
                try:
                    if local_demo_enabled():
                        st.info(f"本機測試驗證碼：{code}")
                    else:
                        send_otp_email(email, code, smtp_secrets())
                    st.session_state.otp_hash = digest
                    st.session_state.otp_expires = expires
                    st.session_state.otp_email = email
                    st.session_state.otp_last_sent = time.time()
                    st.success("驗證碼已寄出，請查看收件匣與垃圾郵件匣。")
                except Exception as exc:
                    st.error(f"驗證碼寄送失敗：{exc}")
        otp = st.text_input("六位數驗證碼", max_chars=6, placeholder="000000")
        if st.button("驗證並繼續", use_container_width=True):
            if email != st.session_state.otp_email:
                st.error("目前輸入的 Email 與接收驗證碼的 Email 不同。")
            elif not is_email_allowed(email, STORE):
                st.error("此信箱不在登入白名單中。")
            elif not verify_otp(otp, st.session_state.otp_hash, st.session_state.otp_expires):
                st.error("驗證碼錯誤或已逾時。")
            elif STORE.has_login_password(email):
                complete_login(email)
            else:
                st.session_state.pending_password_email = email
                st.rerun()


def sidebar() -> None:
    with st.sidebar:
        role_label = "教師" if account_is_teacher() else "學生"
        render_user_card(st.session_state.email, st.session_state.participant_id, role_label)
        if account_is_teacher():
            st.session_state.view = st.radio(
                "使用介面",
                ["student", "teacher"],
                format_func=lambda x: "學生模擬端" if x == "student" else "教師後台",
                index=0 if st.session_state.view == "student" else 1,
            )
        st.markdown("**兩個帳號的用途**")
        st.caption("學校信箱：登入本系統。")
        st.caption("個人 Gmail：到 Google AI Studio 申請自己的 Gemini API Key。")
        st.divider()
        if st.button("登出", use_container_width=True):
            logout()


def settings_with_defaults() -> dict[str, str]:
    values = dict(DEFAULT_SETTINGS)
    try:
        values.update(STORE.get_settings())
    except Exception:
        pass
    return values


def parse_local_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(CONFIG.timezone))
    return parsed


def student_access_error(settings: dict[str, str]) -> str | None:
    if not as_bool(settings.get("system_enabled"), True):
        return "目前系統未開放。"
    now = datetime.now(ZoneInfo(CONFIG.timezone))
    try:
        start = parse_local_datetime(settings.get("open_start", ""))
        end = parse_local_datetime(settings.get("open_end", ""))
    except ValueError:
        return "教師端開放時間格式錯誤，請通知授課教師。"
    if start and now < start:
        return f"系統將於 {start.isoformat(timespec='minutes')} 開放。"
    if end and now > end:
        return "本次練習開放時間已結束。"
    max_sessions = int(settings.get("max_sessions_per_student", "0") or 0)
    if max_sessions > 0 and STORE.count_sessions(st.session_state.participant_id) >= max_sessions:
        return f"你已達教師設定的 {max_sessions} 次使用上限。"
    return None


def api_key_gate() -> GeminiService | None:
    picked = st.session_state.pop("picked_api_key", "")
    if picked:
        st.session_state.api_key_draft = picked
        st.session_state.auto_test_api_key = True
    if "api_key_draft" not in st.session_state:
        st.session_state.api_key_draft = st.session_state.api_key
    with st.container(border=True):
        st.markdown('<p class="ct-kicker">開始前</p>', unsafe_allow_html=True)
        st.markdown("**連接你自己的 Gemini API Key**")
        st.caption(
            "請用個人的 @gmail.com 帳號到 Google AI Studio 申請 API Key。"
            "驗證成功後，Key 只會留在這個瀏覽器，不會寫入 SQLite、逐字稿或研究資料。"
            "共用電腦請點右側 × 刪除記住的 Key。"
        )
        st.link_button("前往 Google AI Studio", "https://aistudio.google.com/", use_container_width=True)
        key_col, action_col = st.columns([3.2, 1], gap="small", vertical_alignment="bottom")
        with key_col:
            key = st.text_input("Gemini API Key", type="password", key="api_key_draft")
        with action_col:
            tested = st.button("測試連線", type="primary", use_container_width=True)
        if st.session_state.pop("auto_test_api_key", False) and str(key or "").strip():
            tested = True
        if tested:
            st.session_state.pending_validate_key = str(key or "").strip()
            if not st.session_state.get("validate_call_id"):
                st.session_state.validate_call_id = f"validate-{uuid.uuid4().hex[:8]}"
        pending_key = str(st.session_state.get("pending_validate_key") or "").strip()
        if pending_key:
            try:
                service = GeminiService(
                    pending_key,
                    CONFIG.model_name,
                    fallback_models=CONFIG.fallback_models,
                    use_browser_router=True,
                )
                service.validate_key(call_id=str(st.session_state.get("validate_call_id") or "validate"))
                st.session_state.api_key = pending_key
                st.session_state.api_validated = True
                st.session_state.active_model_name = service.model_name
                st.session_state._pending_save_api_key = pending_key
                st.session_state.pending_validate_key = ""
                st.session_state.validate_call_id = ""
                render_saved_api_keys(save_key=pending_key)
                st.success("API Key 已驗證，可以開始練習。")
                st.rerun()
            except GeminiRouterPending:
                st.caption("正在由這個瀏覽器測試 Gemini 連線…")
            except Exception as exc:
                st.session_state.api_validated = False
                st.session_state.pending_validate_key = ""
                st.session_state.validate_call_id = ""
                st.error(str(exc))
        result = render_saved_api_keys()
        if result and result.get("ts") != st.session_state.get("_api_key_event_ts"):
            st.session_state._api_key_event_ts = result.get("ts")
            if result.get("action") == "select" and result.get("key"):
                st.session_state.picked_api_key = str(result["key"])
                st.rerun()
    return None


def _remember_model(name: str) -> None:
    st.session_state.active_model_name = name


def gemini() -> GeminiService:
    return GeminiService(
        st.session_state.api_key,
        str(st.session_state.get("active_model_name") or CONFIG.model_name),
        fallback_models=CONFIG.fallback_models,
        on_model_used=_remember_model,
        use_browser_router=True,
    )


def _session_in_progress() -> bool:
    session = st.session_state.get("active_session") or {}
    return bool(session) and str(session.get("completion_status") or "") == "in_progress"


def _has_ai_turn() -> bool:
    return any(str(turn.get("speaker_role") or "").startswith("ai_") for turn in (st.session_state.get("turns") or []))


def store_turn(turn: dict[str, Any]) -> None:
    st.session_state.turns.append(turn)
    STORE.append_turn(turn)


def _find_thread(thread_id: str) -> dict[str, Any] | None:
    wanted = str(thread_id or "").strip()
    if not wanted:
        return None
    try:
        rows = STORE.all_records("Threads")
    except Exception:
        return None
    for row in rows:
        if str(row.get("conversation_thread_id")) == wanted:
            return row
    return None


def _dialogue_turns() -> list[dict[str, Any]]:
    return list(st.session_state.prior_turns_context or []) + list(st.session_state.turns or [])


def _ending_session() -> bool:
    return flow.phase(st.session_state) == flow.ENDING or bool(st.session_state.get("pending_finalize"))


def _enqueue_opening_chat() -> None:
    session = st.session_state.active_session or {}
    session_id = str(session.get("session_id") or "")
    if not session_id or _has_ai_turn():
        return
    flow.set_phase(st.session_state, flow.OPENING)
    flow.enqueue(st.session_state, build_chat_job(
        mode=session["mode"],
        school_id=session["school_id"],
        selected_ids=session["selected_techniques"],
        turns=_dialogue_turns(),
        latest_student_message="",
        case_data=st.session_state.case_data,
        continuation_snapshot=st.session_state.continuation_snapshot,
        counseling_plan=st.session_state.counseling_plan,
        chat_analysis=st.session_state.chat_analysis,
        is_opening=True,
        request_id=f"chat-{session_id}-{len(st.session_state.turns or [])}",
        meta={"has_prior_turns": bool(st.session_state.prior_turns_context)},
    ))


def _reset_live_session_fields() -> None:
    st.session_state.turns = []
    st.session_state.turn_reviews = []
    st.session_state.coach_thoughts = []
    st.session_state.assessment = None
    st.session_state.raw_assessment = ""


def _commit_new_session(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    theme: str,
    difficulty: str,
    plan: dict[str, Any],
    case_data: dict[str, Any] | None,
    case_id: str,
) -> None:
    service = gemini()
    session = new_session(
        participant_id=st.session_state.participant_id,
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        model_name=service.model_name,
        prompt_version=CONFIG.prompt_version,
        timezone=CONFIG.timezone,
        theme=theme,
        difficulty=difficulty,
        case_id=case_id,
    )
    st.session_state.active_session = session
    _reset_live_session_fields()
    st.session_state.case_data = case_data
    st.session_state.counseling_plan = plan
    st.session_state.chat_analysis = None
    st.session_state.continuation_snapshot = None
    st.session_state.prior_turns_context = []
    STORE.start_session(session)
    persist_thread_state("in_progress")
    flow.set_phase(st.session_state, flow.OPENING)


def _commit_continuation(thread: dict[str, Any], selected_ids: list[str], *, plan: dict[str, Any] | None = None) -> None:
    mode = str(thread["mode"])
    school_id = str(thread["school_id"])
    prior_difficulty = str(thread.get("difficulty") or "").strip()
    difficulty = prior_difficulty if prior_difficulty and prior_difficulty != "延續前次" else "中階"
    service = gemini()
    session = new_session(
        participant_id=st.session_state.participant_id,
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        model_name=service.model_name,
        prompt_version=CONFIG.prompt_version,
        timezone=CONFIG.timezone,
        theme="續談上次議題",
        difficulty=difficulty,
        thread_id=str(thread["conversation_thread_id"]),
        case_id=str(thread.get("case_id", "student_topic")),
    )
    st.session_state.active_session = session
    _reset_live_session_fields()
    st.session_state.case_data = parse_json_cell(thread.get("case_data"), None)
    st.session_state.counseling_plan = plan if plan is not None else parse_json_cell(thread.get("counseling_plan"), {})
    st.session_state.chat_analysis = parse_json_cell(thread.get("chat_analysis"), {})
    st.session_state.continuation_snapshot = parse_json_cell(thread.get("latest_snapshot"), {})
    st.session_state.prior_turns_context = parse_json_cell(thread.get("recent_turns"), [])
    if mode == "practice" and plan is not None:
        st.session_state.case_data = case_data_from_plan(plan) or st.session_state.case_data
    STORE.start_session(session)
    persist_thread_state("in_progress")
    flow.set_phase(st.session_state, flow.OPENING)


def record_turn_review(student_turn_index: int, analysis: dict[str, Any] | None) -> None:
    review = (analysis or {}).get("turn_review")
    if not isinstance(review, dict):
        return
    comment = str(review.get("comment", "")).strip()
    verdict = str(review.get("verdict", "")).strip()
    goal = str(review.get("goal", "")).strip()
    effect = str(review.get("effect", "")).strip()
    if not comment and not verdict and not goal and not effect:
        return
    history = list(st.session_state.get("turn_reviews") or [])
    history = [item for item in history if int(item.get("turn_index") or 0) != student_turn_index]
    history.append({
        "turn_index": student_turn_index,
        "verdict": verdict,
        "comment": comment,
        "goal": str(review.get("goal", "")).strip(),
        "effect": str(review.get("effect", "")).strip(),
    })
    st.session_state.turn_reviews = history


def start_new_session(mode: str, school_id: str, selected_ids: list[str], theme: str, difficulty: str) -> None:
    validate_selected_techniques(school_id, selected_ids)
    if _session_in_progress():
        return
    flow.clear_jobs(st.session_state)
    flow.set_phase(st.session_state, flow.OPENING)
    if uses_planner_llm(mode, difficulty):
        flow.enqueue(st.session_state, build_plan_job(
            mode=mode,
            school_id=school_id,
            selected_ids=selected_ids,
            theme=theme,
            difficulty=difficulty,
            request_id=f"plan-new-{st.session_state.participant_id}-{mode}-{school_id}-{theme}-{difficulty}",
            meta={"flow": "new"},
        ))
        return
    _commit_new_session(
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        theme=theme,
        difficulty=difficulty,
        plan={"mode": mode, "school_id": school_id},
        case_data=None,
        case_id="student_topic",
    )
    _enqueue_opening_chat()


def start_continuation(thread: dict[str, Any], selected_ids: list[str]) -> None:
    mode = str(thread["mode"])
    school_id = str(thread["school_id"])
    validate_selected_techniques(school_id, selected_ids)
    thread_id = str(thread["conversation_thread_id"])
    if _session_in_progress() and str((st.session_state.active_session or {}).get("conversation_thread_id")) == thread_id:
        return
    prior_difficulty = str(thread.get("difficulty") or "").strip()
    difficulty = prior_difficulty if prior_difficulty and prior_difficulty != "延續前次" else "中階"
    flow.clear_jobs(st.session_state)
    flow.set_phase(st.session_state, flow.OPENING)
    if uses_planner_llm(mode, difficulty):
        flow.enqueue(st.session_state, build_plan_job(
            mode=mode,
            school_id=school_id,
            selected_ids=selected_ids,
            theme="續談上次議題",
            difficulty=difficulty,
            prior_snapshot=parse_json_cell(thread.get("latest_snapshot"), {}),
            prior_plan=parse_json_cell(thread.get("counseling_plan"), {}),
            prior_analysis=parse_json_cell(thread.get("chat_analysis"), {}),
            request_id=f"plan-cont-{thread_id}",
            meta={"flow": "continuation", "thread": dict(thread)},
        ))
        return
    _commit_continuation(thread, selected_ids)
    _enqueue_opening_chat()


def _analyze_turns(meta: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    count = int(meta.get("session_turn_count") or 0)
    session_turns = list(st.session_state.turns or [])[:max(0, count)]
    return session_turns, list(st.session_state.prior_turns_context or []) + session_turns


def _materialize_job(job: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(job.get("kind") or "")
    meta = dict(job.get("meta") or {})
    session = st.session_state.active_session or {}
    if kind == flow.KIND_PLAN:
        return flow.browser_jobs(job)
    if kind == flow.KIND_CHAT:
        rebuilt = build_chat_job(
            mode=session["mode"],
            school_id=session["school_id"],
            selected_ids=session["selected_techniques"],
            turns=_dialogue_turns(),
            latest_student_message=str(meta.get("latest_student_message") or ""),
            case_data=st.session_state.case_data,
            continuation_snapshot=st.session_state.continuation_snapshot,
            counseling_plan=st.session_state.counseling_plan,
            chat_analysis=st.session_state.chat_analysis,
            is_opening=bool(meta.get("is_opening")),
            request_id=str(job.get("request_id") or job.get("id") or ""),
            meta=meta,
        )
        return flow.browser_jobs(rebuilt)
    if kind == flow.KIND_ANALYZE:
        _session_turns, turns = _analyze_turns(meta)
        rebuilt = build_analyze_job(
            mode=session["mode"],
            school_id=session["school_id"],
            selected_ids=session["selected_techniques"],
            counseling_plan=st.session_state.counseling_plan,
            prior_analysis=st.session_state.chat_analysis,
            turns=turns,
            latest_student_message=str(meta.get("latest_student_message") or ""),
            difficulty=str(session.get("difficulty", "")),
            request_id=str(job.get("request_id") or job.get("id") or ""),
            meta=meta,
        )
        return flow.browser_jobs(rebuilt)
    if kind == flow.KIND_THOUGHT:
        analysis = st.session_state.chat_analysis or {}
        examples = analysis.get("example_replies")
        if not isinstance(examples, list):
            examples = []
        rebuilt = build_thought_job(
            mode=session["mode"],
            school_id=session["school_id"],
            selected_ids=session["selected_techniques"],
            turns=_dialogue_turns(),
            student_guide=str(analysis.get("student_guide", "")),
            example_replies=[str(item) for item in examples],
            prior_notes=list(st.session_state.get("coach_thoughts") or []),
            latest_thought=str(meta.get("latest_thought") or ""),
            request_id=str(job.get("request_id") or job.get("id") or ""),
            meta=meta,
        )
        return flow.browser_jobs(rebuilt)
    if kind == flow.KIND_EVAL_SNAPSHOT:
        rebuilt = build_eval_snapshot_job(
            mode=session["mode"],
            school_id=session["school_id"],
            selected_ids=session["selected_techniques"],
            turns=list(st.session_state.turns or []),
            continuation_snapshot=st.session_state.continuation_snapshot,
            session_id=str(session.get("session_id") or ""),
            meta=meta,
        )
        return flow.browser_jobs(rebuilt)
    return flow.browser_jobs(job)


def _enqueue_analyze_after_chat(session: dict[str, Any], meta: Mapping[str, Any]) -> None:
    if not flow.should_analyze_mid_session(
        difficulty=str(session.get("difficulty", "")),
        is_opening=bool(meta.get("is_opening")),
        has_prior_turns=bool(meta.get("has_prior_turns") or st.session_state.prior_turns_context),
    ):
        return
    session_id = str(session.get("session_id") or "")
    turn_token = str(len(st.session_state.turns or []))
    latest_student_message = str(meta.get("latest_student_message") or "")
    flow.enqueue(st.session_state, build_analyze_job(
        mode=session["mode"],
        school_id=session["school_id"],
        selected_ids=session["selected_techniques"],
        counseling_plan=st.session_state.counseling_plan,
        prior_analysis=st.session_state.chat_analysis,
        turns=_dialogue_turns(),
        latest_student_message=latest_student_message,
        difficulty=str(session.get("difficulty", "")),
        request_id=f"analyze-{session_id}-{turn_token}",
        meta={
            "session_turn_count": len(st.session_state.turns or []),
            "latest_student_message": latest_student_message,
            "ai_turn_index": len(st.session_state.turns or []),
        },
    ))
    flow.set_phase(st.session_state, flow.COACHING)


def _apply_plan_result(job: dict[str, Any], texts: dict[str, str]) -> None:
    request_id = str(job.get("request_id") or job.get("id") or "")
    plan = parse_json_response(texts[request_id])
    meta = dict(job.get("meta") or {})
    mode = str(meta.get("mode") or "")
    school_id = str(meta.get("school_id") or "")
    selected_ids = list(meta.get("selected_ids") or [])
    theme = str(meta.get("theme") or "")
    difficulty = str(meta.get("difficulty") or "")
    plan.setdefault("mode", mode)
    plan.setdefault("school_id", school_id)
    if str(meta.get("flow") or "") == "continuation":
        _commit_continuation(dict(meta.get("thread") or {}), selected_ids, plan=plan)
    else:
        case_data = case_data_from_plan(plan) if mode == "practice" else None
        case_id = str(plan.get("case_id") or ("student_topic" if mode != "practice" else f"case-{uuid.uuid4().hex[:8]}"))
        _commit_new_session(
            mode=mode,
            school_id=school_id,
            selected_ids=selected_ids,
            theme=theme,
            difficulty=difficulty,
            plan=plan,
            case_data=case_data,
            case_id=case_id,
        )
    _enqueue_opening_chat()


def _apply_chat_result(job: dict[str, Any], texts: dict[str, str]) -> None:
    session = st.session_state.active_session or {}
    request_id = str(job.get("request_id") or job.get("id") or "")
    meta = dict(job.get("meta") or {})
    role = "ai_client" if session["mode"] == "practice" else "ai_counselor"
    store_turn(new_turn(
        session=session,
        turn_index=len(st.session_state.turns) + 1,
        speaker_role=role,
        content=texts[request_id],
        timezone=CONFIG.timezone,
        latency_ms=int(getattr(gemini(), "last_latency_ms", 0) or 0),
    ))
    flow.set_phase(st.session_state, flow.LIVE)
    st.session_state.pending_student_stored = None
    _enqueue_analyze_after_chat(session, meta)


def _apply_analyze_result(job: dict[str, Any], texts: dict[str, str]) -> None:
    session = st.session_state.active_session or {}
    meta = dict(job.get("meta") or {})
    request_id = str(job.get("request_id") or job.get("id") or "")
    session_turns, _turns = _analyze_turns(meta)
    latest_student_message = str(meta.get("latest_student_message") or "")
    try:
        st.session_state.chat_analysis = parse_json_response(texts[request_id])
    except Exception:
        st.session_state.chat_analysis = dict(st.session_state.chat_analysis or {})
    show_turn_review = turn_review_visible(str(session.get("difficulty", "")))
    if show_turn_review and session.get("mode") == "practice" and latest_student_message:
        student_index = next(
            (
                int(turn["turn_index"])
                for turn in reversed(session_turns)
                if str(turn.get("speaker_role", "")).startswith("student")
            ),
            0,
        )
        record_turn_review(student_index, st.session_state.chat_analysis)
    if show_turn_review and session.get("mode") == "experience" and st.session_state.chat_analysis:
        record_turn_review(int(meta.get("ai_turn_index") or 0), st.session_state.chat_analysis)
    if not flow.has_kind(st.session_state, flow.KIND_ANALYZE):
        flow.set_phase(st.session_state, flow.LIVE)


def _apply_thought_result(job: dict[str, Any], texts: dict[str, str]) -> None:
    request_id = str(job.get("request_id") or job.get("id") or "")
    notes = list(st.session_state.get("coach_thoughts") or [])
    notes.append({"role": "coach", "content": texts[request_id]})
    st.session_state.coach_thoughts = notes
    st.session_state.pending_thought = ""
    st.session_state.pending_thought_noted = ""


def _apply_eval_snapshot_result(job: dict[str, Any], texts: dict[str, str]) -> None:
    session = st.session_state.active_session or {}
    session_id = str(session.get("session_id") or "")
    eval_id = f"eval-{session_id}"
    snapshot_id = f"snapshot-{session_id}"
    raw = texts.get(eval_id, "")
    try:
        parsed = parse_json_response(raw)
    except Exception as exc:
        parsed = {
            "total_score": None,
            "strengths": [],
            "improvement_points": [],
            "encouragement": "本次晤談與逐字稿已完整保存；評量服務暫時無法完成，可請教師稍後重新檢視。",
            "limitations": str(exc),
        }
    try:
        snapshot = parse_json_response(texts.get(snapshot_id, ""))
    except Exception:
        snapshot = {
            "continuation_role": session.get("continuation_role"),
            "relationship_summary": "本次逐字稿已保存，續談時可由最近對話接續。",
            "disclosed_topics": [],
            "unfinished_issues": [],
            "next_session_focus": [],
        }
    assessment_id = str(st.session_state.setdefault(f"_assessment_id_{session_id}", str(uuid.uuid4())))
    record = {
        "assessment_id": assessment_id,
        "session_id": session_id,
        "participant_id": session["participant_id"],
        "mode": session["mode"],
        "school_id": session["school_id"],
        "rubric_version": CONFIG.rubric_version,
        "total_score": parsed.get("total_score", parsed.get("score", "")),
        "dimension_scores": parsed.get("dimensions", {}),
        "skill_events": parsed.get("skill_events", parsed.get("technique_explanations", [])),
        "strengths": parsed.get("strengths", []),
        "improvement_points": parsed.get("improvement_points", []),
        "quoted_examples": parsed.get("alternative_responses", []),
        "next_practice_focus": parsed.get("next_practice_focus", parsed.get("reflection_questions", [])),
        "encouragement": parsed.get("encouragement", ""),
        "raw_model_output": raw,
        "parsed_json": parsed,
        "created_at": STORE.now(),
    }
    if st.session_state.get("_assessment_saved_for") != session_id:
        STORE.save_assessment(record)
        st.session_state._assessment_saved_for = session_id
    st.session_state.assessment = parsed
    st.session_state.raw_assessment = raw
    st.session_state.continuation_snapshot = snapshot
    finished = finish_session(session, CONFIG.timezone, "completed")
    consent = str((st.session_state.get("pending_finalize") or {}).get("consent") or session.get("research_consent") or "")
    if finished["mode"] == "experience":
        finished["research_consent"] = consent if consent in {"yes", "no", "anonymous"} else "yes"
    else:
        finished["research_consent"] = ""
    st.session_state.active_session = finished
    STORE.finish_session(finished)
    persist_thread_state(flow.thread_status_for_end(keep_process=True), include_turns=True)
    st.session_state.pending_finalize = None
    flow.set_phase(st.session_state, flow.FEEDBACK)


def _apply_job_result(job: dict[str, Any], texts: dict[str, str]) -> None:
    kind = str(job.get("kind") or "")
    if kind == flow.KIND_PLAN:
        _apply_plan_result(job, texts)
    elif kind == flow.KIND_CHAT:
        _apply_chat_result(job, texts)
    elif kind == flow.KIND_ANALYZE:
        _apply_analyze_result(job, texts)
    elif kind == flow.KIND_THOUGHT:
        _apply_thought_result(job, texts)
    elif kind == flow.KIND_EVAL_SNAPSHOT:
        _apply_eval_snapshot_result(job, texts)


def _fail_job(job: dict[str, Any], exc: BaseException) -> None:
    kind = str(job.get("kind") or "")
    session = st.session_state.active_session or {}
    if kind == flow.KIND_CHAT and session:
        store_turn(new_turn(
            session=session,
            turn_index=len(st.session_state.turns) + 1,
            speaker_role="system",
            content="本輪模型暫時無法回應，請稍後再試或結束本次晤談。",
            timezone=CONFIG.timezone,
            error_flag=str(exc)[:300],
        ))
        st.session_state.pending_student_stored = None
        flow.set_phase(st.session_state, flow.LIVE)
        return
    if kind == flow.KIND_ANALYZE:
        st.session_state.chat_analysis = dict(st.session_state.chat_analysis or {})
        return
    if kind == flow.KIND_THOUGHT:
        notes = list(st.session_state.get("coach_thoughts") or [])
        notes.append({"role": "coach", "content": f"暫時無法回應這個想法：{exc}"})
        st.session_state.coach_thoughts = notes
        st.session_state.pending_thought = ""
        st.session_state.pending_thought_noted = ""
        return
    if kind == flow.KIND_PLAN:
        flow.clear_jobs(st.session_state)
        flow.set_phase(st.session_state, flow.SETUP)
        st.error(f"無法開始模擬：{exc}")
        return
    st.error(f"結束晤談時發生問題：{exc}")


def tick_gemini_queue() -> bool:
    """Run at most one queued Gemini job for this Streamlit rerun."""
    try:
        result = flow.tick(
            st.session_state,
            materialize=_materialize_job,
            run_jobs=lambda jobs: run_browser_jobs(gemini(), jobs),
        )
    except GeminiRouterPending:
        return False
    except Exception as exc:
        job = flow.peek_next(st.session_state)
        if job and str(job.get("kind") or "") == flow.KIND_EVAL_SNAPSHOT:
            st.error(f"結束晤談時發生問題：{exc}")
            return False
        if job:
            _fail_job(job, exc)
            flow.complete_job(st.session_state, str(job.get("id") or ""))
        return True
    if not result:
        return False
    job = result["job"]
    try:
        _apply_job_result(job, result["texts"])
    except Exception as exc:
        if str(job.get("kind") or "") == flow.KIND_EVAL_SNAPSHOT:
            st.error(f"結束晤談時發生問題：{exc}")
            return False
        _fail_job(job, exc)
    flow.complete_job(st.session_state, str(job.get("id") or ""))
    return True


def _drain_session_intents() -> None:
    pending_start = st.session_state.get("pending_start_new")
    if pending_start:
        try:
            start_new_session(**pending_start)
            st.session_state.pending_start_new = None
        except Exception as exc:
            st.session_state.pending_start_new = None
            st.error(f"無法開始模擬：{exc}")
            return
    pending_cont = st.session_state.get("pending_continuation")
    if pending_cont:
        try:
            start_continuation(pending_cont["thread"], pending_cont["selected_ids"])
            st.session_state.pending_continuation = None
        except Exception as exc:
            st.session_state.pending_continuation = None
            st.error(f"無法開始續談：{exc}")
            return
    pending_final = st.session_state.get("pending_finalize")
    if pending_final and st.session_state.get("active_session"):
        try:
            prepare_finalize(**pending_final)
        except Exception as exc:
            st.error(f"結束晤談時發生問題：{exc}")


def _starting_without_session() -> bool:
    job = flow.peek_next(st.session_state)
    return bool(job and str(job.get("kind") or "") == flow.KIND_PLAN and not _session_in_progress())


def new_practice_panel(settings: dict[str, str]) -> None:
    allowed_modes = {x.strip() for x in settings.get("allowed_modes", "experience,practice").split(",")}
    mode_options = [m for m in ("experience", "practice") if m in allowed_modes]
    if not mode_options:
        st.error("教師目前未開放任何模式。")
        return
    with st.container(border=True):
        mode = st.radio(
            "選擇模式",
            mode_options,
            format_func=lambda x: "學派體驗｜我當個案，AI 當諮商師" if x == "experience" else "學派實作｜我當諮商師，AI 當個案",
        )
        render_role_callout(mode)
    school_ids = list(SCHOOLS)
    school_id = st.selectbox("選擇學派", school_ids, format_func=lambda x: SCHOOLS[x]["name"])
    school = get_school(school_id)
    st.caption(school["core"])
    options = [t["id"] for t in school["techniques"]]
    label = {t["id"]: f"{t['name']}｜{t['short']}" for t in school["techniques"]}
    if mode == "experience":
        selected = list(school["experience_default"])
        st.markdown("**本次由 AI 示範的三項技巧**")
        render_technique_cards(get_techniques(school_id, selected))
    else:
        selected = st.multiselect(
            "從五項技巧中選擇恰好三項",
            options,
            format_func=lambda x: label[x],
            max_selections=3,
        )
        st.caption(f"已選 {len(selected)}／3 項。系統會依這三項技巧建立具有練習機會的案例。")
    theme_col, diff_col = st.columns(2, gap="medium")
    with theme_col:
        theme_id = st.selectbox("練習主題", list(PRACTICE_THEMES), format_func=lambda x: PRACTICE_THEMES[x])
    with diff_col:
        difficulty = st.select_slider("案例難度", ["初階", "中階", "進階"], value="中階")
        if mode == "practice":
            if difficulty == "初階":
                st.caption("初階會在旁邊顯示依此刻談話調整的計畫與例句；你的每一句諮商回應會在對話中給簡短回饋。")
            elif difficulty == "中階":
                st.caption("中階會在對話中給單句回饋，並可在旁邊寫下想法；不顯示諮商計畫。")
            else:
                st.caption("進階不會在對話中提示；整體回饋在結束晤談後一次給出。")
        else:
            if difficulty == "初階":
                st.caption("初階會在旁邊說明諮商師此刻在做什麼；AI 每一句會標出目標與預期效果。不會預告下一句台詞，也不評分你的個案表現。")
            elif difficulty == "中階":
                st.caption("中階只在對話中標出 AI 每一句的目標與預期效果，不顯示旁欄說明，也不評分你的個案表現。")
            else:
                st.caption("進階不會在對話中提示；結束後再解析 AI 示範，不評分你的個案表現。")
    ready = len(selected) == 3
    if st.button("開始新的模擬", type="primary", use_container_width=True, disabled=not ready):
        if len(selected) != 3:
            st.error("開始前必須選擇恰好三項技巧。")
            return
        st.session_state.pending_start_new = {
            "mode": mode,
            "school_id": school_id,
            "selected_ids": list(selected),
            "theme": PRACTICE_THEMES[theme_id],
            "difficulty": difficulty,
        }
        st.rerun()
    if not ready:
        st.caption("請先選滿三項技巧，再開始模擬。")


def continuation_panel() -> None:
    try:
        threads = STORE.list_threads(st.session_state.participant_id)
    except Exception as exc:
        st.error(f"讀取續談資料失敗：{exc}")
        return
    if not threads:
        with st.container(border=True):
            render_empty_state("還沒有可續談的歷程", "請先完成一次模擬，之後就能接續同一位 AI 對話角色。")
        return
    choices = {str(t["conversation_thread_id"]): t for t in threads}
    selected_thread_id = st.selectbox(
        "選擇要續談的歷程",
        list(choices),
        format_func=lambda x: (
            f"{choices[x].get('school_name')}｜"
            f"{'AI 個案' if choices[x].get('mode') == 'practice' else 'AI 諮商師'}｜"
            f"更新 {choices[x].get('updated_at')}"
        ),
    )
    thread = choices[selected_thread_id]
    school_id = str(thread["school_id"])
    school = get_school(school_id)
    default_ids = parse_json_cell(thread.get("selected_techniques"), school["experience_default"])
    with st.container(border=True):
        render_role_callout("experience" if thread.get("mode") == "experience" else "practice")
        if thread.get("mode") == "experience":
            selected = list(school["experience_default"])
            st.caption("續談會載入同一位 AI 諮商師、同一學派與前次工作焦點。")
            render_technique_cards(get_techniques(school_id, selected))
        else:
            option_ids = [t["id"] for t in school["techniques"]]
            name_map = {t["id"]: f"{t['name']}｜{t['short']}" for t in school["techniques"]}
            valid_defaults = [x for x in default_ids if x in option_ids][:3]
            selected = st.multiselect(
                "本次續談要練習的三項技巧",
                option_ids,
                default=valid_defaults,
                format_func=lambda x: name_map[x],
                max_selections=3,
            )
            st.caption("續談會載入同一位 AI 個案、已揭露內容、關係狀態與未完成議題。")
        snapshot = parse_json_cell(thread.get("latest_snapshot"), {})
        unfinished = snapshot.get("unfinished_issues") or []
        if unfinished:
            st.caption("前次尚未完成")
            render_chips(unfinished)
    ready = len(selected) == 3
    if st.button("開始續談", type="primary", use_container_width=True, disabled=not ready):
        if len(selected) != 3:
            st.error("開始前必須選擇恰好三項技巧。")
            return
        st.session_state.pending_continuation = {
            "thread": thread,
            "selected_ids": list(selected),
        }
        st.rerun()


def stop_simulation_for_risk(session: dict[str, Any], prompt: str) -> None:
    message = safety_message()
    store_turn(new_turn(
        session=session,
        turn_index=len(st.session_state.turns) + 1,
        speaker_role="system",
        content=message,
        timezone=CONFIG.timezone,
        error_flag="immediate_risk_stop",
    ))
    STORE.append("RiskEvents", {
        "risk_event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": session["participant_id"],
        "timestamp": STORE.now(),
        "event_type": "immediate_risk_language",
        "action_taken": "simulation_stopped_and_human_help_displayed",
        "content_redacted": redact_for_preview(prompt),
    })
    flow.clear_jobs(st.session_state)
    st.session_state.pending_finalize = None
    st.session_state.active_session = finish_session(session, CONFIG.timezone, "safety_stopped")
    STORE.finish_session(st.session_state.active_session)
    persist_thread_state(flow.thread_status_for_end(keep_process=False, safety_stopped=True), include_turns=True)
    flow.set_phase(st.session_state, flow.FEEDBACK)


def render_thought_coach(session: dict[str, Any], analysis: dict[str, Any]) -> None:
    if not thought_coach_visible(str(session.get("mode", "")), str(session.get("difficulty", ""))):
        return
    notes = list(st.session_state.get("coach_thoughts") or [])
    st.markdown('<div class="ct-thoughts"><p class="ct-kicker">當下的想法與判斷</p></div>', unsafe_allow_html=True)
    render_thought_log(notes)
    with st.form("coach_thought_form", clear_on_submit=True):
        thought = st.text_area(
            "想法輸入",
            height=140,
            max_chars=min(400, CONFIG.max_input_chars),
            placeholder="例如：我覺得現在該反映情緒，但怕問太快。",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("送出想法", use_container_width=True)
    if submitted:
        text = str(thought or "").strip()
        if not text:
            return
        if detect_pii(text):
            st.error("內容疑似包含 Email、電話或身分證格式。請刪除可識別資訊後再送出。")
            return
        if detect_immediate_risk(text):
            stop_simulation_for_risk(session, text)
            st.rerun()
            return
        st.session_state.pending_thought = text
        if st.session_state.get("pending_thought_noted") != text:
            notes.append({"role": "student", "content": text})
            st.session_state.coach_thoughts = notes
            st.session_state.pending_thought_noted = text
        examples = analysis.get("example_replies")
        if not isinstance(examples, list):
            examples = []
        flow.enqueue(st.session_state, build_thought_job(
            mode=session["mode"],
            school_id=session["school_id"],
            selected_ids=session["selected_techniques"],
            turns=_dialogue_turns(),
            student_guide=str(analysis.get("student_guide", "")),
            example_replies=[str(item) for item in examples],
            prior_notes=list(st.session_state.get("coach_thoughts") or []),
            latest_thought=text,
            request_id=f"thought-{session.get('session_id')}-{len(st.session_state.get('coach_thoughts') or [])}",
            meta={"latest_thought": text},
        ))


def render_chat() -> None:
    session = st.session_state.active_session
    settings = settings_with_defaults()
    target_key = "duration_experience_min" if session["mode"] == "experience" else "duration_practice_min"
    target_minutes = int(settings.get(target_key, "8" if session["mode"] == "experience" else "15") or 0)
    elapsed = datetime.now(ZoneInfo(CONFIG.timezone)) - datetime.fromisoformat(session["started_at"])
    elapsed_min = max(0, int(elapsed.total_seconds() // 60))
    show_plan = live_plan_visible(str(session.get("difficulty", "")))
    show_thoughts = thought_coach_visible(str(session.get("mode", "")), str(session.get("difficulty", "")))
    show_turn_review = turn_review_visible(str(session.get("difficulty", "")))
    analysis = st.session_state.chat_analysis or {}
    reviews = {int(item.get("turn_index") or 0): item for item in (st.session_state.get("turn_reviews") or [])}

    def render_inline_review(role: str, turn: dict[str, Any]) -> None:
        if not show_turn_review:
            return
        review = reviews.get(int(turn.get("turn_index") or 0))
        if not review:
            return
        if session["mode"] == "practice" and role == "student_counselor":
            verdict = review.get("verdict") or "回饋"
            comment = review.get("comment") or ""
            st.caption(f"即時回饋 · {verdict}" + (f"：{comment}" if comment else ""))
        elif session["mode"] == "experience" and role == "ai_counselor":
            goal = str(review.get("goal") or "").strip()
            effect = str(review.get("effect") or "").strip()
            parts = []
            if goal:
                parts.append(f"目標：{goal}")
            if effect:
                parts.append(f"預期效果：{effect}")
            if parts:
                st.caption("本句說明 · " + " · ".join(parts))

    def render_dialog() -> None:
        with st.container(border=True):
            info_col, action_col = st.columns([4.2, 1.1], gap="medium", vertical_alignment="center")
            with info_col:
                st.markdown('<p class="ct-kicker">' + mode_label(session["mode"]) + "</p>", unsafe_allow_html=True)
                st.markdown(f"**{session['school_name']}**")
                render_chips(session["selected_technique_names"])
                extra = ""
                if session["mode"] == "experience":
                    if show_plan:
                        extra = " · 旁欄說明示範重點"
                    elif show_turn_review:
                        extra = " · 單句示範說明開啟"
                    st.caption(f"你正以個案身分對話，約 {elapsed_min} 分鐘 · 建議 {target_minutes} 分鐘{extra}。不評分個案表現；由你自行決定何時結束。")
                else:
                    if show_plan:
                        extra = " · 初階即時計畫開啟"
                    elif show_thoughts:
                        extra = " · 單句說明與想法框開啟"
                    elif show_turn_review:
                        extra = " · 單句說明開啟"
                    else:
                        extra = ""
                    st.caption(f"目前約 {elapsed_min} 分鐘 · 建議練習 {target_minutes} 分鐘{extra}。由你自行決定何時結束，不強制跳轉。")
            with action_col:
                ending = _ending_session()
                if ending:
                    st.caption("正在整理晤談回饋…")
                elif st.button("結束晤談", use_container_width=True):
                    if session["mode"] == "experience":
                        request_experience_research_consent()
                    else:
                        st.session_state.pending_finalize = {"consent": "yes"}
                        st.rerun()
        for turn in st.session_state.turns:
            role = str(turn["speaker_role"])
            with st.chat_message("user" if role.startswith("student") else "assistant"):
                st.caption(ROLE_LABELS.get(role, role))
                st.write(turn["content_raw"])
                render_inline_review(role, turn)
        st.caption("可在括弧中輸入非語言訊息，例如（語氣放緩）、（停頓數秒）。")

    prompt = None
    is_client = session["mode"] == "experience"
    chat_placeholder = "以個案身分說說你的感受或想法…" if is_client else "輸入你的諮商回應…"
    ending = _ending_session()
    if show_plan or show_thoughts:
        chat_col, coach_col = st.columns([1.8, 1] if is_client else [1.55, 1], gap="large")
        with chat_col:
            render_dialog()
            if not ending:
                prompt = st.chat_input(chat_placeholder, max_chars=CONFIG.max_input_chars)
        with coach_col:
            if show_plan:
                examples = analysis.get("example_replies") if not is_client else []
                if not isinstance(examples, list):
                    examples = []
                render_coaching_panel(
                    mode=session["mode"],
                    guide=str(analysis.get("student_guide", "")),
                    examples=examples,
                )
            if show_thoughts and not ending:
                render_thought_coach(session, analysis)
    else:
        render_dialog()
        if not ending:
            prompt = st.chat_input(chat_placeholder, max_chars=CONFIG.max_input_chars)
    if prompt:
        pii = detect_pii(prompt)
        if pii:
            st.error("內容疑似包含 Email、電話或身分證格式。請刪除可識別資訊後再送出。")
            return
        if st.session_state.get("pending_student_stored") != prompt:
            student_role = "student_counselor" if session["mode"] == "practice" else "student_client"
            store_turn(new_turn(
                session=session,
                turn_index=len(st.session_state.turns) + 1,
                speaker_role=student_role,
                content=prompt,
                timezone=CONFIG.timezone,
            ))
            st.session_state.pending_student_stored = prompt
        if detect_immediate_risk(prompt):
            stop_simulation_for_risk(session, prompt)
            st.session_state.pending_student_stored = None
            st.rerun()
            return
        session_id = str(session.get("session_id") or "")
        flow.set_phase(st.session_state, flow.LIVE)
        flow.enqueue(st.session_state, build_chat_job(
            mode=session["mode"],
            school_id=session["school_id"],
            selected_ids=session["selected_techniques"],
            turns=_dialogue_turns(),
            latest_student_message=prompt,
            case_data=st.session_state.case_data,
            continuation_snapshot=st.session_state.continuation_snapshot,
            counseling_plan=st.session_state.counseling_plan,
            chat_analysis=st.session_state.chat_analysis,
            is_opening=False,
            request_id=f"chat-{session_id}-{len(st.session_state.turns or [])}",
            meta={
                "is_opening": False,
                "latest_student_message": prompt,
                "has_prior_turns": bool(st.session_state.prior_turns_context),
            },
        ))


def request_experience_research_consent() -> None:
    _open_experience_research_consent()


@st.dialog("是否作為研究素材", dismissible=False)
def _open_experience_research_consent() -> None:
    st.markdown("這次你擔任個案。是否願意將此次晤談作為教學研究素材？")
    keep_col, drop_col = st.columns(2, gap="small")
    with keep_col:
        willing = st.button("願意", type="primary", use_container_width=True)
        anonymous = st.checkbox("匿名", key="experience_research_anonymous")
        if anonymous:
            st.caption("帳號只留完成紀錄；晤談過程另以不記名與時間保存。")
        if willing:
            st.session_state.pending_finalize = {
                "consent": "anonymous" if anonymous else "yes",
            }
            st.rerun()
    with drop_col:
        if st.button("不願意", use_container_width=True):
            st.session_state.pending_finalize = {"consent": "no"}
            st.rerun()


def prepare_finalize(*, keep_transcript: bool = True, consent: str | None = None) -> None:
    session = st.session_state.active_session
    if not session or str(session.get("completion_status") or "") != "in_progress":
        st.session_state.pending_finalize = None
        return
    if session["mode"] == "experience":
        chosen = consent if consent in {"yes", "no", "anonymous"} else ("yes" if keep_transcript else "no")
    else:
        chosen = "yes"
    if flow.has_kind(st.session_state, flow.KIND_EVAL_SNAPSHOT):
        return
    if chosen != "yes":
        finished = finish_session(session, CONFIG.timezone, "completed")
        finished["research_consent"] = chosen
        st.session_state.active_session = finished
        STORE.finish_session(finished)
        st.session_state.assessment = {}
        st.session_state.raw_assessment = ""
        st.session_state.continuation_snapshot = {
            "continuation_role": finished["continuation_role"],
            "relationship_summary": "本次未保存可識別的晤談過程，續談時請重新建立關係與焦點。",
            "disclosed_topics": [],
            "unfinished_issues": [],
            "next_session_focus": [],
        }
        persist_thread_state(flow.thread_status_for_end(keep_process=False), include_turns=False)
        if chosen == "anonymous":
            save_anon = getattr(STORE, "save_anonymous_transcript", None)
            if callable(save_anon):
                save_anon(finished, st.session_state.turns)
            else:
                from src.data_store import GoogleSheetsStore
                GoogleSheetsStore.save_anonymous_transcript(STORE, finished, st.session_state.turns)
        STORE.purge_session_transcript(finished["session_id"])
        st.session_state.turns = []
        st.session_state.turn_reviews = []
        st.session_state.coach_thoughts = []
        st.session_state.chat_analysis = None
        st.session_state.counseling_plan = None
        flow.clear_jobs(st.session_state)
        st.session_state.pending_finalize = None
        flow.set_phase(st.session_state, flow.FEEDBACK)
        return
    session["research_consent"] = chosen if session["mode"] == "experience" else ""
    st.session_state.active_session = session
    flow.clear_jobs(st.session_state)
    flow.set_phase(st.session_state, flow.ENDING)
    flow.enqueue(st.session_state, build_eval_snapshot_job(
        mode=session["mode"],
        school_id=session["school_id"],
        selected_ids=session["selected_techniques"],
        turns=list(st.session_state.turns or []),
        continuation_snapshot=st.session_state.continuation_snapshot,
        session_id=str(session["session_id"]),
        meta={"consent": chosen},
    ))


def render_feedback(settings: dict[str, str]) -> None:
    session = st.session_state.active_session
    assessment = st.session_state.assessment or {}
    consent = str(session.get("research_consent") or "")
    hide_process = session["mode"] == "experience" and consent in {"no", "anonymous"}
    with st.container(border=True):
        kicker = "體驗完成" if session["mode"] == "experience" else "晤談完成"
        st.markdown(f'<p class="ct-kicker">{kicker}</p>', unsafe_allow_html=True)
        st.markdown(f"**{session['school_name']} · {mode_label(session['mode'])}**")
        render_chips(session["selected_technique_names"])
        if session["mode"] == "experience":
            if consent == "no":
                st.caption("依你的選擇，本次只留下完成紀錄，未保存晤談過程、示範解析或諮商師原句。")
            elif consent == "anonymous":
                st.caption("已將晤談過程以不記名方式另存。你的帳號只留下完成紀錄，不含諮商過程。")
            else:
                st.caption("你剛才擔任個案。逐字稿與示範解析已保存，之後可續談同一位 AI 諮商師。")
        else:
            st.caption("完整逐字稿、練習時間、學派、技巧與形成性回饋已保存。之後可續談同一位 AI 對話角色。")
    if not hide_process and as_bool(settings.get("student_feedback_visible"), True):
        if session["mode"] == "practice":
            if as_bool(settings.get("student_score_visible"), True) and assessment.get("total_score") is not None:
                score_col, note_col = st.columns([1, 2.2], gap="medium", vertical_alignment="center")
                with score_col:
                    st.metric("AI 形成性分數", f"{assessment.get('total_score')} / 100")
                with note_col:
                    st.caption("此分數供練習參考，不是標準化測驗結果，也不會覆寫教師人工成績。")
            if assessment.get("encouragement"):
                st.markdown("**鼓勵與整體回饋**")
                render_quote(assessment["encouragement"])
            if assessment.get("strengths"):
                st.markdown("**具體做得好的地方**")
                for item in assessment["strengths"]:
                    st.markdown(f"- {item.get('point', '')}")
                    if item.get("evidence_quote"):
                        render_quote(item.get("evidence_quote", ""))
                    if item.get("effect"):
                        st.caption(item.get("effect", ""))
            if assessment.get("improvement_points"):
                st.markdown("**最值得優先調整**")
                for item in assessment["improvement_points"]:
                    st.markdown(f"- **{item.get('point', '')}**：{item.get('reason', '')}")
            if assessment.get("alternative_responses"):
                st.markdown("**可嘗試的替代回應**")
                for item in assessment["alternative_responses"]:
                    with st.container(border=True):
                        st.caption("原句")
                        render_quote(item.get("original_quote", ""))
                        st.caption("可改為")
                        st.write(item.get("better_response", ""))
                        if item.get("why"):
                            st.caption(item.get("why", ""))
            if assessment.get("next_practice_focus"):
                st.markdown("**下次練習焦點**")
                for item in assessment["next_practice_focus"]:
                    st.markdown(f"- {item}")
        else:
            st.info("你剛才擔任個案。以下只解析 AI 示範諮商師，不評分你的自我揭露或個案表現。")
            if assessment.get("overall_learning"):
                st.markdown("**本次可以帶走的重點**")
                render_quote(assessment["overall_learning"])
            if assessment.get("technique_explanations"):
                st.markdown("**示範技巧說明**")
                for item in assessment["technique_explanations"]:
                    name = next((t["name"] for t in get_school(session["school_id"])["techniques"] if t["id"] == item.get("technique_id")), item.get("technique_id", "技巧"))
                    with st.expander(name):
                        if item.get("ai_quote"):
                            st.caption("AI 諮商師原句")
                            render_quote(item.get("ai_quote", ""))
                        st.write(f"使用理由：{item.get('why_used', '')}")
                        st.write(f"可能效果：{item.get('possible_effect', '')}")
            questions = assessment.get("reflection_questions") or assessment.get("next_practice_focus") or []
            if questions:
                st.markdown("**可以想想**")
                for item in questions:
                    st.markdown(f"- {item}")
            if assessment.get("encouragement"):
                st.markdown("**給觀察者的一句話**")
                render_quote(assessment["encouragement"])
    elif not hide_process:
        st.info("教師目前設定為不向學生顯示 AI 回饋；本次資料仍已保存供教師檢視。")

    kept = not hide_process
    action_col, home_col = st.columns(2, gap="small")
    with action_col:
        if kept:
            transcript = make_transcript_txt(session, st.session_state.turns)
            st.download_button(
                "下載逐字稿 TXT",
                transcript,
                file_name=safe_filename(session["session_id"]),
                mime="text/plain",
                use_container_width=True,
            )
        else:
            st.caption("未保存逐字稿，因此沒有檔案可下載。")
    with home_col:
        if st.button("回到練習首頁", type="primary", use_container_width=True):
            flow.clear_jobs(st.session_state)
            flow.set_phase(st.session_state, flow.SETUP)
            st.session_state.active_session = None
            st.session_state.turns = []
            st.session_state.case_data = None
            st.session_state.counseling_plan = None
            st.session_state.chat_analysis = None
            st.session_state.turn_reviews = []
            st.session_state.coach_thoughts = []
            st.session_state.continuation_snapshot = None
            st.session_state.prior_turns_context = []
            st.session_state.assessment = None
            st.rerun()


def student_page() -> None:
    settings = settings_with_defaults()
    error = student_access_error(settings)
    if error and not account_is_teacher():
        apply_theme("student")
        show_online_people()
        render_header()
        st.error(error)
        return
    in_chat = bool(
        st.session_state.active_session
        and st.session_state.active_session.get("completion_status") == "in_progress"
    )
    if in_chat:
        session = st.session_state.active_session or {}
        apply_theme(
            "coach"
            if live_plan_visible(str(session.get("difficulty", "")))
            or thought_coach_visible(str(session.get("mode", "")), str(session.get("difficulty", "")))
            else "chat"
        )
        show_online_people()
    else:
        apply_theme("student")
        show_online_people()
        render_header(show_notice=not bool(st.session_state.active_session))
    pending_save = str(st.session_state.pop("_pending_save_api_key", "") or "")
    if not st.session_state.api_validated or not st.session_state.api_key:
        api_key_gate()
        return
    if pending_save:
        render_saved_api_keys(save_key=pending_save, hide=True)
    _drain_session_intents()
    if _session_in_progress() != in_chat:
        st.rerun()
    if _starting_without_session():
        st.info("正在準備模擬…")
        if tick_gemini_queue():
            st.rerun()
        return
    in_chat = bool(
        st.session_state.active_session
        and st.session_state.active_session.get("completion_status") == "in_progress"
    )
    if st.session_state.active_session:
        if in_chat:
            render_chat()
        else:
            render_feedback(settings)
            return
        if tick_gemini_queue():
            st.rerun()
        elif not flow.has_jobs(st.session_state):
            keep_gemini_router_alive()
        return
    tab1, tab2 = st.tabs(["開始新模擬", "續談上次歷程"])
    with tab1:
        new_practice_panel(settings)
    with tab2:
        continuation_panel()


def export_research_zip() -> bytes:
    flusher = getattr(STORE, "flush", None)
    if callable(flusher):
        flusher()
    declined = {
        str(row.get("session_id"))
        for row in STORE.all_records("Sessions")
        if str(row.get("research_consent") or "") == "no"
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for sheet in SCHEMAS:
            if sheet == "AuthSessions":
                continue
            rows = STORE.all_records(sheet)
            if sheet == "whitelist":
                headers = [h for h in SCHEMAS[sheet] if h != "password_hash"]
                rows = [{key: row.get(key, "") for key in headers} for row in rows]
            else:
                headers = SCHEMAS[sheet]
                if sheet in {"ChatLogs", "Assessments", "SkillEvents"} and declined:
                    rows = [row for row in rows if str(row.get("session_id")) not in declined]
            frame = pd.DataFrame(rows, columns=headers)
            zf.writestr(f"{sheet}.csv", frame.to_csv(index=False).encode("utf-8-sig"))
    return output.getvalue()


def teacher_settings_panel(settings: dict[str, str]) -> None:
    st.markdown('<p class="ct-kicker">課程控制</p>', unsafe_allow_html=True)
    st.markdown("**教學開放設定**")
    with st.form("teacher_settings"):
        left, right = st.columns(2, gap="large")
        with left:
            enabled = st.checkbox("開放學生使用", value=as_bool(settings.get("system_enabled"), True))
            modes = st.multiselect(
                "開放模式", ["experience", "practice"],
                default=[x.strip() for x in settings.get("allowed_modes", "experience,practice").split(",") if x.strip()],
                format_func=lambda x: "學派體驗" if x == "experience" else "學生實作",
            )
            feedback = st.checkbox("學生可看形成性回饋", value=as_bool(settings.get("student_feedback_visible"), True))
            score = st.checkbox("學生可看 AI 形成性分數", value=as_bool(settings.get("student_score_visible"), True))
        with right:
            open_start = st.text_input("開放時間（ISO，可留白）", settings.get("open_start", ""), placeholder="2026-09-15T08:00:00+08:00")
            open_end = st.text_input("關閉時間（ISO，可留白）", settings.get("open_end", ""), placeholder="2027-01-15T23:59:00+08:00")
            max_sessions = st.number_input("每位學生最多 Session 數（0 表示不限）", min_value=0, value=int(settings.get("max_sessions_per_student", "0") or 0))
            duration_experience = st.number_input("體驗模式建議分鐘數", min_value=1, max_value=60, value=int(settings.get("duration_experience_min", "8") or 8))
            duration_practice = st.number_input("實作模式建議分鐘數", min_value=1, max_value=60, value=int(settings.get("duration_practice_min", "15") or 15))
        if st.form_submit_button("儲存設定", type="primary", use_container_width=True):
            updates = {
                "system_enabled": str(enabled).lower(),
                "open_start": open_start.strip(),
                "open_end": open_end.strip(),
                "max_sessions_per_student": max_sessions,
                "duration_experience_min": duration_experience,
                "duration_practice_min": duration_practice,
                "allowed_modes": ",".join(modes),
                "student_feedback_visible": str(feedback).lower(),
                "student_score_visible": str(score).lower(),
            }
            try:
                if open_start:
                    parse_local_datetime(open_start)
                if open_end:
                    parse_local_datetime(open_end)
                for key, value in updates.items():
                    STORE.save_setting(key, value, st.session_state.email)
                st.success("設定已儲存。")
            except Exception as exc:
                st.error(f"設定未儲存：{exc}")


def teacher_whitelist_panel() -> None:
    st.markdown('<p class="ct-kicker">帳號管理</p>', unsafe_allow_html=True)
    st.markdown("**登入白名單**")
    st.caption("只有 enabled 的 Email 可以用密碼或 OTP 登入。學生無法自行註冊。密碼雜湊不會顯示。")
    rows = STORE.list_whitelist()
    if rows:
        display = []
        for row in rows:
            item = {key: value for key, value in row.items() if key != "password_hash"}
            item["已設密碼"] = "是" if str(row.get("password_hash", "")).strip() else "否"
            display.append(item)
        st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
    else:
        with st.container(border=True):
            render_empty_state("白名單尚無資料", "請新增學生 Email，或在 Secrets 的 teacher_emails／login_allowlist 種子帳號。")
    with st.form("add_whitelist"):
        email_col, role_col = st.columns([2.4, 1], gap="small", vertical_alignment="bottom")
        with email_col:
            new_email = st.text_input("新增 Email")
        with role_col:
            new_role = st.selectbox("角色", ["student", "teacher"], format_func=lambda x: "學生" if x == "student" else "教師")
        if st.form_submit_button("加入白名單", type="primary", use_container_width=True):
            value = normalize_email(new_email)
            if "@" not in value:
                st.error("請輸入有效 Email。")
            else:
                STORE.upsert_whitelist(value, new_role, True)
                st.success(f"已加入：{value}")
                st.rerun()
    if rows:
        target = st.selectbox(
            "停用或重新啟用",
            [str(r.get("email", "")) for r in rows],
        )
        col1, col2 = st.columns(2, gap="small")
        role = next((str(r.get("role", "student")) for r in rows if r.get("email") == target), "student")
        with col1:
            if st.button("停用此 Email", use_container_width=True):
                STORE.upsert_whitelist(target, role, False)
                st.rerun()
        with col2:
            if st.button("重新啟用此 Email", use_container_width=True):
                STORE.upsert_whitelist(target, role, True)
                st.rerun()


def _school_display_name(school_id: str) -> str:
    try:
        return get_school(str(school_id))["name"]
    except Exception:
        return str(school_id or "")


def teacher_anonymous_panel() -> None:
    st.markdown('<p class="ct-kicker">不記名晤談</p>', unsafe_allow_html=True)
    st.markdown("**匿名晤談紀錄**")
    st.caption("這些紀錄不含 Email、participant_id 或續談 thread，無法對回學生帳號。")
    rows = STORE.all_records("AnonymousSessions")
    if not rows:
        with st.container(border=True):
            render_empty_state("目前尚無匿名晤談", "學生在體驗結束時勾選「匿名」後，晤談過程會出現在這裡。")
        return
    display = pd.DataFrame(rows)
    columns = [
        c for c in [
            "started_at", "ended_at", "duration_seconds", "mode", "school_id",
            "selected_technique_names", "difficulty", "anonymous_session_id",
        ]
        if c in display.columns
    ]
    shown = display[columns].copy()
    if "school_id" in shown.columns:
        shown["school_id"] = shown["school_id"].map(_school_display_name)
    st.dataframe(shown, use_container_width=True, hide_index=True)
    session_ids = [str(row.get("anonymous_session_id") or "") for row in rows]
    chosen = st.selectbox("查看單次匿名晤談", session_ids, format_func=lambda x: f"{x[:8]}…")
    row = next((item for item in rows if str(item.get("anonymous_session_id")) == chosen), {})
    render_meta_grid([
        ("學派", _school_display_name(str(row.get("school_id", "")))),
        ("模式", mode_label(str(row.get("mode", "")))),
        ("開始時間", str(row.get("started_at", "") or "")),
    ])
    st.markdown("**逐字稿**")
    render_transcript(STORE.anonymous_session_turns(chosen))


def teacher_dashboard() -> None:
    apply_theme("teacher")
    show_online_people()
    render_header(show_notice=True)
    if not account_is_teacher():
        st.error("此帳號沒有教師後台權限。")
        return
    settings = settings_with_defaults()
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["學生進度與逐字稿", "匿名晤談", "登入白名單", "開放設定", "研究資料匯出"])
    with tab1:
        sessions = STORE.all_records("Sessions")
        identities = STORE.all_records("IdentityMap")
        if not sessions:
            with st.container(border=True):
                render_empty_state("目前尚無 Session 資料", "學生完成模擬後，進度與逐字稿會顯示在這裡。")
        else:
            sdf = pd.DataFrame(sessions)
            idf = pd.DataFrame(identities)[["participant_id", "email"]] if identities else pd.DataFrame(columns=["participant_id", "email"])
            merged = sdf.merge(idf, on="participant_id", how="left")
            completed = merged[merged["completion_status"].isin(["completed", "safety_stopped"])]
            c1, c2, c3 = st.columns(3, gap="medium")
            c1.metric("學生人數", int(merged["participant_id"].nunique()))
            c2.metric("Session 數", len(merged))
            durations = pd.to_numeric(merged.get("duration_seconds", pd.Series(dtype=float)), errors="coerce").fillna(0)
            c3.metric("累計練習分鐘", f"{durations.sum()/60:.1f}")
            email_options = ["全部"] + sorted(str(x) for x in merged["email"].dropna().unique())
            selected_email = st.selectbox("依學校 Email 篩選", email_options)
            shown = completed if selected_email == "全部" else completed[completed["email"] == selected_email]
            columns = [c for c in ["email", "started_at", "mode", "school_id", "selected_technique_names", "duration_seconds", "completion_status", "research_consent", "session_id"] if c in shown.columns]
            display = shown[columns].copy()
            if "research_consent" in display.columns:
                display["research_consent"] = display["research_consent"].map(
                    lambda x: {"yes": "同意", "no": "未同意", "anonymous": "匿名"}.get(str(x), "—")
                )
            st.dataframe(display, use_container_width=True, hide_index=True)
            if not shown.empty:
                session_ids = list(shown["session_id"].astype(str))
                chosen = st.selectbox("查看單次 Session", session_ids, format_func=lambda x: f"{x[:8]}…")
                row = shown[shown["session_id"].astype(str) == chosen].iloc[0].to_dict()
                consent = str(row.get("research_consent") or "")
                render_meta_grid([
                    ("學生", str(row.get("email", "") or "")),
                    ("學派", _school_display_name(str(row.get("school_id", "")))),
                    ("模式", mode_label(str(row.get("mode", "")))),
                ])
                turns = STORE.session_turns(chosen)
                st.markdown("**逐字稿**")
                if consent == "no":
                    render_empty_state("學生未同意作為研究素材", "本次體驗只留下完成紀錄，不含諮商過程，也不會出現在研究匯出的對話資料中。")
                elif consent == "anonymous":
                    render_empty_state("晤談過程已不記名另存", "此帳號只留下完成紀錄。匿名晤談請到「匿名晤談」分頁查看，無法對回這位學生。")
                else:
                    render_transcript(turns)
                thread_id = str(row.get("conversation_thread_id", ""))
                thread = next(
                    (t for t in STORE.all_records("Threads") if str(t.get("conversation_thread_id")) == thread_id),
                    None,
                )
                if thread and consent not in {"no", "anonymous"}:
                    with st.expander("內部諮商計畫（學生不可見）"):
                        st.json(parse_json_cell(thread.get("counseling_plan"), {}), expanded=False)
                    with st.expander("內部對話分析（學生不可見）"):
                        st.json(parse_json_cell(thread.get("chat_analysis"), {}), expanded=False)
                assessment = STORE.get_assessment(chosen)
                if assessment:
                    with st.expander("AI 原始形成性回饋"):
                        parsed = parse_json_cell(assessment.get("parsed_json"), {})
                        st.json(parsed, expanded=False)
                st.markdown("**教師人工成績與評語**")
                with st.form(f"grade-{chosen}"):
                    score_col, comment_col = st.columns([1, 2.2], gap="medium")
                    with score_col:
                        use_score = st.checkbox("本次填寫教師分數")
                        teacher_score = st.number_input("教師分數", min_value=0, max_value=100, value=80, disabled=not use_score)
                    with comment_col:
                        teacher_comment = st.text_area("教師評語", height=120)
                    if st.form_submit_button("另存教師評量", type="primary", use_container_width=True):
                        STORE.add_teacher_grade(
                            chosen, str(row.get("participant_id")), st.session_state.email,
                            int(teacher_score) if use_score else None, teacher_comment,
                        )
                        st.success("教師評量已另存，不會覆寫 AI 原始結果。")
    with tab2:
        teacher_anonymous_panel()
    with tab3:
        teacher_whitelist_panel()
    with tab4:
        teacher_settings_panel(settings)
    with tab5:
        with st.container(border=True):
            st.markdown('<p class="ct-kicker">研究匯出</p>', unsafe_allow_html=True)
            st.markdown("**下載完整後台 CSV 壓縮檔**")
            st.caption(
                "匯出包含 whitelist、IdentityMap、Sessions、ChatLogs、AnonymousSessions、AnonymousChatLogs、Threads、Assessments、SkillEvents、TeacherGrades、Settings 與 RiskEvents。"
                "whitelist 與 IdentityMap 含 Email，研究去識別化時應單獨保管或移除。"
                "體驗模式選「不願意」的對話資料不會匯出；勾選匿名的晤談過程在 AnonymousSessions／AnonymousChatLogs。"
            )
            try:
                payload = export_research_zip()
                st.download_button(
                    "下載完整後台 CSV 壓縮檔",
                    payload,
                    file_name=f"theory_agent_research_export_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
            except Exception as exc:
                st.error(f"資料匯出失敗：{exc}")


try:
    restore_browser_session()
    if st.session_state.pending_password_email and not st.session_state.authenticated:
        password_setup_page()
    elif not st.session_state.authenticated:
        login_page()
    else:
        sidebar()
        if st.session_state.view == "teacher":
            teacher_dashboard()
        else:
            student_page()
except GeminiRouterPending:
    st.caption("正在由這個瀏覽器呼叫 Gemini…")
