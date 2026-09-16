"""Shared Streamlit theme, layout helpers, and presentational markup."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import streamlit.components.v1 as components

APP_CSS = """
@import url("https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&display=swap");

:root {
  --ct-bg: #f4f1eb;
  --ct-surface: #fffdf8;
  --ct-ink: #1c2422;
  --ct-muted: #5e6a66;
  --ct-line: #e2dcd2;
  --ct-sage: #3d6b63;
  --ct-sage-dark: #2c514b;
  --ct-sage-soft: #e7f0ed;
  --ct-warn-bg: #f8efe2;
  --ct-warn-ink: #6b4a1b;
  --ct-radius: 16px;
  --ct-shadow: 0 1px 2px rgba(28, 36, 34, 0.04), 0 10px 28px rgba(28, 36, 34, 0.05);
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
[data-testid="stSidebar"], [data-testid="stMarkdownContainer"],
.stMarkdown, .stTextInput, .stSelectbox, .stMultiSelect, .stRadio,
.stButton, .stChatMessage, .stCaption, .stAlert {
  font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
}

.stApp {
  background: var(--ct-bg);
  color: var(--ct-ink);
}

[data-testid="stHeader"] {
  background: rgba(244, 241, 235, 0.88);
  backdrop-filter: blur(10px);
  border-bottom: 0;
}

[data-testid="stToolbar"] {
  display: none;
}

[data-testid="stDecoration"] {
  display: none;
}

.block-container,
[data-testid="stMainBlockContainer"] {
  max-width: __MAX_WIDTH__;
  margin-left: auto !important;
  margin-right: auto !important;
  padding-top: 3.15rem;
  padding-bottom: 4.5rem;
  padding-left: 1.5rem;
  padding-right: 1.5rem;
}

[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"] {
  max-width: __MAX_WIDTH__ !important;
  margin-left: auto !important;
  margin-right: auto !important;
  width: 100%;
}

[data-testid="stBottomBlockContainer"] {
  padding-left: 1.5rem !important;
  padding-right: 1.5rem !important;
  background: var(--ct-bg) !important;
}

[data-testid="stSidebar"] {
  background: #efebe3;
  border-right: 1px solid var(--ct-line);
}

[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
  padding: 1.15rem 1rem 1.5rem;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  font-size: 0.92rem;
  letter-spacing: 0.02em;
}

[data-testid="stMarkdownContainer"]:has(> style) {
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
}

[data-testid="stElementContainer"]:has(.ct-online),
[data-testid="element-container"]:has(.ct-online) {
  height: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: visible !important;
}

iframe[title$="ime_enter_guard"],
iframe[title$="gemini_router"] {
  height: 0 !important;
  width: 0 !important;
  border: 0 !important;
  position: absolute !important;
  pointer-events: none !important;
}

[data-testid="stElementContainer"]:has(iframe[title$="ime_enter_guard"]),
[data-testid="element-container"]:has(iframe[title$="ime_enter_guard"]),
[data-testid="stElementContainer"]:has(iframe[title$="gemini_router"]),
[data-testid="element-container"]:has(iframe[title$="gemini_router"]) {
  height: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
  padding: 0.15rem 0.1rem;
}

[data-testid="stVerticalBlock"] > [data-testid="element-container"]:has([data-testid="stChatInput"]) {
  position: sticky;
  bottom: 0;
}

h1, h2, h3 {
  letter-spacing: 0.01em;
  font-weight: 700;
  color: var(--ct-ink);
}

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button,
.stLinkButton > a {
  border-radius: 12px !important;
  min-height: 2.7rem;
  font-weight: 600 !important;
  border: 1px solid var(--ct-line) !important;
  box-shadow: none !important;
}

.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
  background: var(--ct-sage) !important;
  border-color: var(--ct-sage) !important;
  color: #fff !important;
}

.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
  background: var(--ct-sage-dark) !important;
  border-color: var(--ct-sage-dark) !important;
}

[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
  border-radius: 12px !important;
  min-height: 2.7rem;
  background: var(--ct-surface) !important;
  border-color: var(--ct-line) !important;
}

[data-testid="stCaption"] {
  color: var(--ct-muted) !important;
  line-height: 1.55;
}

[data-testid="stAlert"] {
  border-radius: 14px !important;
  border: 1px solid var(--ct-line) !important;
}

[data-testid="stMetric"] {
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: 14px;
  padding: 0.9rem 1rem 0.75rem;
}

[data-testid="stMetric"] label {
  color: var(--ct-muted);
}

div[data-testid="stVerticalBlockBorderWrapper"] > div,
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--ct-surface) !important;
  border: 1px solid var(--ct-line) !important;
  border-radius: var(--ct-radius) !important;
  box-shadow: var(--ct-shadow);
}

[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 0.25rem;
  border-bottom: 1px solid var(--ct-line);
}

[data-testid="stTabs"] [data-baseweb="tab"] {
  padding: 0.7rem 0.9rem;
  font-weight: 600;
}

[data-testid="stExpander"] {
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: 14px;
}

[data-testid="stChatMessage"] {
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: 16px;
  padding: 0.35rem 0.2rem;
}

[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: var(--ct-sage-soft);
  border-color: #d5e4df;
}

[data-testid="stChatInput"] {
  background: transparent;
  max-width: 100%;
  margin-left: auto;
  margin-right: auto;
}

[data-testid="stChatInput"] textarea {
  border-radius: 14px !important;
}

[data-testid="stDataFrame"] {
  border: 1px solid var(--ct-line);
  border-radius: 12px;
  overflow: hidden;
}

.ct-masthead {
  display: flex;
  align-items: center;
  gap: 0.95rem;
  margin: 0 0 1rem;
}

.ct-mark {
  width: 3rem;
  height: 3rem;
  border-radius: 14px;
  background: var(--ct-sage);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1.2rem;
  flex-shrink: 0;
}

.ct-masthead-copy h1 {
  font-size: 1.45rem;
  line-height: 1.25;
  margin: 0;
}

.ct-masthead-copy p {
  margin: 0.2rem 0 0;
  color: var(--ct-muted);
  font-size: 0.92rem;
}

.ct-notice {
  display: flex;
  gap: 0.7rem;
  align-items: flex-start;
  background: var(--ct-warn-bg);
  color: var(--ct-warn-ink);
  border: 1px solid #ead9be;
  border-radius: 14px;
  padding: 0.85rem 1rem;
  margin: 0 0 1.2rem;
  font-size: 0.9rem;
  line-height: 1.55;
}

.ct-notice strong {
  display: block;
  margin-bottom: 0.15rem;
}

.ct-kicker {
  margin: 0 0 0.2rem;
  color: var(--ct-sage);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.ct-hint {
  color: var(--ct-muted);
  font-size: 0.9rem;
  line-height: 1.55;
  margin: 0.35rem 0 0;
}

.ct-user {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: 14px;
  padding: 0.8rem 0.85rem;
  margin-bottom: 0.85rem;
}

.ct-avatar {
  width: 2.35rem;
  height: 2.35rem;
  border-radius: 50%;
  background: var(--ct-sage-soft);
  color: var(--ct-sage-dark);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}

.ct-user-email {
  font-weight: 600;
  font-size: 0.92rem;
  word-break: break-all;
  line-height: 1.35;
}

.ct-user-meta {
  color: var(--ct-muted);
  font-size: 0.78rem;
  margin-top: 0.15rem;
}

.ct-role-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem;
  margin: 0.35rem 0 0.15rem;
}

.ct-role-card {
  background: var(--ct-sage-soft);
  border-radius: 12px;
  padding: 0.75rem 0.85rem;
}

.ct-role-card span {
  display: block;
  color: var(--ct-muted);
  font-size: 0.75rem;
  margin-bottom: 0.2rem;
}

.ct-role-card strong {
  font-size: 0.95rem;
}

.ct-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.35rem 0 0.15rem;
}

.ct-chip {
  display: inline-flex;
  align-items: center;
  background: var(--ct-sage-soft);
  color: var(--ct-sage-dark);
  border-radius: 999px;
  padding: 0.22rem 0.7rem;
  font-size: 0.8rem;
  font-weight: 600;
}

.ct-tech-card {
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: 14px;
  padding: 0.85rem 0.9rem;
  min-height: 7.2rem;
}

.ct-tech-card strong {
  display: block;
  font-size: 0.95rem;
  margin-bottom: 0.35rem;
}

.ct-tech-card p {
  margin: 0;
  color: var(--ct-muted);
  font-size: 0.84rem;
  line-height: 1.5;
}

.ct-session-meta {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.ct-session-meta h2 {
  font-size: 1.28rem;
  margin: 0;
}

.ct-quote {
  background: #f7f4ee;
  border-left: 3px solid var(--ct-sage);
  border-radius: 0 12px 12px 0;
  padding: 0.7rem 0.85rem;
  margin: 0.35rem 0 0.7rem;
  font-size: 0.92rem;
  line-height: 1.55;
}

.ct-transcript {
  max-height: 28rem;
  overflow-y: auto;
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: 14px;
  padding: 0.35rem 1rem;
}

.ct-turn {
  padding: 0.8rem 0;
  border-bottom: 1px solid var(--ct-line);
}

.ct-turn:last-child {
  border-bottom: 0;
}

.ct-turn .who {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--ct-muted);
  margin-bottom: 0.25rem;
}

.ct-turn .body {
  font-size: 0.92rem;
  line-height: 1.6;
  white-space: pre-wrap;
}

.ct-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 0.2rem 0 0.9rem;
}

.ct-meta-item {
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: 12px;
  padding: 0.7rem 0.8rem;
}

.ct-meta-item span {
  display: block;
  color: var(--ct-muted);
  font-size: 0.75rem;
  margin-bottom: 0.2rem;
}

.ct-meta-item strong {
  font-size: 0.92rem;
  word-break: break-all;
}

.ct-empty {
  text-align: center;
  color: var(--ct-muted);
  padding: 1.4rem 0.8rem 1.1rem;
}

.ct-empty strong {
  display: block;
  color: var(--ct-ink);
  margin-bottom: 0.3rem;
}

.ct-online {
  position: fixed;
  top: 0.85rem;
  right: 1.15rem;
  z-index: 10050;
  font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
}

.ct-online details {
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: 999px;
  box-shadow: var(--ct-shadow);
  min-width: 7.5rem;
}

.ct-online[data-openable="1"] details[open] {
  border-radius: 16px;
  min-width: 16rem;
}

.ct-online summary {
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  cursor: default;
  padding: 0.42rem 0.85rem;
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--ct-ink);
}

.ct-online[data-openable="1"] summary {
  cursor: pointer;
}

.ct-online summary::-webkit-details-marker {
  display: none;
}

.ct-online-dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: #3f8f6b;
  box-shadow: 0 0 0 4px rgba(63, 143, 107, 0.16);
  flex-shrink: 0;
}

.ct-online ul {
  margin: 0;
  padding: 0 0.85rem 0.75rem;
  list-style: none;
  border-top: 1px solid var(--ct-line);
}

.ct-online li {
  display: flex;
  justify-content: space-between;
  gap: 0.6rem;
  padding-top: 0.55rem;
  font-size: 0.8rem;
  line-height: 1.35;
  word-break: break-all;
}

.ct-online li span {
  color: var(--ct-muted);
  flex-shrink: 0;
}

.ct-coach {
  background: var(--ct-surface);
  border: 1px solid var(--ct-line);
  border-radius: var(--ct-radius);
  padding: 1rem 1.05rem 1.1rem;
  box-shadow: var(--ct-shadow);
  position: sticky;
  top: 4.75rem;
}

.ct-coach .ct-kicker {
  margin-bottom: 0.35rem;
}

.ct-coach-block {
  margin-top: 0.75rem;
}

.ct-coach-block span {
  display: block;
  color: var(--ct-muted);
  font-size: 0.75rem;
  margin-bottom: 0.25rem;
}

.ct-coach-block p {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.55;
}

.ct-coach-example {
  margin: 0 0 0.45rem;
  padding: 0.45rem 0.6rem;
  background: var(--ct-sage-soft);
  border-radius: 10px;
  font-size: 0.9rem;
  line-height: 1.5;
}

.ct-coach-example:last-child {
  margin-bottom: 0;
}

.ct-coach-empty {
  color: var(--ct-muted);
  font-size: 0.88rem;
  margin: 0;
}

.ct-thoughts {
  margin-top: 0.95rem;
  padding-top: 0.8rem;
  border-top: 1px solid var(--ct-line);
}

.ct-thoughts .ct-kicker {
  margin-bottom: 0.35rem;
}

.ct-thought-log {
  max-height: 12.5rem;
  overflow-y: auto;
  margin-bottom: 0.55rem;
}

.ct-thought-item {
  margin: 0 0 0.45rem;
  padding: 0.4rem 0.55rem;
  border-radius: 10px;
  font-size: 0.86rem;
  line-height: 1.5;
}

.ct-thought-item span {
  display: block;
  color: var(--ct-muted);
  font-size: 0.72rem;
  margin-bottom: 0.15rem;
}

.ct-thought-item.student {
  background: var(--ct-sage-soft);
}

.ct-thought-item.coach {
  background: #f4f1eb;
  border: 1px solid var(--ct-line);
}

[data-testid="stVerticalBlock"]:has(.ct-thoughts) [data-testid="stTextArea"] {
  overflow: visible;
}

[data-testid="stVerticalBlock"]:has(.ct-thoughts) [data-testid="stTextArea"] textarea {
  min-height: 8.75rem !important;
  padding-bottom: 0.85rem !important;
}

[data-testid="stVerticalBlock"]:has(.ct-thoughts) [data-testid="InputInstructions"] {
  position: relative !important;
  inset: auto !important;
  bottom: auto !important;
  right: auto !important;
  display: block;
  width: 100%;
  margin: 0.2rem 0 0.35rem;
  text-align: right;
  line-height: 1.3;
  pointer-events: none;
}

[data-testid="stVerticalBlock"]:has(.ct-thoughts) [data-testid="InputInstructions"] > span:not(:last-child) {
  display: none !important;
}

[data-testid="stVerticalBlock"]:has(.ct-thoughts) [data-testid="InputInstructions"] > span::before {
  content: none !important;
  margin: 0 !important;
}

@media (max-width: 800px) {
  .ct-role-grid,
  .ct-meta-grid {
    grid-template-columns: 1fr;
  }
  .ct-masthead-copy h1 {
    font-size: 1.22rem;
  }
}
"""

SAFETY_NOTICE = (
    "本系統僅供教學演練，不提供心理治療、診斷、臨床決策或緊急危機服務。"
    "請勿輸入真實個案姓名、電話、地址、學校或機構等可識別資訊。"
)

ROLE_LABELS = {
    "student_client": "你（個案）",
    "student_counselor": "你（諮商師）",
    "ai_client": "AI 模擬個案",
    "ai_counselor": "AI 示範諮商師",
    "system": "系統",
}


def _st():
    import streamlit as st

    return st


_IME_GUARD_DIR = Path(__file__).resolve().parent / "frontend" / "ime_enter_guard"
_ime_enter_guard = components.declare_component("ime_enter_guard", path=str(_IME_GUARD_DIR))


def install_ime_enter_guard() -> None:
    """Keep Zhuyin/IME Enter from submitting st.chat_input while composing."""
    _ime_enter_guard(default=None, key="ct_ime_enter_guard")


def apply_theme(density: str = "student") -> None:
    st = _st()
    install_ime_enter_guard()
    widths = {
        "login": "28.5rem",
        "student": "46rem",
        "chat": "48rem",
        "coach": "72rem",
        "teacher": "72rem",
    }
    extra = ""
    if density == "login":
        extra = """
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] {
          display: none !important;
        }
        [data-testid="stAppViewContainer"] > .main,
        [data-testid="stMain"] {
          margin-left: 0 !important;
        }
        """
    if density == "coach":
        extra += """
        [data-testid="stBottomBlockContainer"] {
          max-width: min(100%, 44rem) !important;
          margin-left: auto !important;
          margin-right: auto !important;
        }
        """
    css = APP_CSS.replace("__MAX_WIDTH__", widths.get(density, widths["student"])) + extra
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def escape_html(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def mode_label(mode: str) -> str:
    return "學派體驗" if mode == "experience" else "學生實作"


def render_masthead(title: str, subtitle: str) -> None:
    st = _st()
    st.markdown(
        f"""
        <div class="ct-masthead">
          <div class="ct-mark" aria-hidden="true">諮</div>
          <div class="ct-masthead-copy">
            <h1>{escape_html(title)}</h1>
            <p>{escape_html(subtitle)}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_safety_notice() -> None:
    st = _st()
    st.markdown(
        f"""
        <div class="ct-notice">
          <div>
            <strong>教學演練用途</strong>
            {escape_html(SAFETY_NOTICE)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_online_badge(people: Sequence[Mapping[str, Any]], *, show_people: bool) -> None:
    st = _st()
    count = len(people)
    label = f"{count} 人在線"
    items = ""
    can_open = show_people and count > 0
    if can_open:
        rows = []
        for person in people:
            role = "教師" if str(person.get("role", "")) == "teacher" else "學生"
            rows.append(
                f"<li>{escape_html(person.get('email', ''))}<span>{role}</span></li>"
            )
        items = f"<ul>{''.join(rows)}</ul>"
    st.markdown(
        f"""
        <div class="ct-online" data-openable="{1 if can_open else 0}">
          <details>
            <summary><span class="ct-online-dot" aria-hidden="true"></span>{escape_html(label)}</summary>
            {items}
          </details>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_user_card(email: str, participant_id: str, role_label: str) -> None:
    st = _st()
    initial = (email[:1] or "?").upper()
    st.markdown(
        f"""
        <div class="ct-user">
          <div class="ct-avatar">{escape_html(initial)}</div>
          <div>
            <div class="ct-user-email">{escape_html(email)}</div>
            <div class="ct-user-meta">{escape_html(role_label)} · {escape_html(participant_id)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_role_callout(mode: str) -> None:
    st = _st()
    if mode == "experience":
        yours, ai, hint = (
            "你擔任個案",
            "AI 擔任示範諮商師",
            "用虛構或低敏感內容說話即可。系統不評分你的個案表現，旁側與對話中的說明是在解說 AI 諮商師。",
        )
    else:
        yours, ai, hint = "你擔任諮商師", "AI 擔任模擬個案", "請從五項技巧中選恰好三項，系統會建立具練習機會的案例。"
    st.markdown(
        f"""
        <div class="ct-role-grid">
          <div class="ct-role-card"><span>你的角色</span><strong>{yours}</strong></div>
          <div class="ct-role-card"><span>AI 的角色</span><strong>{ai}</strong></div>
        </div>
        <p class="ct-hint">{hint}</p>
        """,
        unsafe_allow_html=True,
    )


def render_chips(labels: Iterable[str]) -> None:
    st = _st()
    values = list(labels) if not isinstance(labels, str) else [labels]
    chips = "".join(f'<span class="ct-chip">{escape_html(label)}</span>' for label in values if label)
    if chips:
        st.markdown(f'<div class="ct-chip-row">{chips}</div>', unsafe_allow_html=True)


def render_technique_cards(items: Sequence[Mapping[str, Any]]) -> None:
    st = _st()
    if not items:
        return
    cols = st.columns(len(items), gap="small")
    for col, item in zip(cols, items):
        with col:
            st.markdown(
                f"""
                <div class="ct-tech-card">
                  <strong>{escape_html(item.get("name", ""))}</strong>
                  <p>{escape_html(item.get("short", ""))}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_quote(text: str) -> None:
    st = _st()
    st.markdown(f'<div class="ct-quote">{escape_html(text)}</div>', unsafe_allow_html=True)


def render_empty_state(title: str, body: str) -> None:
    st = _st()
    st.markdown(
        f"""
        <div class="ct-empty">
          <strong>{escape_html(title)}</strong>
          {escape_html(body)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def coaching_panel_copy(mode: str) -> dict[str, str]:
    if mode == "experience":
        return {
            "title": "此刻示範說明",
            "guide_label": "諮商師此刻在做什麼",
            "guide_empty": "送出一句後，這裡會說明示範諮商師此刻的做法與用意，不會預告下一句台詞。",
            "examples_label": "",
            "examples_empty": "",
        }
    return {
        "title": "初階練習提示",
        "guide_label": "接下來的計畫與做法",
        "guide_empty": "送出一句後，這裡會依此刻談話更新計畫與做法。",
        "examples_label": "符合此刻的例句",
        "examples_empty": "符合此刻談話的例句會顯示在這裡。",
    }


def render_coaching_panel(
    *,
    mode: str,
    guide: str,
    examples: Sequence[str] | None = None,
) -> None:
    st = _st()
    copy = coaching_panel_copy(mode)
    guide_text = str(guide or "").strip()
    example_items = [str(item).strip() for item in (examples or []) if str(item).strip()]
    guide_html = (
        f"<p>{escape_html(guide_text)}</p>"
        if guide_text
        else f'<p class="ct-coach-empty">{escape_html(copy["guide_empty"])}</p>'
    )
    blocks = f'<div class="ct-coach-block"><span>{escape_html(copy["guide_label"])}</span>{guide_html}</div>'
    if copy["examples_label"]:
        if example_items:
            example_html = "".join(f"<p class=\"ct-coach-example\">{escape_html(item)}</p>" for item in example_items)
        else:
            example_html = f'<p class="ct-coach-empty">{escape_html(copy["examples_empty"])}</p>'
        blocks += f'<div class="ct-coach-block"><span>{escape_html(copy["examples_label"])}</span>{example_html}</div>'
    st.markdown(
        f"""
        <div class="ct-coach">
          <p class="ct-kicker">{escape_html(copy["title"])}</p>
          {blocks}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_thought_log(notes: Sequence[Mapping[str, Any]]) -> None:
    st = _st()
    if not notes:
        st.markdown(
            '<p class="ct-coach-empty">寫下你此刻的想法或判斷，這裡會給簡短回應。這段不會進入模擬逐字稿。</p>',
            unsafe_allow_html=True,
        )
        return
    items: list[str] = []
    for note in notes[-8:]:
        kind = "student" if str(note.get("role", "")) == "student" else "coach"
        label = "你的想法" if kind == "student" else "回應"
        items.append(
            f'<div class="ct-thought-item {kind}"><span>{label}</span>'
            f"{escape_html(note.get('content', ''))}</div>"
        )
    st.markdown(f'<div class="ct-thought-log">{"".join(items)}</div>', unsafe_allow_html=True)


def render_meta_grid(items: Sequence[tuple[str, str]]) -> None:
    st = _st()
    cells = "".join(
        f'<div class="ct-meta-item"><span>{escape_html(label)}</span><strong>{escape_html(value)}</strong></div>'
        for label, value in items
    )
    st.markdown(f'<div class="ct-meta-grid">{cells}</div>', unsafe_allow_html=True)


def render_transcript(turns: Sequence[Mapping[str, Any]]) -> None:
    st = _st()
    if not turns:
        render_empty_state("尚無對話內容", "這次 Session 還沒有逐字稿。")
        return
    parts: list[str] = []
    for turn in turns:
        role = ROLE_LABELS.get(str(turn.get("speaker_role", "")), str(turn.get("speaker_role", "")))
        idx = turn.get("turn_index", "")
        body = escape_html(turn.get("content_raw", ""))
        parts.append(
            f'<div class="ct-turn"><div class="who">{escape_html(idx)} · {escape_html(role)}</div>'
            f'<div class="body">{body}</div></div>'
        )
    st.markdown(f'<div class="ct-transcript">{"".join(parts)}</div>', unsafe_allow_html=True)
