from src.llm_pipeline import (
    build_analyze_job,
    build_chat_job,
    build_eval_snapshot_job,
)
from src.session_flow import (
    KIND_ANALYZE,
    KIND_CHAT,
    KIND_EVAL_SNAPSHOT,
    KIND_THOUGHT,
    browser_jobs,
    complete_job,
    enqueue,
    peek_next,
    should_analyze_mid_session,
    thread_status_for_end,
    tick,
)


def _job(kind: str, job_id: str, **meta) -> dict:
    return {"id": job_id, "kind": kind, "request_id": job_id, "meta": meta, "prompt": kind}


def test_chat_jumps_ahead_of_analyze_without_dropping_it() -> None:
    state: dict = {}
    enqueue(state, _job(KIND_ANALYZE, "analyze-S1-1"))
    enqueue(state, _job(KIND_THOUGHT, "thought-S1-1"))
    enqueue(state, _job(KIND_CHAT, "chat-S1-2"))
    assert [job["id"] for job in state["gemini_job_queue"]] == [
        "chat-S1-2",
        "analyze-S1-1",
        "thought-S1-1",
    ]
    enqueue(state, _job(KIND_CHAT, "chat-S1-2"))
    assert [job["id"] for job in state["gemini_job_queue"]] == [
        "chat-S1-2",
        "analyze-S1-1",
        "thought-S1-1",
    ]


def test_tick_runs_at_most_one_job_and_leaves_it_until_complete() -> None:
    state: dict = {}
    enqueue(state, _job(KIND_CHAT, "chat-S1-1"))
    enqueue(state, _job(KIND_ANALYZE, "analyze-S1-1"))
    seen: list[list[str]] = []

    def run_jobs(jobs):
        seen.append([str(job.get("request_id")) for job in jobs])
        return {job["request_id"]: "ok" for job in jobs}

    result = tick(state, materialize=browser_jobs, run_jobs=run_jobs)
    assert result is not None
    assert result["job"]["id"] == "chat-S1-1"
    assert seen == [["chat-S1-1"]]
    assert peek_next(state)["id"] == "chat-S1-1"
    complete_job(state, "chat-S1-1")
    assert peek_next(state)["id"] == "analyze-S1-1"


def test_eval_snapshot_is_one_queue_job_with_two_browser_payloads() -> None:
    job = build_eval_snapshot_job(
        mode="practice",
        school_id="cbt",
        selected_ids=["automatic_thoughts", "evidence_review", "cognitive_restructuring"],
        turns=[],
        continuation_snapshot={},
        session_id="S1",
    )
    payloads = browser_jobs(job)
    assert job["kind"] == KIND_EVAL_SNAPSHOT
    assert [item["request_id"] for item in payloads] == ["eval-S1", "snapshot-S1"]
    state: dict = {}
    enqueue(state, job)
    enqueue(state, _job(KIND_ANALYZE, "analyze-S1-9"))
    seen: list[int] = []

    def run_jobs(jobs):
        seen.append(len(list(jobs)))
        return {job["request_id"]: "{}" for job in jobs}

    result = tick(state, materialize=browser_jobs, run_jobs=run_jobs)
    assert result is not None
    assert result["job"]["kind"] == KIND_EVAL_SNAPSHOT
    assert seen == [2]
    assert peek_next(state)["kind"] == KIND_EVAL_SNAPSHOT


def test_eval_failure_leaves_job_queued_for_retry() -> None:
    state: dict = {}
    enqueue(state, build_eval_snapshot_job(
        mode="experience",
        school_id="cbt",
        selected_ids=["automatic_thoughts", "evidence_review", "cognitive_restructuring"],
        turns=[],
        continuation_snapshot={},
        session_id="S9",
    ))

    def boom(_jobs):
        raise RuntimeError("iframe dropped")

    try:
        tick(state, materialize=browser_jobs, run_jobs=boom)
    except RuntimeError as exc:
        assert "iframe dropped" in str(exc)
    else:
        raise AssertionError("expected run_jobs error to propagate")
    assert peek_next(state)["id"] == "eval-snapshot-S9"


def test_should_analyze_skips_advanced_and_brand_new_opening() -> None:
    assert should_analyze_mid_session(difficulty="初階", is_opening=False) is True
    assert should_analyze_mid_session(difficulty="中階", is_opening=False) is True
    assert should_analyze_mid_session(difficulty="進階", is_opening=False) is False
    assert should_analyze_mid_session(difficulty="初階", is_opening=True, has_prior_turns=False) is False
    assert should_analyze_mid_session(difficulty="初階", is_opening=True, has_prior_turns=True) is True


def test_thread_status_for_end_closes_safety_and_declined_process() -> None:
    assert thread_status_for_end(keep_process=True) == "active"
    assert thread_status_for_end(keep_process=False) == "closed"
    assert thread_status_for_end(keep_process=True, safety_stopped=True) == "closed"


def test_chat_and_analyze_job_builders_keep_reply_first_temperatures() -> None:
    chat = build_chat_job(
        mode="practice",
        school_id="cbt",
        selected_ids=["automatic_thoughts", "evidence_review", "cognitive_restructuring"],
        turns=[],
        latest_student_message="你聽起來很累。",
        case_data=None,
        continuation_snapshot=None,
        counseling_plan={"mode": "practice"},
        chat_analysis=None,
        is_opening=False,
        request_id="chat-S1-2",
    )
    analyze = build_analyze_job(
        mode="practice",
        school_id="cbt",
        selected_ids=["automatic_thoughts", "evidence_review", "cognitive_restructuring"],
        counseling_plan={"mode": "practice"},
        prior_analysis=None,
        turns=[],
        latest_student_message="你聽起來很累。",
        difficulty="初階",
        request_id="analyze-S1-2",
        meta={"session_turn_count": 2},
    )
    assert chat["kind"] == KIND_CHAT
    assert chat["temperature"] == 0.55
    assert analyze["kind"] == KIND_ANALYZE
    assert analyze["temperature"] == 0.1
    assert analyze["response_json"] is True
    assert analyze["meta"]["session_turn_count"] == 2
