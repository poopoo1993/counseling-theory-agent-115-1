from pathlib import Path
from types import SimpleNamespace

from src.gemini_router import GeminiRouterPending, generate_via_browser, run_browser_jobs


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
    assert "Promise.all" in html
    assert "queuedJobs" in html
    assert "generativelanguage.googleapis.com" in html
    assert "resultValue = {" in html
    assert "error: errText" in html


def test_generate_via_browser_returns_cached_call_id(monkeypatch):
    import src.gemini_router as router

    state = {"_gemini_router_mounted": False}
    dummy_st = SimpleNamespace(session_state=state)
    calls = {"n": 0}

    def fake_component(**kwargs):
        calls["n"] += 1
        assert kwargs["key"] == "ct_gemini_router"
        jobs = kwargs["jobs"]
        return {
            "results": [{
                "request_id": jobs[0]["request_id"],
                "text": "pong",
                "model": "gemini-flash-latest",
                "latency_ms": 12,
                "error": "",
            }]
        }

    monkeypatch.setattr(router, "_st", lambda: dummy_st)
    monkeypatch.setattr(router, "_gemini_router", fake_component)
    service = _service()
    first = generate_via_browser(service, "hi", call_id="validate")
    second = generate_via_browser(service, "hi again", call_id="validate")
    assert first == second == "pong"
    assert calls["n"] == 1
    assert service.last_latency_ms == 12


def test_run_browser_jobs_batches_and_ignores_stale_results(monkeypatch):
    import src.gemini_router as router

    state = {"_gemini_router_mounted": False}
    dummy_st = SimpleNamespace(session_state=state)

    def stale_component(**kwargs):
        return {
            "results": [{
                "request_id": "old",
                "text": "stale",
                "model": "gemini-flash-latest",
                "latency_ms": 1,
                "error": "",
            }]
        }

    monkeypatch.setattr(router, "_st", lambda: dummy_st)
    monkeypatch.setattr(router, "_gemini_router", stale_component)
    try:
        run_browser_jobs(_service(), [
            {"request_id": "analyze-S1-1", "prompt": "a"},
            {"request_id": "chat-S1-1", "prompt": "b"},
        ])
    except GeminiRouterPending:
        pass
    else:
        raise AssertionError("expected GeminiRouterPending for stale results")

    def fresh_component(**kwargs):
        jobs = kwargs["jobs"]
        return {
            "results": [
                {
                    "request_id": job["request_id"],
                    "text": job["request_id"] + "-ok",
                    "model": "gemini-flash-latest",
                    "latency_ms": 4,
                    "error": "",
                }
                for job in jobs
            ]
        }

    state["_gemini_router_mounted"] = False
    monkeypatch.setattr(router, "_gemini_router", fresh_component)
    texts = run_browser_jobs(_service(), [
        {"request_id": "analyze-S1-1", "prompt": "a"},
        {"request_id": "chat-S1-1", "prompt": "b"},
    ])
    assert texts["analyze-S1-1"] == "analyze-S1-1-ok"
    assert texts["chat-S1-1"] == "chat-S1-1-ok"


def test_generate_via_browser_raises_pending_until_result(monkeypatch):
    import src.gemini_router as router

    dummy_st = SimpleNamespace(session_state={"_gemini_router_mounted": False})
    monkeypatch.setattr(router, "_st", lambda: dummy_st)
    monkeypatch.setattr(router, "_gemini_router", lambda **_kwargs: None)
    try:
        generate_via_browser(_service(), "hi", call_id="analyze-S1-1")
    except GeminiRouterPending:
        return
    raise AssertionError("expected GeminiRouterPending")
