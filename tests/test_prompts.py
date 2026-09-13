from src.prompts import build_dialogue_prompt, build_practice_evaluator_prompt


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


def test_evaluator_distinguishes_missed_and_no_opportunity():
    prompt = build_practice_evaluator_prompt("cbt", SELECTED, [])
    assert "missed_opportunity" in prompt
    assert "no_opportunity" in prompt
    assert "extension_skill" in prompt
