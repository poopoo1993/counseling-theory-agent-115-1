from src.prompts import (
    analysis_for_chatbot,
    build_chat_analysis_prompt,
    build_counseling_plan_prompt,
    build_dialogue_prompt,
    build_knowledge_block,
    build_practice_evaluator_prompt,
    live_coaching_enabled,
)


SELECTED = ["automatic_thoughts", "evidence_review", "cognitive_restructuring"]


def test_practice_dialogue_prompt_keeps_ai_as_client():
    system, prompt = build_dialogue_prompt(
        mode="practice", school_id="cbt", selected_ids=SELECTED, turns=[],
        latest_student_message="你當時腦中浮現什麼？", case_data={"case_id": "demo"},
        continuation_snapshot=None,
    )
    assert "只能扮演標準化模擬個案" in system
    assert "不得變成教師" in system
    assert "學生諮商師最新一句" in prompt
    assert "知識庫" in prompt


def test_experience_dialogue_forbids_technique_names():
    system, prompt = build_dialogue_prompt(
        mode="experience", school_id="cbt", selected_ids=SELECTED, turns=[],
        latest_student_message="我最近很累。", case_data=None,
        continuation_snapshot=None,
        counseling_plan={"phase_goals": ["建立關係"]},
        chat_analysis={"next_focus": "了解情緒"},
    )
    assert "不得揭露技巧名稱" in system
    assert "示範諮商師" in system
    assert "技巧名稱" in prompt


def test_knowledge_block_uses_library_ids_only():
    block = build_knowledge_block("cbt", SELECTED)
    assert "automatic_thoughts" in block
    assert "辨識自動化思考" in block
    assert "school_id=cbt" in block


def test_planner_and_analyzer_json_contracts():
    plan = build_counseling_plan_prompt(
        mode="practice", school_id="cbt", selected_ids=SELECTED,
        theme="課業與表現壓力", difficulty="中階",
    )
    assert "info_targets" in plan
    assert "public_opening" in plan
    assert "phase_goals" in plan
    analysis = build_chat_analysis_prompt(
        mode="practice", school_id="cbt", selected_ids=SELECTED,
        counseling_plan={"info_targets": []}, prior_analysis=None,
        turns=[], latest_student_message="你腦中浮現什麼？",
        difficulty="中階",
    )
    assert "hidden_or_incomplete" in analysis
    assert "next_focus" in analysis
    assert "不得發明" in analysis
    assert "student_guide" not in analysis
    assert "整體回饋只在晤談結束後" in analysis


def test_easy_practice_analyzer_adds_live_coaching_fields():
    assert live_coaching_enabled("practice", "初階")
    assert not live_coaching_enabled("practice", "中階")
    assert not live_coaching_enabled("practice", "進階")
    assert not live_coaching_enabled("experience", "初階")
    prompt = build_chat_analysis_prompt(
        mode="practice", school_id="cbt", selected_ids=SELECTED,
        counseling_plan={"info_targets": []}, prior_analysis=None,
        turns=[], latest_student_message="你當時腦中浮現什麼？",
        difficulty="初階",
    )
    assert "student_guide" in prompt
    assert "turn_review" in prompt
    assert "實作初階" in prompt


def test_analysis_for_chatbot_strips_student_visible_fields():
    hidden = analysis_for_chatbot({
        "next_focus": "簡短回答",
        "student_guide": "試試反映情緒",
        "turn_review": {"verdict": "合宜", "comment": "這句有抓住感受"},
    })
    assert hidden["next_focus"] == "簡短回答"
    assert "student_guide" not in hidden
    assert "turn_review" not in hidden


def test_evaluator_distinguishes_missed_and_no_opportunity():
    prompt = build_practice_evaluator_prompt("cbt", SELECTED, [])
    assert "missed_opportunity" in prompt
    assert "no_opportunity" in prompt
    assert "extension_skill" in prompt
