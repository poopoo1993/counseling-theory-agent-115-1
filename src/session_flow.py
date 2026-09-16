"""Session phases and a per-browser Gemini job queue.

Streamlit reruns can mount `ct_gemini_router` only once. The queue guarantees
at most one Gemini job (or one independent eval+snapshot batch) per tick.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any

from .prompts import turn_review_visible

QUEUE_KEY = "gemini_job_queue"
PHASE_KEY = "session_phase"

GATE = "gate"
SETUP = "setup"
OPENING = "opening"
LIVE = "live"
COACHING = "coaching"
ENDING = "ending"
FEEDBACK = "feedback"

KIND_PLAN = "plan"
KIND_CHAT = "chat"
KIND_ANALYZE = "analyze"
KIND_THOUGHT = "thought"
KIND_EVAL_SNAPSHOT = "eval_snapshot"

KIND_PRIORITY = {
    KIND_PLAN: 0,
    KIND_CHAT: 0,
    KIND_EVAL_SNAPSHOT: 0,
    KIND_ANALYZE: 1,
    KIND_THOUGHT: 2,
}


def phase(state: Mapping[str, Any]) -> str:
    value = str(state.get(PHASE_KEY) or "").strip()
    return value or GATE


def set_phase(state: MutableMapping[str, Any], value: str) -> None:
    state[PHASE_KEY] = str(value)


def get_queue(state: MutableMapping[str, Any]) -> list[dict[str, Any]]:
    queue = state.get(QUEUE_KEY)
    if not isinstance(queue, list):
        queue = []
        state[QUEUE_KEY] = queue
    return queue


def clear_jobs(state: MutableMapping[str, Any]) -> None:
    state[QUEUE_KEY] = []


def peek_next(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    queue = get_queue(state)
    if not queue:
        return None
    job = queue[0]
    return dict(job) if isinstance(job, dict) else None


def has_kind(state: MutableMapping[str, Any], kind: str) -> bool:
    wanted = str(kind)
    return any(str(job.get("kind") or "") == wanted for job in get_queue(state) if isinstance(job, dict))


def has_jobs(state: MutableMapping[str, Any]) -> bool:
    return bool(get_queue(state))


def _job_id(job: Mapping[str, Any]) -> str:
    return str(job.get("id") or job.get("request_id") or "").strip()


def enqueue(state: MutableMapping[str, Any], job: Mapping[str, Any]) -> dict[str, Any]:
    """Insert a job. Reply/plan/eval stay ahead of analyze and thought; duplicates are ignored."""
    payload = dict(job)
    job_id = _job_id(payload)
    if not job_id:
        raise ValueError("Gemini job needs an id")
    payload["id"] = job_id
    kind = str(payload.get("kind") or "").strip()
    payload["kind"] = kind
    payload["priority"] = int(payload.get("priority", KIND_PRIORITY.get(kind, 9)))
    queue = get_queue(state)
    if any(_job_id(existing) == job_id for existing in queue if isinstance(existing, dict)):
        return payload
    insert_at = len(queue)
    for index, existing in enumerate(queue):
        if not isinstance(existing, dict):
            continue
        if int(existing.get("priority", 9)) > payload["priority"]:
            insert_at = index
            break
    queue.insert(insert_at, payload)
    state[QUEUE_KEY] = queue
    return payload


def complete_job(state: MutableMapping[str, Any], job_id: str) -> dict[str, Any] | None:
    wanted = str(job_id or "").strip()
    queue = get_queue(state)
    for index, existing in enumerate(queue):
        if isinstance(existing, dict) and _job_id(existing) == wanted:
            finished = queue.pop(index)
            state[QUEUE_KEY] = queue
            return finished
    return None


def should_analyze_mid_session(
    *,
    difficulty: str,
    is_opening: bool = False,
    has_prior_turns: bool = False,
) -> bool:
    """初／中階 side-channel coaching. Skip 進階 mid-session and brand-new openings."""
    if not turn_review_visible(difficulty):
        return False
    if is_opening and not has_prior_turns:
        return False
    return True


def thread_status_for_end(*, keep_process: bool, safety_stopped: bool = False) -> str:
    """Continuation lists `active` only. Closed threads are not stuck in_progress."""
    if safety_stopped or not keep_process:
        return "closed"
    return "active"


def browser_jobs(job: Mapping[str, Any]) -> list[dict[str, Any]]:
    nested = job.get("browser_jobs")
    if isinstance(nested, list) and nested:
        return [dict(item) for item in nested if isinstance(item, Mapping)]
    request_id = str(job.get("request_id") or job.get("id") or "").strip()
    if not request_id:
        return []
    return [{
        "request_id": request_id,
        "prompt": str(job.get("prompt") or ""),
        "system_instruction": str(job.get("system_instruction") or ""),
        "temperature": float(job.get("temperature", 0.4)),
        "max_output_tokens": int(job.get("max_output_tokens", 1200)),
        "response_json": bool(job.get("response_json", False)),
    }]


def tick(
    state: MutableMapping[str, Any],
    *,
    materialize: Callable[[dict[str, Any]], Sequence[Mapping[str, Any]]],
    run_jobs: Callable[[Sequence[Mapping[str, Any]]], dict[str, str]],
) -> dict[str, Any] | None:
    """Run the head-of-queue job. Caller applies side effects, then `complete_job`."""
    job = peek_next(state)
    if not job:
        return None
    payloads = [dict(item) for item in materialize(job) if isinstance(item, Mapping)]
    if not payloads:
        complete_job(state, str(job.get("id") or ""))
        return None
    texts = run_jobs(payloads)
    return {"job": job, "texts": texts}
