from src.transcript import extract_nonverbal_cues, make_transcript_txt


def test_extract_nonverbal_cues_supports_full_and_half_width_parentheses():
    assert extract_nonverbal_cues("我不知道。（視線移開） (雙手握緊)") == ["視線移開", "雙手握緊"]


def test_transcript_preserves_raw_nonverbal_text():
    session = {
        "session_id": "S1", "started_at": "2026-09-13T10:00:00+08:00",
        "mode": "practice", "school_name": "完形治療",
        "selected_technique_names": ["此時此刻覺察", "身體感受覺察", "空椅技術"],
    }
    turns = [{"turn_index": 1, "speaker_role": "ai_client", "content_raw": "（低下頭）我有點難過。"}]
    text = make_transcript_txt(session, turns).decode("utf-8-sig")
    assert "（低下頭）我有點難過。" in text
    assert "AI 模擬個案" in text
