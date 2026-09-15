from src.ui import escape_html, mode_label, ROLE_LABELS


def test_escape_html_prevents_markup_injection() -> None:
    assert escape_html("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert escape_html('quote "test"') == "quote &quot;test&quot;"


def test_mode_labels_stay_traditional_chinese() -> None:
    assert mode_label("experience") == "學派體驗"
    assert mode_label("practice") == "學生實作"


def test_role_labels_cover_session_speakers() -> None:
    assert set(ROLE_LABELS) >= {
        "student_client",
        "student_counselor",
        "ai_client",
        "ai_counselor",
        "system",
    }


def test_thought_log_styles_exist() -> None:
    from src.ui import APP_CSS

    assert ".ct-thought-log" in APP_CSS
    assert ".ct-thought-item.student" in APP_CSS
