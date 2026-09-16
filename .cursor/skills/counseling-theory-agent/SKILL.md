---
name: counseling-theory-agent
description: >-
  Guides coding and content changes in the counseling theory skills training
  Agent (Streamlit + Gemini + SQLite): 11 schools, experience vs practice
  modes, three Gemini engines (plan, chat analysis, chatbot), technique library,
  prompts, sessions, continuation threads, formative assessments, SkillEvents,
  whitelist OTP login, safety routing, transcripts, and the teacher research
  backend. Use when working in counseling_theory, editing schools or techniques,
  prompts, llm_pipeline, app.py session flows, data_store schemas, ChatLogs, or
  research logging.
---

# Counseling Theory Agent

University teaching simulator (Traditional Chinese UI). Not therapy, diagnosis, or crisis care.

## When to apply

Use for any change in this repo: schools, techniques, prompts, Streamlit flows, SQLite schemas, safety, auth, transcripts, teacher dashboard, tests, or docs.

## Product invariants

Do not violate these unless the user explicitly changes the product contract:

1. **11 schools × 5 techniques.** Practice and experience both use **exactly 3** techniques per session. Experience uses `experience_default`; practice is student-chosen.
2. **`src/theory_library.py` is the only source of school/technique names.** UI, prompts, and tests must load from `SCHOOLS`. Never invent a technique name in a prompt or screen.
3. **Three in-session Gemini engines, then a separate post-session assessment.** Planner is used for **practice** (to generate the case) and for **進階** experience. Experience **初階／中階** skip the planner and use analyzer + chatbot only. Analyzer (each student turn) is internal JSON **except** 初階／中階, which show a simple `turn_review` in the chat. **Practice 初階** also shows a side plan (`student_guide` + `example_replies`) that must follow the current talk; do **not** repeat `turn_review` on the side. **Practice 中階** keeps the side thought box and in-chat sentence notes, but **no** plan panel. **Experience 初階** shows observer notes (`student_guide` only: what the counselor is doing now) and no next-line examples. The chatbot must not teach, score, or name techniques. **進階** shows formative review only after the session ends.
4. **Experience never scores the student-as-client.** Practice scores counselor performance only. Experience 初階／中階 `turn_review` explains the AI counselor sentence (goal / expected effect), never the student’s client talk. Teacher grades append to `TeacherGrades` and **never overwrite** `Assessments` or `raw_model_output`.
5. **`ChatLogs.content_raw` is append-only during a session.** Preserve full text, including parenthetical nonverbal cues. Do not rewrite past turns when re-scoring. Exception requested by product: after **experience** 「結束晤談」, ask research consent. **不願意：** keep only the session completion stub (school / time / duration); **delete ChatLogs** and do not persist Assessments/SkillEvents, 示範解析, or counselor quotes. **願意：** keep identifiable transcript and demo analysis as now. **願意 + 匿名：** student Sessions row is like 不願意 (consent `anonymous`, no process); copy the counseling process into `AnonymousSessions` / `AnonymousChatLogs` with timestamps and **no** participant_id, email, or thread id. Practice transcripts stay. 實作初階／中階旁欄「當下的想法與判斷」只存在 `session_state.coach_thoughts`，不得寫入 `ChatLogs` 或逐字稿。體驗（學生當個案）不顯示想法框。
6. **Student Gemini API Key stays in Streamlit session memory, and may be remembered in this browser's localStorage after a successful test.** Never write it to SQLite, transcripts, logs, or exceptions.
7. **User-facing copy and model prompts are Traditional Chinese.** Identifiers (`school_id`, `technique_id`) are English `snake_case`.
8. **Login is SQLite whitelist + OTP, then password.** First login uses OTP and must set a password. Later logins may use the password. Domain shortcut is not used. Seed from secrets; teachers can add/disable emails. Never store plaintext passwords or API keys.

## Directory map

| Path | Role |
| --- | --- |
| `app.py` | Streamlit UI: whitelist OTP login, student chat, continuation, teacher dashboard, ZIP export |
| `src/theory_library.py` | `SCHOOLS`, `PRACTICE_THEMES`, technique validation |
| `src/prompts.py` | Knowledge block, planner, analyzer, chatbot, evaluator, experience analysis, snapshot |
| `src/llm_pipeline.py` | Plan once / analyze then chat; fail-open analysis |
| `src/session_service.py` | Session/turn dicts, `continuation_role`, duration, completion status |
| `src/data_store.py` | `SCHEMAS`, `SqliteStore`, `MemoryStore`; API keys must not enter this module |
| `src/gemini_client.py` | Gemini wrapper, JSON parse, gemini-3 `thinking_config`; Streamlit uses the browser router |
| `src/gemini_router.py` | Hidden iframe: student browser POSTs `generateContent`; Python caches by `call_id` |
| `src/safety.py` | Immediate-risk keyword routing and PII block (interface only, not clinical assessment) |
| `src/auth.py` | OTP hash, whitelist check via store, teacher role |
| `src/transcript.py` | Nonverbal extraction, UTF-8-SIG TXT download |
| `src/config.py` | Secrets → `AppConfig`, `DEFAULT_SETTINGS` |
| `scripts/check_project.py` | Offline 11×5×3 + required-file check |
| `tests/` | Library, prompts, safety, transcript, auth, SqliteStore |
| `docs/` | Deploy, student guide, data dictionary, acceptance, build report |

IDs, sheet columns, speaker roles, and rubric JSON: [reference.md](reference.md). Edit walkthroughs: [examples.md](examples.md).

## Domain terms

| Term | Meaning |
| --- | --- |
| **school** / `school_id` | One of 11 counseling theories |
| **technique** | Fixed skill on a school (`id`, `name`, `short`, `affordance`) |
| **affordance** | Case condition so that technique can reasonably be practiced |
| **experience** | Student = client; AI = same-school demo counselor |
| **practice** | Student = counselor; AI = standardized client generated for the 3 techniques |
| **session** | One sitting (`session_id`); status `in_progress` / `completed` / `safety_stopped` |
| **thread** | Cross-session continuation of the same AI role (`conversation_thread_id`) |
| **continuation_role** | `ai_client` (practice) or `ai_counselor` (experience) |
| **formative assessment** | Post-session AI JSON; not a validated test score |
| **nonverbal** | Observable behavior in `（）` or `()`; not inner states or diagnoses |

## Workflows

### Edit schools or techniques

1. Change only `src/theory_library.py` first.
2. Keep **5 techniques** and **3 valid `experience_default` IDs** per school unless the user is changing that contract (then update `scripts/check_project.py`, `tests/test_theory_library.py`, UI copy that says 「五項」「恰好三項」, and `docs/`).
3. Each technique needs a unique `id`, Chinese `name`/`short`, and an `affordance` the case prompt can satisfy.
4. Run the verification commands below.
5. Do not hardcode school or technique names in `app.py` or `prompts.py`.

### Edit prompts or roles

1. Edit `src/prompts.py` (and `src/llm_pipeline.py` call wiring). Keep `COMMON_SYSTEM`. Inject `build_knowledge_block` into planner, analyzer, and chatbot.
2. Practice chatbot: AI **only** as client. Experience chatbot: AI **only** as that school's counselor. Neither may name techniques mid-session. Plan/analysis JSON stays internal.
3. Evaluator JSON and experience-analysis JSON are parse contracts (`parse_json_response`). Changing keys requires UI + `save_assessment` mapping updates.
4. If prompt *meaning* changes, bump `prompt_version` and/or `rubric_version` in config defaults (research versioning). Do not rewrite old `raw_model_output`.
5. Add/adjust tests in `tests/test_prompts.py` for role boundaries (`只能扮演標準化模擬個案`, `missed_opportunity` vs `no_opportunity`).

### Edit session, chat, or teacher UI

1. Student path: API key gate → planner → chat (analyze then chatbot) → `finalize_session` (assessment + snapshot + thread upsert).
2. Practice start uses planner JSON (includes case fields) before the first AI turn. Continuation reuses `case_data`, `counseling_plan`, `chat_analysis`, `latest_snapshot`, and last 6 `recent_turns`, then re-plans.
3. Safety: `detect_pii` blocks send; `detect_immediate_risk` stops simulation, writes `RiskEvents`, sets `safety_stopped`. Keep crisis patterns **specific** so classroom suicide-prevention talk does not trip them (`tests/test_safety.py`).
4. Teacher path is Email-filtered research review plus whitelist admin. Export ZIP includes IdentityMap and whitelist (PII); docs warn to store them separately.

### Edit SQLite schema

1. Change `SCHEMAS` in `src/data_store.py`. `SqliteStore.ensure_schema` **adds missing columns**; it does not rename or delete.
2. Prefer new columns. Never change the meaning of `content_raw` or `raw_model_output`. Persist `counseling_plan` and `chat_analysis` on Threads.
3. Re-scoring = new `assessment_id` (+ new `rubric_version` if the rubric changed).
4. Keep `MemoryStore` method-compatible with `SqliteStore`.

## Conventions

- Session modes: only `experience` | `practice`.
- Speaker roles: `student_client`, `student_counselor`, `ai_client`, `ai_counselor`, `system`.
- Practice themes: keys of `PRACTICE_THEMES` (Chinese labels in UI). Difficulty UI: `初階` / `中階` / `進階`. Practice 初階 = live plan + examples beside chat + in-chat sentence notes + a side thought box (not written to `ChatLogs`). Practice 中階 = in-chat sentence notes + a side thought box, no plan panel. Experience 初階 = observer notes beside chat (no examples, no thought box) + in-chat sentence notes. Experience 中階 = in-chat sentence notes only. 進階 = end-of-session review only. Experience never scores the student-as-client.
- `participant_id` is `P-` + 12 hex from `sha256(salt:email)`. Salt is a secret; never commit it. Anonymous counseling process uses `AnonymousSessions` / `AnonymousChatLogs` without `participant_id`.
- JSON cells: `json_cell` / `parse_json_cell` (`ensure_ascii=False`).
- Transcripts: UTF-8-SIG; filename `theory_agent_transcript_<session_id>.txt`.
- Timezone default `Asia/Taipei`; timestamps ISO with offset.

## Verification

Python 3.11+. No secrets required for:

```bash
python scripts/check_project.py
python -m pytest -q
```

Local UI: copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml` (gitignored), then `streamlit run app.py`.

After library edits: 11 schools, 5 techniques, 3 defaults. After prompt edits: role-separation tests still pass. After schema edits: header lists match `SCHEMAS` and dictionary doc. After UI edits: Traditional Chinese; experience has no student score; practice still requires 3 techniques.

`check_project.py` currently requires `.streamlit/secrets.toml.example` (and README also lists `.github/workflows/tests.yml`). Restore those files if missing rather than deleting the checks.

## Gotchas

- **Production store is Google Sheets when `SPREADSHEET_ID` and service-account JSON are set.** Path `[app].sqlite_path` default `data/app.sqlite` is local/demo only (gitignored). Streamlit Cloud reboot wipes that file. `REQUIRE_SHEETS=true` must not fall back to SQLite. `GoogleSheetsStore` uses the same `SCHEMAS` (including Anonymous* and AuthSessions). **Do not re-run `ensure_schema` / `seed_whitelist` against Sheets on every Streamlit rerun** (login, widgets, and each chat turn all rerun `app.py`). The Sheets API quota is about 60 reads/minute per service account; 13 header reads per page load will 429 and crash the login screen. Schema is ensured in the constructor; later calls must no-op. Retry only 429/5xx. ChatLogs/Sessions/Threads/Assessments/SkillEvents writes share a **process-wide spike buffer** (flush at 80 rows or 15s). It is not a durable queue: a Cloud reboot can drop a few seconds of unflushed rows. Login/safety sheets (`whitelist`, `AuthSessions`, `IdentityMap`, `Settings`, `RiskEvents`) still write immediately. `SqliteStore` / `MemoryStore` stay write-through.
- **Student-browser Gemini router:** Streamlit Cloud builds prompts but does **not** call Gemini. A persistent hidden iframe POSTs `generateContent` and returns `{results:[{request_id, text, model, latency_ms, error}]}`. Cache by stable `call_id`. Raise `GeminiRouterPending` (a `BaseException`) until the iframe finishes. Never write the key to Sheets or logs. Prompt text is visible in DevTools; that is accepted for this classroom app. **Do not remount the iframe per call** (`key=ct_gemini_router`). Streamlit allows that key **once per rerun**; if plan (or another job) just returned, wait for the next rerun before opening chat. A student turn **replies first** (chatbot uses plan + last analysis if any, not this turn’s analyzer). The reply is stored and shown as soon as that packet returns. Analyzer runs **afterwards** to update `turn_review` / side plan; it must not block the visible line. If the student sends again, chat preempts a still-running analysis. End-of-session eval + snapshot stay one parallel batch.
- **Whitelist:** `is_email_allowed(email, store)` checks enabled whitelist rows in the active store. Seed from `[auth].login_allowlist` and `[auth].teacher_emails` (or legacy `[app].teacher_test_emails`). Disabled rows cannot receive OTP. After first OTP, user sets a password (`whitelist.password_hash`). Default teacher `poopoo1993@gmail.com` is seeded with a password if missing. Never export `password_hash`.
- **SMTP:** `[smtp]` or `[email]`. `local_demo_mode` only shows OTP on screen.
- **Gemini 3:** Prefer `thinking_config.thinking_level=low` when the installed `google-genai` ThinkingConfig has that field. Older SDKs (e.g. 1.47) only allow `thinking_budget` and reject `thinking_level` with pydantic `extra_forbidden`. Inspect fields, fall back to `thinking_budget=0` for low, and omit thinking_config if GenerateContentConfig still rejects it.
- **Browser refresh:** Streamlit `session_state` is wiped on F5. Login is restored from a hashed `sid` query token in `AuthSessions` (TTL 12h; SQLite locally, Google Sheets in production). Gemini API Keys may be remembered in **browser localStorage only** after a successful test, never in SQLite or Sheets. Logout deletes the login token, not the browser key list. Skip `AuthSessions` in research ZIP export. Cloud **reboot** is different: local SQLite is destroyed; Sheets data remains.
- **Zhuyin / IME Enter:** `st.chat_input` treats Enter as send. Traditional Chinese Zhuyin uses Enter to confirm a candidate, which would submit a half-finished line. `install_ime_enter_guard` (via `apply_theme`) swallows Enter during `compositionstart`/`isComposing`/keyCode 229 and the duplicate Enter right after `compositionend`. Do not remove that component to “simplify” chat input.
- **Context window:** `AppConfig.recent_context_turns` defaults to 14 but dialogue currently slices `turns[-14:]` in `prompts.py`. Change both if changing window.
- **Stored `temperature`:** `new_session` writes `0.4`; live calls use 0.55 (chatbot), 0.65 (planner), 0.1 (analyzer/eval/snapshot).
- **`Sessions` vs `Threads`:** `school_name` is on the in-memory session and on Threads, not on the Sessions headers—extra keys are dropped on append.
- **Analyzer fail-open:** if analysis JSON fails, chatbot uses last good `chat_analysis` / plan.
- **Experience → SkillEvents:** `save_assessment` expands `skill_events`; experience analysis stores `technique_explanations` in that field. Do not assume every SkillEvents row has `status`.
- **Do not commit** `.streamlit/secrets.toml`, `data/*.sqlite`, API keys, SMTP passwords, or service-account JSON.
