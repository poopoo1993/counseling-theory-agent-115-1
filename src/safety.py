"""教學情境的基本安全分流，不取代真人風險評估。"""

from __future__ import annotations

import re


CRISIS_PATTERNS = [
    r"我(?:現在|今天|今晚)?想(?:要)?自殺",
    r"我(?:現在|今天|今晚)?想(?:要)?死",
    r"已經準備好.*(?:自殺|結束生命)",
    r"我要殺(?:他|她|人)",
    r"現在就要傷害(?:自己|別人|他|她)",
]

PII_PATTERNS = {
    "phone": re.compile(r"(?<!\d)(?:09\d{8}|0\d{1,2}-?\d{6,8})(?!\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "taiwan_id": re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?!\d)"),
}


def detect_immediate_risk(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return any(re.search(pattern, compact) for pattern in CRISIS_PATTERNS)


def detect_pii(text: str) -> list[str]:
    return [name for name, pattern in PII_PATTERNS.items() if pattern.search(text or "")]


def safety_message() -> str:
    return (
        "你剛才的內容可能涉及立即的人身安全。這個系統只供教學模擬，不能提供危機處遇。"
        "請先停止模擬，立即聯絡所在地緊急服務、可信任的人或專業人員；若你在臺灣，"
        "可撥 119／110，或衛生福利部安心專線 1925。請不要獨自承擔。"
    )


def redact_for_preview(text: str) -> str:
    value = text or ""
    for kind, pattern in PII_PATTERNS.items():
        value = pattern.sub(f"[{kind}_已隱去]", value)
    return value
