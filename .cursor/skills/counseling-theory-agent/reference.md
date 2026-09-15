# Reference: IDs, schemas, roles

Load this when adding a school/technique, changing Sheets columns, or mapping assessment JSON.

## Schools and techniques

`SCHOOLS` insertion order is the UI order.

| school_id | Chinese name | technique_ids (5) | experience_default (3) |
| --- | --- | --- | --- |
| `psychodynamic` | 精神分析／心理動力 | `free_association`, `resistance_exploration`, `transference_pattern`, `clarification_confrontation`, `tentative_interpretation` | `free_association`, `resistance_exploration`, `tentative_interpretation` |
| `adlerian` | 阿德勒學派 | `family_constellation`, `early_recollection`, `lifestyle`, `social_interest`, `encouragement_reorientation` | `family_constellation`, `early_recollection`, `social_interest` |
| `person_centered` | 個人中心治療 | `empathic_reflection`, `feeling_reflection`, `paraphrase_clarification`, `congruence`, `here_now_relationship` | `empathic_reflection`, `feeling_reflection`, `congruence` |
| `gestalt` | 完形治療 | `present_awareness`, `body_awareness`, `empty_chair`, `two_chair`, `unfinished_experiment` | `present_awareness`, `body_awareness`, `empty_chair` |
| `behavior` | 行為治療 | `functional_analysis`, `self_monitoring`, `relaxation`, `graded_exposure`, `reinforcement_activation` | `functional_analysis`, `self_monitoring`, `graded_exposure` |
| `cbt` | Beck 認知治療／CBT | `automatic_thoughts`, `evidence_review`, `cognitive_restructuring`, `behavioral_experiment`, `activity_homework` | `automatic_thoughts`, `evidence_review`, `cognitive_restructuring` |
| `rebt` | 理情行為治療 REBT | `abc_model`, `irrational_belief`, `disputation`, `rational_emotive_imagery`, `behavioral_belief_homework` | `abc_model`, `irrational_belief`, `disputation` |
| `reality` | 現實治療／選擇理論 | `wants`, `doing`, `evaluation`, `planning`, `choice_responsibility` | `wants`, `evaluation`, `planning` |
| `sfbt` | 焦點解決短期治療 SFBT | `miracle_question`, `exception_question`, `scaling_question`, `coping_question`, `compliment_next_step` | `exception_question`, `scaling_question`, `miracle_question` |
| `narrative` | 敘事治療 | `externalization`, `problem_naming`, `relative_influence`, `unique_outcome`, `reauthoring` | `externalization`, `unique_outcome`, `reauthoring` |
| `positive` | 正向心理治療 | `strength_identification`, `strength_use`, `three_good_things`, `gratitude`, `hope_meaning_best_self` | `strength_identification`, `three_good_things`, `hope_meaning_best_self` |

Exact default ID lists live in `src/theory_library.py`. Technique object shape:

```python
{"id": "automatic_thoughts", "name": "辨識自動化思考", "short": "…", "affordance": "…"}
```

## Practice themes

| theme_id | Label |
| --- | --- |
| `academic` | 課業與表現壓力 |
| `relationship` | 人際關係與歸屬 |
| `career` | 生涯選擇與自我懷疑 |
| `family` | 家庭期待與界線 |
| `internship` | 實習壓力與角色適應 |
| `self_worth` | 自我價值與失敗經驗 |

## Speaker roles and completion

| `speaker_role` | Who | Mode |
| --- | --- | --- |
| `student_client` | Student | experience |
| `student_counselor` | Student | practice |
| `ai_client` | Gemini client | practice |
| `ai_counselor` | Gemini counselor | experience |
| `system` | Safety/error | both |

`continuation_role` on session/thread: `ai_client` if practice else `ai_counselor`.

`completion_status`: `in_progress` | `completed` | `safety_stopped`.

Teacher dashboard lists sessions with `completed` or `safety_stopped`.

## Sheets / SQLite (`SCHEMAS`)

SQLite tables (same names as former worksheets). Append-only research events: ChatLogs, Assessments, SkillEvents, TeacherGrades, RiskEvents. Upserts: whitelist (`email`), IdentityMap (`participant_id`), Sessions (`session_id`), Threads (`conversation_thread_id`), Settings (`key`).

**whitelist:** `email`, `role`, `enabled`, `created_at`

**IdentityMap:** `participant_id`, `email`, `created_at`, `last_login_at`, `role`

**Sessions:** `session_id`, `conversation_thread_id`, `participant_id`, `agent_type` (always `theory`), `mode`, `continuation_role`, `started_at`, `ended_at`, `duration_seconds`, `case_id`, `school_id`, `selected_techniques`, `selected_technique_names`, `model_name`, `prompt_version`, `temperature`, `completion_status`, `theme`, `difficulty`

**ChatLogs:** `turn_id`, `session_id`, `conversation_thread_id`, `participant_id`, `turn_index`, `speaker_role`, `speaker_id`, `content_raw`, `nonverbal_cues`, `timestamp`, `stage_at_turn`, `skill_labels`, `selected_skill_match`, `latency_ms`, `error_flag`

**Threads:** `conversation_thread_id`, `participant_id`, `mode`, `continuation_role`, `school_id`, `school_name`, `selected_techniques`, `selected_technique_names`, `case_id`, `case_data`, `counseling_plan`, `chat_analysis`, `latest_snapshot`, `last_session_id`, `recent_turns`, `difficulty`, `updated_at`, `status`

**Assessments:** `assessment_id`, `session_id`, `participant_id`, `mode`, `school_id`, `rubric_version`, `total_score`, `dimension_scores`, `skill_events`, `strengths`, `improvement_points`, `quoted_examples`, `next_practice_focus`, `encouragement`, `raw_model_output`, `parsed_json`, `created_at`

**SkillEvents:** `assessment_id`, `session_id`, `participant_id`, `technique_id`, `status`, `turn_index`, `quality`, `evidence_quote`, `effect`

**TeacherGrades:** `grade_id`, `session_id`, `participant_id`, `teacher_email`, `teacher_score`, `teacher_comment`, `created_at`

**Settings:** `key`, `value`, `updated_at`, `updated_by`

**RiskEvents:** `risk_event_id`, `session_id`, `participant_id`, `timestamp`, `event_type`, `action_taken`, `content_redacted`

Default settings keys: `system_enabled`, `open_start`, `open_end`, `max_sessions_per_student`, `duration_experience_min`, `duration_practice_min`, `allowed_modes`, `student_feedback_visible`, `student_score_visible`.

## Practice case JSON

Produced by the **planner** at practice session start (`response_json=True`), not a separate case-only call:

- `case_id`, `display_name`, `public_opening`, `persona`, `presenting_problem`
- `hidden_formulation` (never shown to student)
- `disclosure_layers` (3 strings)
- `resistance_rules`, `nonverbal_baseline` (max 3)

Experience sessions use `case_id` = `student_topic` and no case JSON.

## Practice evaluator JSON

Five dimensions, each 0–20, `total_score` 0–100:

- `theory_fit`, `selected_skills`, `timing_process`, `responsiveness`, `communication_professionalism`

`skill_events[].status`: `used` | `missed_opportunity` | `no_opportunity` | `extension_skill`

`skill_events[].quality`: `mechanical` | `appropriate` | `natural_helpful` | `not_observed`

Also: `strengths`, `improvement_points`, `alternative_responses`, `encouragement`, `next_practice_focus`, `limitations`.

`no_opportunity` is not a miss. `extension_skill` (unselected same-school technique) is not a penalty.

## Experience analysis JSON

`mode`: `experience`, `score`: `null`. Fields: `technique_explanations`, `overall_learning`, `encouragement`, `reflection_questions`.

`finalize_session` maps `technique_explanations` into Assessments.`skill_events` and `reflection_questions` into `next_practice_focus`.

## Continuation snapshot JSON

`continuation_role`, `relationship_summary`, `disclosed_topics`, `emotional_state`, `prior_interventions`, `student_response_patterns`, `unfinished_issues`, `next_session_focus`, `ai_role_consistency`.

Thread stores last **6** turns as `recent_turns`. Dialogue prompt also receives the snapshot plus up to 14 recent turns (current + prior context).

## Gemini call defaults

| Call | temperature | max_output_tokens | JSON |
| --- | --- | --- | --- |
| Planner | 0.65 | 1500 | yes |
| Analyzer | 0.1 | 1600 | yes |
| Chatbot (dialogue) | 0.55 | 550 | no |
| Evaluator / experience analysis | 0.1 | 3200 | yes |
| Snapshot | 0.1 | 1600 | yes |
| API key test | 0.0 | 256 | no |

Retry 3 times on 429/quota/timeout/503. Default model config: `gemini-3.8-flash`.

## Auth and config

- Login: enabled SQLite `whitelist` row, then OTP. No open school-domain login.
- Seed: `[auth].login_allowlist` + `[auth].teacher_emails` (legacy `[app].teacher_test_emails`).
- OTP: 6 digits, hashed `salt:sha256` in session state, default TTL 600s, resend cooldown 60s.
- `local_demo_mode`: show OTP on screen.
- `participant_salt` under `[auth]` or `[app]`.
- SQLite path: `[app].sqlite_path` default `data/app.sqlite`.

## Safety

Crisis regexes in `src/safety.py` target **immediate** first-person intent, not academic mention. PII: TW mobile/landline, email, Taiwan ID. Redaction tokens: `[phone_已隱去]`, `[email_已隱去]`, `[taiwan_id_已隱去]`. Crisis copy points to 119/110/1925.
