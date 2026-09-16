from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from src.gemini_router import GeminiRouterPending, generate_via_browser


def _service() -> SimpleNamespace:
    return SimpleNamespace(
        api_key="test-key",
        model_name="gemini-flash-latest",
        fallback_models=(),
        on_model_used=None,
        last_latency_ms=0,
        _models_to_try=lambda: ["gemini-flash-latest"],
    )


def test_gemini_router_html_posts_generate_content_and_retries():
    html = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "frontend"
        / "gemini_router"
        / "index.html"
    ).read_text(encoding="utf-8")
    assert "generateContent" in html
    assert "thinkingConfig" in html
    assert "status === 429" in html
    assert "generativelanguage.googleapis.com" in html
    assert "resultValue = {" in html
    assert "error: errText" in html


def test_generate_via_browser_returns_cached_call_id(monkeypatch):
    import src.gemini_router as router

    state = {}
    dummy_st = SimpleNamespace(session_state=state, spinner=lambda *_a, **_k: nullcontext())
    calls = {"n": 0}

    def fake_component(**kwargs):
        calls["n"] += 1
        job = kwargs["job"]
        return {
            "request_id": job["request_id"],
            "text": "pong",
            "model": "gemini-flash-latest",
            "latency_ms": 12,
            "error": "",
        }

    monkeypatch.setattr(router, "_st", lambda: dummy_st)
    monkeypatch.setattr(router, "_gemini_router", fake_component)
    service = _service()
    first = generate_via_browser(service, "hi", call_id="validate")
    second = generate_via_browser(service, "hi again", call_id="validate")
    assert first == second == "pong"
    assert calls["n"] == 1
    assert service.last_latency_ms == 12


def test_generate_via_browser_raises_pending_until_result(monkeypatch):
    import src.gemini_router as router

    dummy_st = SimpleNamespace(session_state={}, spinner=lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(router, "_st", lambda: dummy_st)
    monkeypatch.setattr(router, "_gemini_router", lambda **_kwargs: None)
    try:
        generate_via_browser(_service(), "hi", call_id="analyze-S1-1")
    except GeminiRouterPending:
        return
    raise AssertionError("expected GeminiRouterPending")
