from src.safety import detect_immediate_risk, detect_pii, redact_for_preview


def test_immediate_risk_is_specific():
    assert detect_immediate_risk("我今晚想要自殺")
    assert not detect_immediate_risk("這是課堂討論自殺防治的虛構案例")


def test_pii_detection_and_redaction():
    text = "請打 0912345678 或寄到 someone@example.com"
    assert set(detect_pii(text)) == {"phone", "email"}
    redacted = redact_for_preview(text)
    assert "0912345678" not in redacted
    assert "someone@example.com" not in redacted
