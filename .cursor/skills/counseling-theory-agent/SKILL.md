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
3. **Three in-session Gemini engines, then a separate post-session assessment.** Planner (once per session/continuation) and analyzer (each student turn) are internal JSON. Only the chatbot is visible. Chatbot must not teach, score, or name techniques. Formative scoring/analysis runs only after the student ends the session.
4. **Experience never scores the student-as-client.** Practice scores counselor performance only. Teacher grades append to `TeacherGrades` and **never overwrite** `Assessments` or `raw_model_output`.
5. **`ChatLogs.content_raw` is append-only.** Preserve full text, including parenthetical nonverbal cues. Do not rewrite past turns when re-scoring.
6. **Student Gemini API Key stays in Streamlit session memory.** Never write it to SQLite, transcripts, logs, or exceptions.
7. **User-facing copy and model prompts are Traditional Chinese.** Identifiers (`school_id`, `technique_id`) are English `snake_case`.
8. **Login is SQLite whitelist + OTP.** Domain shortcut is not used. Seed from secrets; teachers can add/disable emails.

## Directory map

| Path | Role |
| --- | --- |
| `app.py` | Streamlit UI: whitelist OTP login, student chat, continuation, teacher dashboard, ZIP export |
| `src/theory_library.py` | `SCHOOLS`, `PRACTICE_THEMES`, technique validation |
| `src/prompts.py` | Knowledge block, planner, analyzer, chatbot, evaluator, experience analysis, snapshot |
| `src/llm_pipeline.py` | Plan once / analyze then chat; fail-open analysis |
| `src/session_service.py` | Session/turn dicts, `continuation_role`, duration, completion status |
| `src/data_store.py` | `SCHEMAS`, `SqliteStore`, `MemoryStore`; API keys must not enter this module |
| `src/gemini_client.py` | Gemini wrapper, JSON parse, gemini-3 `thinking_config` |
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
- Practice themes: keys of `PRACTICE_THEMES` (Chinese labels in UI). Difficulty UI: `初階` / `中階` / `進階`.
- `participant_id` is `P-` + 12 hex from `sha256(salt:email)`. Salt is a secret; never commit it.
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

- **SQLite is the login/chat store.** Path `app.sqlite_path` default `data/app.sqlite` (gitignored). Login does not require Google Sheets. `GoogleSheetsStore` remains in code but is unused.
- **Whitelist:** `is_email_allowed(email, store)` checks enabled SQLite rows only. Seed from `[auth].login_allowlist` and `[auth].teacher_emails` (or legacy `[app].teacher_test_emails`). Disabled rows cannot receive OTP.
- **SMTP:** `[smtp]` or `[email]`. `local_demo_mode` only shows OTP on screen.
- **Gemini 3:** `thinking_config.thinking_level` must stay `low` for short replies, or visible text can be empty.
- **Context window:** `AppConfig.recent_context_turns` defaults to 14 but dialogue currently slices `turns[-14:]` in `prompts.py`. Change both if changing window.
- **Stored `temperature`:** `new_session` writes `0.4`; live calls use 0.55 (chatbot), 0.65 (planner), 0.1 (analyzer/eval/snapshot).
- **`Sessions` vs `Threads`:** `school_name` is on the in-memory session and on Threads, not on the Sessions headers—extra keys are dropped on append.
- **Analyzer fail-open:** if analysis JSON fails, chatbot uses last good `chat_analysis` / plan.
- **Experience → SkillEvents:** `save_assessment` expands `skill_events`; experience analysis stores `technique_explanations` in that field. Do not assume every SkillEvents row has `status`.
- **Do not commit** `.streamlit/secrets.toml`, `data/*.sqlite`, API keys, SMTP passwords, or service-account JSON.
