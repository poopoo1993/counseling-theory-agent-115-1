---
name: counseling-theory-agent
description: >-
  Guides coding and content changes in the counseling theory skills training
  Agent (Streamlit + Gemini + Google Sheets): 11 schools, experience vs practice
  modes, technique library, prompts, sessions, continuation threads, formative
  assessments, SkillEvents, OTP login, safety routing, transcripts, and the
  teacher research backend. Use when working in counseling_theory, editing
  schools or techniques, prompts, app.py session flows, data_store schemas,
  ChatLogs, or research logging.
---

# Counseling Theory Agent

University teaching simulator (Traditional Chinese UI). Not therapy, diagnosis, or crisis care.

## When to apply

Use for any change in this repo: schools, techniques, prompts, Streamlit flows, Sheets schemas, safety, auth, transcripts, teacher dashboard, tests, or docs.

## Product invariants

Do not violate these unless the user explicitly changes the product contract:

1. **11 schools × 5 techniques.** Practice and experience both use **exactly 3** techniques per session. Experience uses `experience_default`; practice is student-chosen.
2. **`src/theory_library.py` is the only source of school/technique names.** UI, prompts, and tests must load from `SCHOOLS`. Never invent a technique name in a prompt or screen.
3. **Dialogue and assessment are separate Gemini calls.** In-session AI must not teach, score, or name techniques. Scoring/analysis runs only after the student ends the session.
4. **Experience never scores the student-as-client.** Practice scores counselor performance only. Teacher grades append to `TeacherGrades` and **never overwrite** `Assessments` or `raw_model_output`.
5. **`ChatLogs.content_raw` is append-only.** Preserve full text, including parenthetical nonverbal cues. Do not rewrite past turns when re-scoring.
6. **Student Gemini API Key stays in Streamlit session memory.** Never write it to Sheets, transcripts, logs, or exceptions.
7. **User-facing copy and model prompts are Traditional Chinese.** Identifiers (`school_id`, `technique_id`) are English `snake_case`.

## Directory map

| Path | Role |
| --- | --- |
| `app.py` | Streamlit UI: OTP login, student chat, continuation, teacher dashboard, ZIP export |
| `src/theory_library.py` | `SCHOOLS`, `PRACTICE_THEMES`, technique validation |
| `src/prompts.py` | Case, dialogue, evaluator, experience analysis, continuation snapshot |
| `src/session_service.py` | Session/turn dicts, `continuation_role`, duration, completion status |
| `src/data_store.py` | `SCHEMAS`, `GoogleSheetsStore`, `MemoryStore`; API keys must not enter this module |
| `src/gemini_client.py` | Gemini wrapper, JSON parse, gemini-3 `thinking_config` |
| `src/safety.py` | Immediate-risk keyword routing and PII block (interface only, not clinical assessment) |
| `src/auth.py` | OTP hash, `@hcu.edu.tw` domain, teacher allowlist |
| `src/transcript.py` | Nonverbal extraction, UTF-8-SIG TXT download |
| `src/config.py` | Secrets → `AppConfig`, `DEFAULT_SETTINGS` |
| `scripts/check_project.py` | Offline 11×5×3 + required-file check |
| `tests/` | Library, prompts, safety, transcript, MemoryStore |
| `docs/` | Deploy, Sheets, student guide, data dictionary, acceptance, build report |

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

1. Edit `src/prompts.py` only. Keep `COMMON_SYSTEM` (teaching simulation, no PII, Traditional Chinese, observable nonverbal only).
2. Practice dialogue: AI **only** as client. Experience dialogue: AI **only** as that school's counselor. Neither may name techniques mid-session.
3. Evaluator JSON and experience-analysis JSON are parse contracts (`parse_json_response`). Changing keys requires UI + `save_assessment` mapping updates.
4. If prompt *meaning* changes, bump `prompt_version` and/or `rubric_version` in config defaults (research versioning). Do not rewrite old `raw_model_output`.
5. Add/adjust tests in `tests/test_prompts.py` for role boundaries (`只能扮演標準化模擬個案`, `missed_opportunity` vs `no_opportunity`).

### Edit session, chat, or teacher UI

1. Student path: API key gate → new session or continuation → chat → `finalize_session` (assessment + snapshot + thread upsert).
2. Practice start generates a case JSON **before** the first AI turn. Continuation reuses `case_data`, `latest_snapshot`, and last 6 `recent_turns`.
3. Safety: `detect_pii` blocks send; `detect_immediate_risk` stops simulation, writes `RiskEvents`, sets `safety_stopped`. Keep crisis patterns **specific** so classroom suicide-prevention talk does not trip them (`tests/test_safety.py`).
4. Teacher path is Email-filtered research review. Export ZIP includes IdentityMap (PII); docs warn to store it separately.

### Edit Google Sheets schema

1. Change `SCHEMAS` in `src/data_store.py`. `ensure_schema` **adds missing headers**; it does not rename or delete.
2. Prefer new columns. Never change the meaning of `content_raw` or `raw_model_output`.
3. Re-scoring = new `assessment_id` (+ new `rubric_version` if the rubric changed).
4. Update `docs/RESEARCH_DATA_DICTIONARY.md`.
5. Keep `MemoryStore` method-compatible with `GoogleSheetsStore`.

## Conventions

- Session modes: only `experience` | `practice`.
- Speaker roles: `student_client`, `student_counselor`, `ai_client`, `ai_counselor`, `system`.
- Practice themes: keys of `PRACTICE_THEMES` (Chinese labels in UI). Difficulty UI: `初階` / `中階` / `進階`.
- `participant_id` is `P-` + 12 hex from `sha256(salt:email)`. Salt is a secret; never commit it.
- JSON cells in Sheets: `json_cell` / `parse_json_cell` (`ensure_ascii=False`).
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

- **Sheets vs memory:** If Sheets auth fails, store is `MemoryStore`. Login is blocked unless `app.local_demo_mode` is true. Do not print credential fragments from Google auth errors.
- **Secrets compatibility:** Spreadsheet: top-level `SPREADSHEET_ID` + `GOOGLE_SERVICE_ACCOUNT_JSON`, or `[google_sheets]`, or `[gcp_service_account]`. SMTP: `[smtp]` or `[email]`. Teachers: `[auth].teacher_emails` or legacy `[app].teacher_test_emails`. `REQUIRE_SHEETS` appears in docs but is unused in code; real gate is Sheets connect + `local_demo_mode`.
- **Private keys:** Accept full PEM or body-only Base64; `normalize_private_key` reconstructs PKCS#8. Never log PEM text.
- **Gemini 3:** `thinking_config.thinking_level` must stay `low` for short replies, or visible text can be empty.
- **Context window:** `AppConfig.recent_context_turns` defaults to 14 but dialogue currently slices `turns[-14:]` in `prompts.py`. Change both if changing window.
- **Stored `temperature`:** `new_session` writes `0.4`; live calls use 0.55 (dialogue), 0.65 (case), 0.1 (eval/snapshot). Do not treat the Sessions column as the actual call temperature.
- **`Sessions` vs `Threads`:** `school_name` is on the in-memory session and on Threads, not on the Sessions sheet headers—extra keys are dropped on append.
- **Experience → SkillEvents:** `save_assessment` expands `skill_events`; experience analysis stores `technique_explanations` in that field (different keys than practice `used|missed_opportunity|...`). Do not assume every SkillEvents row has `status`.
- **Do not commit** `.streamlit/secrets.toml`, API keys, SMTP passwords, or service-account JSON.
