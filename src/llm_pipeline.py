"""Three Gemini roles: counseling plan, chat analysis, chatbot. Plan/analysis stay internal.

Chat replies first; analysis is a side-channel. Streamlit builds jobs here and runs
them through `session_flow` (at most one Gemini job per rerun).
"""

from __future__ import annotations

import time
from typing import Any

from .gemini_client import GeminiService, parse_json_response
from .prompts import (
    analysis_for_chatbot,
    build_chat_analysis_prompt,
    build_counseling_plan_prompt,
    build_dialogue_prompt,
    build_experience_analysis_prompt,
    build_practice_evaluator_prompt,
    build_snapshot_prompt,
    build_thought_coach_prompt,
)
from .session_flow import KIND_ANALYZE, KIND_CHAT, KIND_EVAL_SNAPSHOT, KIND_PLAN, KIND_THOUGHT


def create_counseling_plan(
    service: GeminiService,
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    theme: str,
    difficulty: str,
    prior_snapshot: dict[str, Any] | None = None,
    prior_plan: dict[str, Any] | None = None,
    prior_analysis: dict[str, Any] | None = None,
    call_id: str | None = None,
) -> dict[str, Any]:
    raw = service.generate_text(
        build_counseling_plan_prompt(
            mode=mode,
            school_id=school_id,
            selected_ids=selected_ids,
            theme=theme,
            difficulty=difficulty,
            prior_snapshot=prior_snapshot,
            prior_plan=prior_plan,
            prior_analysis=prior_analysis,
        ),
        system_instruction="你是內部諮商計畫引擎，只輸出符合 schema 的 JSON，不要對學生說話。",
        temperature=0.65,
        max_output_tokens=1500,
        response_json=True,
        call_id=call_id,
    )
    plan = parse_json_response(raw)
    plan.setdefault("mode", mode)
    plan.setdefault("school_id", school_id)
    return plan


def analyze_chat(
    service: GeminiService,
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    counseling_plan: dict[str, Any] | None,
    prior_analysis: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    latest_student_message: str,
    difficulty: str = "",
    call_id: str | None = None,
) -> dict[str, Any]:
    try:
        raw = service.generate_text(
            build_chat_analysis_prompt(
                mode=mode,
                school_id=school_id,
                selected_ids=selected_ids,
                counseling_plan=counseling_plan,
                prior_analysis=prior_analysis,
                turns=turns,
                latest_student_message=latest_student_message,
                difficulty=difficulty,
            ),
            system_instruction="你是對話分析引擎，只輸出 JSON。",
            temperature=0.1,
            max_output_tokens=1600,
            response_json=True,
            call_id=call_id,
        )
        return parse_json_response(raw)
    except Exception as exc:
        from .gemini_router import GeminiRouterPending
        if isinstance(exc, GeminiRouterPending):
            raise
        return dict(prior_analysis or {})


def generate_chat_reply(
    service: GeminiService,
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
    latest_student_message: str,
    case_data: dict[str, Any] | None,
    continuation_snapshot: dict[str, Any] | None,
    counseling_plan: dict[str, Any] | None,
    chat_analysis: dict[str, Any] | None,
    is_opening: bool,
    call_id: str | None = None,
) -> tuple[str, int]:
    system, prompt = build_dialogue_prompt(
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        turns=turns,
        latest_student_message=latest_student_message,
        case_data=case_data,
        continuation_snapshot=continuation_snapshot,
        is_opening=is_opening,
        counseling_plan=counseling_plan,
        chat_analysis=analysis_for_chatbot(chat_analysis),
    )
    started = time.perf_counter()
    response = service.generate_text(
        prompt,
        system_instruction=system,
        temperature=0.55,
        max_output_tokens=550,
        call_id=call_id,
    )
    latency = int(getattr(service, "last_latency_ms", 0) or ((time.perf_counter() - started) * 1000))
    return response, latency


def generate_thought_coach_reply(
    service: GeminiService,
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
    student_guide: str,
    example_replies: list[str],
    prior_notes: list[dict[str, Any]],
    latest_thought: str,
    call_id: str | None = None,
) -> str:
    system, prompt = build_thought_coach_prompt(
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        turns=turns,
        student_guide=student_guide,
        example_replies=example_replies,
        prior_notes=prior_notes,
        latest_thought=latest_thought,
    )
    return service.generate_text(
        prompt,
        system_instruction=system,
        temperature=0.35,
        max_output_tokens=450,
        call_id=call_id,
    )


def build_plan_job(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    theme: str,
    difficulty: str,
    prior_snapshot: dict[str, Any] | None = None,
    prior_plan: dict[str, Any] | None = None,
    prior_analysis: dict[str, Any] | None = None,
    request_id: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(meta or {})
    payload.update({
        "mode": mode,
        "school_id": school_id,
        "selected_ids": list(selected_ids),
        "theme": theme,
        "difficulty": difficulty,
    })
    return {
        "id": request_id,
        "kind": KIND_PLAN,
        "request_id": request_id,
        "prompt": build_counseling_plan_prompt(
            mode=mode,
            school_id=school_id,
            selected_ids=selected_ids,
            theme=theme,
            difficulty=difficulty,
            prior_snapshot=prior_snapshot,
            prior_plan=prior_plan,
            prior_analysis=prior_analysis,
        ),
        "system_instruction": "你是內部諮商計畫引擎，只輸出符合 schema 的 JSON，不要對學生說話。",
        "temperature": 0.65,
        "max_output_tokens": 1500,
        "response_json": True,
        "meta": payload,
    }


def build_chat_job(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
    latest_student_message: str,
    case_data: dict[str, Any] | None,
    continuation_snapshot: dict[str, Any] | None,
    counseling_plan: dict[str, Any] | None,
    chat_analysis: dict[str, Any] | None,
    is_opening: bool,
    request_id: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    system, prompt = build_dialogue_prompt(
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        turns=turns,
        latest_student_message=latest_student_message,
        case_data=case_data,
        continuation_snapshot=continuation_snapshot,
        is_opening=is_opening,
        counseling_plan=counseling_plan,
        chat_analysis=analysis_for_chatbot(chat_analysis),
    )
    payload = dict(meta or {})
    payload.update({
        "is_opening": bool(is_opening),
        "latest_student_message": latest_student_message,
    })
    return {
        "id": request_id,
        "kind": KIND_CHAT,
        "request_id": request_id,
        "prompt": prompt,
        "system_instruction": system,
        "temperature": 0.55,
        "max_output_tokens": 550,
        "response_json": False,
        "meta": payload,
    }


def build_analyze_job(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    counseling_plan: dict[str, Any] | None,
    prior_analysis: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    latest_student_message: str,
    difficulty: str = "",
    request_id: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(meta or {})
    payload.setdefault("latest_student_message", latest_student_message)
    return {
        "id": request_id,
        "kind": KIND_ANALYZE,
        "request_id": request_id,
        "prompt": build_chat_analysis_prompt(
            mode=mode,
            school_id=school_id,
            selected_ids=selected_ids,
            counseling_plan=counseling_plan,
            prior_analysis=prior_analysis,
            turns=turns,
            latest_student_message=latest_student_message,
            difficulty=difficulty,
        ),
        "system_instruction": "你是對話分析引擎，只輸出 JSON。",
        "temperature": 0.1,
        "max_output_tokens": 1600,
        "response_json": True,
        "meta": payload,
    }


def build_thought_job(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
    student_guide: str,
    example_replies: list[str],
    prior_notes: list[dict[str, Any]],
    latest_thought: str,
    request_id: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    system, prompt = build_thought_coach_prompt(
        mode=mode,
        school_id=school_id,
        selected_ids=selected_ids,
        turns=turns,
        student_guide=student_guide,
        example_replies=example_replies,
        prior_notes=prior_notes,
        latest_thought=latest_thought,
    )
    payload = dict(meta or {})
    payload["latest_thought"] = latest_thought
    return {
        "id": request_id,
        "kind": KIND_THOUGHT,
        "request_id": request_id,
        "prompt": prompt,
        "system_instruction": system,
        "temperature": 0.35,
        "max_output_tokens": 450,
        "response_json": False,
        "meta": payload,
    }


def build_eval_snapshot_job(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
    continuation_snapshot: dict[str, Any] | None,
    session_id: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    eval_id = f"eval-{session_id}"
    snapshot_id = f"snapshot-{session_id}"
    if mode == "practice":
        eval_prompt = build_practice_evaluator_prompt(school_id, selected_ids, turns)
    else:
        eval_prompt = build_experience_analysis_prompt(school_id, selected_ids, turns)
    return {
        "id": f"eval-snapshot-{session_id}",
        "kind": KIND_EVAL_SNAPSHOT,
        "request_id": eval_id,
        "request_ids": [eval_id, snapshot_id],
        "browser_jobs": [
            {
                "request_id": eval_id,
                "prompt": eval_prompt,
                "system_instruction": "你是形成性教學回饋評量器。只能根據逐字稿證據輸出 JSON。",
                "temperature": 0.1,
                "max_output_tokens": 3200,
                "response_json": True,
            },
            {
                "request_id": snapshot_id,
                "prompt": build_snapshot_prompt(
                    mode, school_id, selected_ids, turns, continuation_snapshot,
                ),
                "system_instruction": "你是續談狀態摘要器，只輸出不含可識別資訊的 JSON。",
                "temperature": 0.1,
                "max_output_tokens": 1600,
                "response_json": True,
            },
        ],
        "meta": dict(meta or {}),
    }
