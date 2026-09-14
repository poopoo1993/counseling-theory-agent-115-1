# Examples

## Edit an existing technique (keep 5×3 contract)

Goal: clarify CBT `automatic_thoughts` affordance so case generation produces a catchable thought.

1. In `src/theory_library.py`, change only that technique’s `short` and/or `affordance`. Leave `id` stable (SkillEvents and prompts key on it).
2. Do not add a sixth technique.
3. Run:

```bash
python scripts/check_project.py
python -m pytest tests/test_theory_library.py tests/test_prompts.py -q
```

IDs are research keys. Renaming `automatic_thoughts` → `auto_thought` breaks old SkillEvents joins; add a new id only if the user accepts a data break and a `rubric_version` bump.

## Add a twelfth school (explicit contract change)

Only if the user asks to move off the 11-school product:

1. Append a new `school_id` in `SCHOOLS` with 5 techniques and 3 `experience_default` ids.
2. Change `len(SCHOOLS) != 11` in `scripts/check_project.py` and `tests/test_theory_library.py`.
3. Update README/docs copy that says 「11 個」.
4. UI `selectbox` already iterates `SCHOOLS`; no `app.py` list to edit.
5. Keep prompts loading via `get_school` / `get_techniques`.

## Change evaluator behavior without mixing it into chat

Wrong: add “tell the student the score” to `build_dialogue_prompt`.

Right:

1. Edit `build_practice_evaluator_prompt` JSON instructions (e.g. stricter evidence).
2. If dimension keys change, update `finalize_session` record mapping and `render_feedback`.
3. Bump `rubric_version` default in `src/config.py`.
4. Extend `tests/test_prompts.py` assertions (`missed_opportunity`, `no_opportunity`, `extension_skill` must remain distinct).
5. Old Assessments rows stay as-is; new sessions get the new version.

## Add a Sheets column

Example: persist actual Gemini temperature on Sessions.

1. Append `"call_temperature"` to `SCHEMAS["Sessions"]` (do not reuse or redefine `temperature` meaning for old rows).
2. Pass the value in `new_session` / `start_session`.
3. `ensure_schema` will add the missing header on next Sheets connect.
4. Document the column in `docs/RESEARCH_DATA_DICTIONARY.md`.
5. MemoryStore uses the same `SCHEMAS` keys via `append`; no second schema.

Do not rename `content_raw`. Re-scoring must `append` a new Assessments row.

## Practice vs experience role check

After touching `build_dialogue_prompt`, this must still hold:

```python
system, prompt = build_dialogue_prompt(
    mode="practice", school_id="cbt",
    selected_ids=["automatic_thoughts", "evidence_review", "cognitive_restructuring"],
    turns=[], latest_student_message="你當時腦中浮現什麼？",
    case_data={"case_id": "demo"}, continuation_snapshot=None,
)
assert "只能扮演標準化模擬個案" in system
assert "不得變成教師" in system
```

Experience system must contain the school name as 示範諮商師 and must forbid 技巧名稱 mid-session.

## Local demo without Sheets

In gitignored `.streamlit/secrets.toml`:

```toml
[app]
local_demo_mode = true
title = "諮商理論技巧訓練 Agent"
teacher_test_emails = ["you@example.com"]
```

Login shows the OTP on screen. Data dies on refresh. Never enable `local_demo_mode` in production Secrets if research logs must persist.
