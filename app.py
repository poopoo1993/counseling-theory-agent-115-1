from __future__ import annotations

import io
import time
import uuid
import zipfile
from datetime import datetime
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
from src.data_store import SCHEMAS, SqliteStore, parse_json_cell
from src.gemini_client import GeminiService, parse_json_response
from src.llm_pipeline import analyze_chat, create_counseling_plan, generate_chat_reply
from src.prompts import (
    build_experience_analysis_prompt,
    build_practice_evaluator_prompt,
    build_snapshot_prompt,
    case_data_from_plan,
    live_coaching_enabled,
)
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
    render_quote,
    render_role_callout,
    render_safety_notice,
    render_technique_cards,
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


@st.cache_resource(show_spinner=False)
def build_shared_store(sqlite_path: str, timezone: str):
    return SqliteStore(sqlite_path, timezone)


def get_store():
    if "data_store" in st.session_state:
        return st.session_state.data_store
    app = SECRETS.get("app", {}) if isinstance(SECRETS.get("app"), dict) else {}
    sqlite_path = str(app.get("sqlite_path", "data/app.sqlite")).strip() or "data/app.sqlite"
    store = build_shared_store(sqlite_path, CONFIG.timezone)
    store.seed_whitelist(CONFIG.login_allowlist, CONFIG.teacher_emails)
    st.session_state.store_mode = "sqlite"
    st.session_state.data_store = store
    return store


STORE = get_store()


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


def persist_thread_state(status: str = "in_progress") -> None:
    session = st.session_state.active_session
    if not session:
        return
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
        "case_data": st.session_state.case_data or {},
        "counseling_plan": st.session_state.counseling_plan or {},
        "chat_analysis": st.session_state.chat_analysis or {},
        "latest_snapshot": st.session_state.continuation_snapshot or {},
        "last_session_id": session["session_id"],
        "recent_turns": (st.session_state.prior_turns_context + st.session_state.turns)[-6:],
        "difficulty": session.get("difficulty", ""),
        "updated_at": STORE.now(),
        "status": status,
    })


def logout() -> None:
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
    with st.container(border=True):
        st.markdown('<p class="ct-kicker">開始前</p>', unsafe_allow_html=True)
        st.markdown("**連接你自己的 Gemini API Key**")
        st.caption(
            "請用個人的 @gmail.com 帳號到 Google AI Studio 申請 API Key。"
            "Key 只留在目前瀏覽器工作階段，不會寫入 SQLite、逐字稿或研究資料。"
            "重新整理後仍保持登入，但需再輸入一次 API Key。"
        )
        st.link_button("前往 Google AI Studio", "https://aistudio.google.com/", use_container_width=True)
        key_col, action_col = st.columns([3.2, 1], gap="small", vertical_alignment="bottom")
        with key_col:
            key = st.text_input("Gemini API Key", type="password", value=st.session_state.api_key)
        with action_col:
            tested = st.button("測試連線", type="primary", use_container_width=True)
        if tested:
            try:
                with st.spinner("正在測試連線…"):
                    service = GeminiService(key, CONFIG.model_name)
                    service.validate_key()
                st.session_state.api_key = key.strip()
                st.session_state.api_validated = True
                st.success("API Key 已驗證，可以開始練習。")
                st.rerun()
            except Exception as exc:
                st.session_state.api_validated = False
                st.error(str(exc))
    return None


def gemini() -> GeminiService:
    return GeminiService(st.session_state.api_key, CONFIG.model_name)


def store_turn(turn: dict[str, Any]) -> None:
    st.session_state.turns.append(turn)
    STORE.append_turn(turn)


def record_turn_review(student_turn_index: int, analysis: dict[str, Any] | None) -> None:
    review = (analysis or {}).get("turn_review")
    if not isinstance(review, dict):
        return
    comment = str(review.get("comment", "")).strip()
    verdict = str(review.get("verdict", "")).strip()
    if not comment and not verdict:
        return
    history = list(st.session_state.get("turn_reviews") or [])
    history = [item for item in history if int(item.get("turn_index") or 0) != student_turn_index]
    history.append({
        "turn_index": student_turn_index,
        "verdict": verdict,
        "comment": comment,
    })
    st.session_state.turn_reviews = history


def generate_ai_turn(is_opening: bool, latest_student_message: str = "") -> None:
    session = st.session_state.active_session
    turns = st.session_state.prior_turns_context + st.session_state.turns
    coaching = live_coaching_enabled(session["mode"], str(session.get("difficulty", "")))
    should_analyze = (not is_opening) or bool(st.session_state.prior_turns_context) or coaching
    if should_analyze:
        st.session_state.chat_analysis = analyze_chat(
            gemini(),
            mode=session["mode"],
            school_id=session["school_id"],
            selected_ids=session["selected_techniques"],
            counseling_plan=st.session_state.counseling_plan,
            prior_analysis=st.session_state.chat_analysis,
            turns=turns,
            latest_student_message=latest_student_message,
            difficulty=str(session.get("difficulty", "")),
        )
        if coaching and latest_student_message:
            student_index = next(
                (
                    int(turn["turn_index"])
                    for turn in reversed(st.session_state.turns)
                    if str(turn.get("speaker_role", "")).startswith("student")
                ),
                0,
            )
            record_turn_review(student_index, st.session_state.chat_analysis)
        persist_thread_state("in_progress")
    response, latency = generate_chat_reply(
        gemini(),
        mode=session["mode"],
        school_id=session["school_id"],
        selected_ids=session["selected_techniques"],
        turns=turns,
        latest_student_message=latest_student_message,
        case_data=st.session_state.case_data,
        continuation_snapshot=st.session_state.continuation_snapshot,
        counseling_plan=st.session_state.counseling_plan,
        chat_analysis=st.session_state.chat_analysis,
        is_opening=is_opening,
    )
    role = "ai_client" if session["mode"] == "practice" else "ai_counselor"
    store_turn(new_turn(
        session=session,
        turn_index=len(st.session_state.turns) + 1,
        speaker_role=role,
        content=response,
        timezone=CONFIG.timezone,
        latency_ms=latency,
    ))
    persist_thread_state("in_progress")


def start_new_session(mode: str, school_id: str, selected_ids: list[str], theme: str, difficulty: str) -> None:
    validate_selected_techniques(school_id, selected_ids)
    plan = create_counseling_plan(
        gemini(),
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        theme=theme,
        difficulty=difficulty,
    )
    case_data = case_data_from_plan(plan) if mode == "practice" else None
    case_id = str(plan.get("case_id") or ("student_topic" if mode != "practice" else f"case-{uuid.uuid4().hex[:8]}"))
    session = new_session(
        participant_id=st.session_state.participant_id,
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        model_name=CONFIG.model_name,
        prompt_version=CONFIG.prompt_version,
        timezone=CONFIG.timezone,
        theme=theme,
        difficulty=difficulty,
        case_id=case_id,
    )
    st.session_state.active_session = session
    st.session_state.turns = []
    st.session_state.case_data = case_data
    st.session_state.counseling_plan = plan
    st.session_state.chat_analysis = None
    st.session_state.turn_reviews = []
    st.session_state.continuation_snapshot = None
    st.session_state.prior_turns_context = []
    st.session_state.assessment = None
    STORE.start_session(session)
    persist_thread_state("in_progress")
    generate_ai_turn(is_opening=True)


def start_continuation(thread: dict[str, Any], selected_ids: list[str]) -> None:
    mode = str(thread["mode"])
    school_id = str(thread["school_id"])
    validate_selected_techniques(school_id, selected_ids)
    prior_difficulty = str(thread.get("difficulty") or "").strip()
    difficulty = prior_difficulty if prior_difficulty and prior_difficulty != "延續前次" else "中階"
    session = new_session(
        participant_id=st.session_state.participant_id,
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        model_name=CONFIG.model_name,
        prompt_version=CONFIG.prompt_version,
        timezone=CONFIG.timezone,
        theme="續談上次議題",
        difficulty=difficulty,
        thread_id=str(thread["conversation_thread_id"]),
        case_id=str(thread.get("case_id", "student_topic")),
    )
    st.session_state.active_session = session
    st.session_state.turns = []
    st.session_state.case_data = parse_json_cell(thread.get("case_data"), None)
    st.session_state.counseling_plan = parse_json_cell(thread.get("counseling_plan"), {})
    st.session_state.chat_analysis = parse_json_cell(thread.get("chat_analysis"), {})
    st.session_state.turn_reviews = []
    st.session_state.continuation_snapshot = parse_json_cell(thread.get("latest_snapshot"), {})
    st.session_state.prior_turns_context = parse_json_cell(thread.get("recent_turns"), [])
    st.session_state.assessment = None
    st.session_state.counseling_plan = create_counseling_plan(
        gemini(),
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        theme="續談上次議題",
        difficulty=difficulty,
        prior_snapshot=st.session_state.continuation_snapshot,
        prior_plan=st.session_state.counseling_plan,
        prior_analysis=st.session_state.chat_analysis,
    )
    if mode == "practice":
        st.session_state.case_data = case_data_from_plan(st.session_state.counseling_plan) or st.session_state.case_data
    STORE.start_session(session)
    persist_thread_state("in_progress")
    generate_ai_turn(is_opening=True)


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
                st.caption("初階會在對話旁提供即時練習提示，並對你每一句諮商回應給簡短回饋。")
            else:
                st.caption("中階與進階不會在對話中提示；整體回饋在結束晤談後一次給出。")
    ready = len(selected) == 3
    if st.button("開始新的模擬", type="primary", use_container_width=True, disabled=not ready):
        if len(selected) != 3:
            st.error("開始前必須選擇恰好三項技巧。")
            return
        try:
            with st.spinner("正在擬定學派計畫並建立開場…"):
                start_new_session(mode, school_id, list(selected), PRACTICE_THEMES[theme_id], difficulty)
            st.rerun()
        except Exception as exc:
            st.error(f"無法開始模擬：{exc}")
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
        try:
            with st.spinner("正在接續上次晤談關係…"):
                start_continuation(thread, list(selected))
            st.rerun()
        except Exception as exc:
            st.error(f"無法開始續談：{exc}")


def render_chat() -> None:
    session = st.session_state.active_session
    settings = settings_with_defaults()
    target_key = "duration_experience_min" if session["mode"] == "experience" else "duration_practice_min"
    target_minutes = int(settings.get(target_key, "8" if session["mode"] == "experience" else "15") or 0)
    elapsed = datetime.now(ZoneInfo(CONFIG.timezone)) - datetime.fromisoformat(session["started_at"])
    elapsed_min = max(0, int(elapsed.total_seconds() // 60))
    coaching = live_coaching_enabled(session["mode"], str(session.get("difficulty", "")))
    analysis = st.session_state.chat_analysis or {}
    reviews = {int(item.get("turn_index") or 0): item for item in (st.session_state.get("turn_reviews") or [])}

    def render_dialog() -> None:
        with st.container(border=True):
            info_col, action_col = st.columns([4.2, 1.1], gap="medium", vertical_alignment="center")
            with info_col:
                st.markdown('<p class="ct-kicker">' + mode_label(session["mode"]) + "</p>", unsafe_allow_html=True)
                st.markdown(f"**{session['school_name']}**")
                render_chips(session["selected_technique_names"])
                extra = " · 初階即時提示開啟" if coaching else ""
                st.caption(f"目前約 {elapsed_min} 分鐘 · 建議練習 {target_minutes} 分鐘{extra}。由你自行決定何時結束，不強制跳轉。")
            with action_col:
                if st.button("結束晤談", use_container_width=True):
                    finalize_session()
                    st.rerun()
        for turn in st.session_state.turns:
            role = str(turn["speaker_role"])
            with st.chat_message("user" if role.startswith("student") else "assistant"):
                st.caption(ROLE_LABELS.get(role, role))
                st.write(turn["content_raw"])
                if coaching and role == "student_counselor":
                    review = reviews.get(int(turn.get("turn_index") or 0))
                    if review:
                        verdict = review.get("verdict") or "回饋"
                        comment = review.get("comment") or ""
                        st.caption(f"即時回饋 · {verdict}" + (f"：{comment}" if comment else ""))
        st.caption("可在括弧中輸入非語言訊息，例如（語氣放緩）、（停頓數秒）。")

    if coaching:
        chat_col, coach_col = st.columns([1.55, 1], gap="large")
        with chat_col:
            render_dialog()
        with coach_col:
            latest = next(iter(reversed(st.session_state.get("turn_reviews") or [])), None)
            render_coaching_panel(analysis.get("student_guide", ""), latest)
    else:
        render_dialog()

    prompt = st.chat_input("輸入你的回應…", max_chars=CONFIG.max_input_chars)
    if not prompt:
        return
    pii = detect_pii(prompt)
    if pii:
        st.error("內容疑似包含 Email、電話或身分證格式。請刪除可識別資訊後再送出。")
        return
    student_role = "student_counselor" if session["mode"] == "practice" else "student_client"
    student_turn = new_turn(
        session=session,
        turn_index=len(st.session_state.turns) + 1,
        speaker_role=student_role,
        content=prompt,
        timezone=CONFIG.timezone,
    )
    store_turn(student_turn)
    if detect_immediate_risk(prompt):
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
        st.session_state.active_session = finish_session(session, CONFIG.timezone, "safety_stopped")
        STORE.finish_session(st.session_state.active_session)
        st.rerun()
    try:
        with st.spinner("正在分析對話並回應…"):
            generate_ai_turn(is_opening=False, latest_student_message=prompt)
    except Exception as exc:
        store_turn(new_turn(
            session=session,
            turn_index=len(st.session_state.turns) + 1,
            speaker_role="system",
            content="本輪模型暫時無法回應，請稍後再試或結束本次晤談。",
            timezone=CONFIG.timezone,
            error_flag=str(exc)[:300],
        ))
    st.rerun()


def finalize_session() -> None:
    session = finish_session(st.session_state.active_session, CONFIG.timezone, "completed")
    st.session_state.active_session = session
    STORE.finish_session(session)
    raw = ""
    parsed: dict[str, Any]
    try:
        if session["mode"] == "practice":
            prompt = build_practice_evaluator_prompt(
                session["school_id"], session["selected_techniques"], st.session_state.turns
            )
        else:
            prompt = build_experience_analysis_prompt(
                session["school_id"], session["selected_techniques"], st.session_state.turns
            )
        raw = gemini().generate_text(
            prompt,
            system_instruction="你是形成性教學回饋評量器。只能根據逐字稿證據輸出 JSON。",
            temperature=0.1,
            max_output_tokens=3200,
            response_json=True,
        )
        parsed = parse_json_response(raw)
    except Exception as exc:
        parsed = {
            "total_score": None,
            "strengths": [],
            "improvement_points": [],
            "encouragement": "本次晤談與逐字稿已完整保存；評量服務暫時無法完成，可請教師稍後重新檢視。",
            "limitations": str(exc),
        }

    assessment_id = str(uuid.uuid4())
    record = {
        "assessment_id": assessment_id,
        "session_id": session["session_id"],
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
    STORE.save_assessment(record)
    st.session_state.assessment = parsed
    st.session_state.raw_assessment = raw

    try:
        snapshot_raw = gemini().generate_text(
            build_snapshot_prompt(
                session["mode"], session["school_id"], session["selected_techniques"],
                st.session_state.turns, st.session_state.continuation_snapshot,
            ),
            system_instruction="你是續談狀態摘要器，只輸出不含可識別資訊的 JSON。",
            temperature=0.1,
            max_output_tokens=1600,
            response_json=True,
        )
        snapshot = parse_json_response(snapshot_raw)
    except Exception:
        snapshot = {
            "continuation_role": session["continuation_role"],
            "relationship_summary": "本次逐字稿已保存，續談時可由最近對話接續。",
            "disclosed_topics": [],
            "unfinished_issues": [],
            "next_session_focus": [],
        }
    st.session_state.continuation_snapshot = snapshot
    persist_thread_state("active")


def render_feedback(settings: dict[str, str]) -> None:
    session = st.session_state.active_session
    assessment = st.session_state.assessment or {}
    with st.container(border=True):
        st.markdown('<p class="ct-kicker">晤談完成</p>', unsafe_allow_html=True)
        st.markdown(f"**{session['school_name']} · {mode_label(session['mode'])}**")
        render_chips(session["selected_technique_names"])
        st.caption("完整逐字稿、練習時間、學派、技巧與形成性回饋已保存。之後可續談同一位 AI 對話角色。")
    if as_bool(settings.get("student_feedback_visible"), True):
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
            st.info("體驗模式不評分學生的自我揭露或『個案表現』。以下只解析 AI 諮商師的示範。")
            if assessment.get("technique_explanations"):
                for item in assessment["technique_explanations"]:
                    name = next((t["name"] for t in get_school(session["school_id"])["techniques"] if t["id"] == item.get("technique_id")), item.get("technique_id", "技巧"))
                    with st.expander(name):
                        if item.get("ai_quote"):
                            st.caption("AI 原句")
                            render_quote(item.get("ai_quote", ""))
                        st.write(f"使用理由：{item.get('why_used', '')}")
                        st.write(f"可能效果：{item.get('possible_effect', '')}")
            if assessment.get("overall_learning"):
                st.write(assessment["overall_learning"])
            if assessment.get("encouragement"):
                render_quote(assessment["encouragement"])
    else:
        st.info("教師目前設定為不向學生顯示 AI 回饋；本次資料仍已保存供教師檢視。")

    transcript = make_transcript_txt(session, st.session_state.turns)
    action_col, home_col = st.columns(2, gap="small")
    with action_col:
        st.download_button(
            "下載逐字稿 TXT",
            transcript,
            file_name=safe_filename(session["session_id"]),
            mime="text/plain",
            use_container_width=True,
        )
    with home_col:
        if st.button("回到練習首頁", type="primary", use_container_width=True):
            st.session_state.active_session = None
            st.session_state.turns = []
            st.session_state.case_data = None
            st.session_state.counseling_plan = None
            st.session_state.chat_analysis = None
            st.session_state.turn_reviews = []
            st.session_state.continuation_snapshot = None
            st.session_state.prior_turns_context = []
            st.session_state.assessment = None
            st.rerun()


def student_page() -> None:
    settings = settings_with_defaults()
    error = student_access_error(settings)
    if error and not account_is_teacher():
        apply_theme("student")
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
            if live_coaching_enabled(session.get("mode", ""), str(session.get("difficulty", "")))
            else "chat"
        )
    else:
        apply_theme("student")
        render_header(show_notice=not bool(st.session_state.active_session))
    if not st.session_state.api_validated or not st.session_state.api_key:
        api_key_gate()
        return
    if st.session_state.active_session:
        if in_chat:
            render_chat()
        else:
            render_feedback(settings)
        return
    tab1, tab2 = st.tabs(["開始新模擬", "續談上次歷程"])
    with tab1:
        new_practice_panel(settings)
    with tab2:
        continuation_panel()


def export_research_zip() -> bytes:
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


def teacher_dashboard() -> None:
    apply_theme("teacher")
    render_header(show_notice=True)
    if not account_is_teacher():
        st.error("此帳號沒有教師後台權限。")
        return
    settings = settings_with_defaults()
    tab1, tab2, tab3, tab4 = st.tabs(["學生進度與逐字稿", "登入白名單", "開放設定", "研究資料匯出"])
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
            columns = [c for c in ["email", "started_at", "mode", "school_id", "selected_technique_names", "duration_seconds", "completion_status", "session_id"] if c in shown.columns]
            st.dataframe(shown[columns], use_container_width=True, hide_index=True)
            if not shown.empty:
                session_ids = list(shown["session_id"].astype(str))
                chosen = st.selectbox("查看單次 Session", session_ids, format_func=lambda x: f"{x[:8]}…")
                row = shown[shown["session_id"].astype(str) == chosen].iloc[0].to_dict()
                render_meta_grid([
                    ("學生", str(row.get("email", ""))),
                    ("學派", _school_display_name(str(row.get("school_id", "")))),
                    ("模式", mode_label(str(row.get("mode", "")))),
                ])
                turns = STORE.session_turns(chosen)
                st.markdown("**逐字稿**")
                render_transcript(turns)
                thread_id = str(row.get("conversation_thread_id", ""))
                thread = next(
                    (t for t in STORE.all_records("Threads") if str(t.get("conversation_thread_id")) == thread_id),
                    None,
                )
                if thread:
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
        teacher_whitelist_panel()
    with tab3:
        teacher_settings_panel(settings)
    with tab4:
        with st.container(border=True):
            st.markdown('<p class="ct-kicker">研究匯出</p>', unsafe_allow_html=True)
            st.markdown("**下載完整後台 CSV 壓縮檔**")
            st.caption(
                "匯出包含 whitelist、IdentityMap、Sessions、ChatLogs、Threads、Assessments、SkillEvents、TeacherGrades、Settings 與 RiskEvents。"
                "whitelist 與 IdentityMap 含 Email，研究去識別化時應單獨保管或移除。"
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
