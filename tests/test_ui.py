from src.ui import coaching_panel_copy, escape_html, mode_label, ROLE_LABELS


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
    assert "[data-testid=\"InputInstructions\"]" in APP_CSS
    assert "span:not(:last-child)" in APP_CSS
    assert "padding-top: 3.15rem" in APP_CSS
    assert ":has(.ct-hud)" in APP_CSS
    assert ":has(.ct-online)" in APP_CSS
    assert ".ct-quota-fill" in APP_CSS
    assert 'iframe[title$="quota_sync"]' in APP_CSS
    assert "backdrop-filter: none" in APP_CSS
    assert "z-index: 1000000" in APP_CSS
    assert "stHorizontalBlock" in APP_CSS
    assert ":has(.ct-thoughts)" in APP_CSS
    assert "align-items: flex-end" in APP_CSS
    assert "bottom: 5.25rem" in APP_CSS


def test_quota_bar_overlays_three_remaining_metrics():
    from src.ui import _quota_bar_html

    html = _quota_bar_html({
        "rpm_ratio": 0.4,
        "rpd_ratio": 0.8,
        "tpm_ratio": 0.2,
        "rpm_remaining": 6,
        "rpd_remaining": 50,
        "tpm_remaining": 200000,
        "rpm_limit": 10,
        "rpd_limit": 250,
        "tpm_limit": 250000,
        "limited": False,
    })
    assert "ct-quota-fill ct-quota-rpd" in html
    assert "ct-quota-fill ct-quota-tpm" in html
    assert "ct-quota-fill ct-quota-rpm" in html
    assert "width:80.0%" in html
    assert "width:40.0%" in html
    assert "width:20.0%" in html
    assert "RPM 剩 6" in html
    assert "RPD 剩 50" in html
    assert "TPM 剩 200K" in html
    assert "ct-quota-capped" not in html


def test_ime_enter_guard_blocks_composition_enter() -> None:
    from pathlib import Path

    from src.ui import APP_CSS, _IME_GUARD_DIR, install_ime_enter_guard

    html = (_IME_GUARD_DIR / "index.html").read_text(encoding="utf-8")
    assert "compositionend" in html
    assert "isComposing" in html
    assert "229" in html
    assert "justEnded" in html
    assert "st.chat_input" not in html
    assert 'iframe[title$="ime_enter_guard"]' in APP_CSS
    assert 'iframe[title$="gemini_router"]' in APP_CSS
    assert 'iframe[title$="quota_sync"]' in APP_CSS
    assert callable(install_ime_enter_guard)


def test_experience_coaching_panel_is_observer_notes() -> None:
    copy = coaching_panel_copy("experience")
    assert copy["title"] == "此刻示範說明"
    assert copy["guide_label"] == "諮商師此刻在做什麼"
    assert copy["examples_label"] == ""
    assert "預告" in copy["guide_empty"]
    practice = coaching_panel_copy("practice")
    assert practice["examples_label"] == "符合此刻的例句"
    assert practice["title"] == "初階練習提示"
