from src.prompts import (
    analysis_for_chatbot,
    build_chat_analysis_prompt,
    build_counseling_plan_prompt,
    build_dialogue_prompt,
    build_knowledge_block,
    build_practice_evaluator_prompt,
    build_thought_coach_prompt,
    live_coaching_enabled,
    live_plan_visible,
    thought_coach_visible,
    turn_review_visible,
    uses_planner_llm,
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
    assert '"student_guide"' not in analysis
    assert "turn_review" in analysis
    assert "不要輸出諮商計畫或例句" in analysis


def test_easy_practice_analyzer_adds_live_coaching_fields():
    assert live_coaching_enabled("practice", "初階")
    assert live_plan_visible("初階")
    assert thought_coach_visible("practice", "初階")
    assert not thought_coach_visible("experience", "初階")
    assert thought_coach_visible("practice", "中階")
    assert not thought_coach_visible("practice", "進階")
    assert not thought_coach_visible("experience", "中階")
    assert turn_review_visible("中階")
    assert not live_plan_visible("中階")
    assert not live_coaching_enabled("practice", "進階")
    assert live_coaching_enabled("experience", "初階")
    prompt = build_chat_analysis_prompt(
        mode="practice", school_id="cbt", selected_ids=SELECTED,
        counseling_plan={"info_targets": []}, prior_analysis=None,
        turns=[], latest_student_message="你當時腦中浮現什麼？",
        difficulty="初階",
    )
    assert "student_guide" in prompt
    assert "example_replies" in prompt
    assert "turn_review" in prompt
    assert "實作初階" in prompt


def test_experience_easy_and_medium_analyzer_fields():
    easy = build_chat_analysis_prompt(
        mode="experience", school_id="cbt", selected_ids=SELECTED,
        counseling_plan={"info_targets": []}, prior_analysis=None,
        turns=[], latest_student_message="我最近很累。",
        difficulty="初階",
    )
    assert "student_guide" in easy
    assert '"example_replies"' not in easy
    assert "不可預告下一句" in easy
    assert "goal" in easy
    assert "不可評分學生" in easy
    medium = build_chat_analysis_prompt(
        mode="experience", school_id="cbt", selected_ids=SELECTED,
        counseling_plan={"info_targets": []}, prior_analysis=None,
        turns=[], latest_student_message="我最近很累。",
        difficulty="中階",
    )
    assert '"student_guide"' not in medium
    assert '"example_replies"' not in medium
    assert "turn_review" in medium
    hard = build_chat_analysis_prompt(
        mode="experience", school_id="cbt", selected_ids=SELECTED,
        counseling_plan={"info_targets": []}, prior_analysis=None,
        turns=[], latest_student_message="我最近很累。",
        difficulty="進階",
    )
    assert '"student_guide"' not in hard
    assert "turn_review" not in hard
    assert "進階的整體回饋" in hard


def test_planner_used_for_practice_and_hard_experience_only():
    assert uses_planner_llm("practice", "初階")
    assert uses_planner_llm("practice", "進階")
    assert not uses_planner_llm("experience", "初階")
    assert not uses_planner_llm("experience", "中階")
    assert uses_planner_llm("experience", "進階")


def test_analysis_for_chatbot_strips_student_visible_fields():
    hidden = analysis_for_chatbot({
        "next_focus": "簡短回答",
        "student_guide": "試試反映情緒",
        "example_replies": ["你聽起來很累。"],
        "turn_review": {"verdict": "合宜", "comment": "這句有抓住感受"},
    })
    assert hidden["next_focus"] == "簡短回答"
    assert "student_guide" not in hidden
    assert "example_replies" not in hidden
    assert "turn_review" not in hidden


def test_thought_coach_prompt_stays_out_of_simulation_roles():
    system, prompt = build_thought_coach_prompt(
        mode="practice", school_id="cbt", selected_ids=SELECTED,
        turns=[], student_guide="先反映情緒", example_replies=["你聽起來很累。"],
        prior_notes=[], latest_thought="我覺得該問證據了。",
    )
    assert "教學督導" in system
    assert "不得扮演模擬個案" in system
    assert "不要打分數" in system
    assert "我覺得該問證據了。" in prompt
    system_ex, prompt_ex = build_thought_coach_prompt(
        mode="experience", school_id="cbt", selected_ids=SELECTED,
        turns=[], student_guide="建立關係", example_replies=[],
        prior_notes=[{"role": "student", "content": "他好像在繞圈子"}],
        latest_thought="這是不是同理？",
    )
    assert "不得評分學生的個案表現" in system_ex
    assert "這是不是同理？" in prompt_ex
    assert "模擬逐字稿" in prompt_ex


def test_evaluator_distinguishes_missed_and_no_opportunity():
    prompt = build_practice_evaluator_prompt("cbt", SELECTED, [])
    assert "missed_opportunity" in prompt
    assert "no_opportunity" in prompt
    assert "extension_skill" in prompt
