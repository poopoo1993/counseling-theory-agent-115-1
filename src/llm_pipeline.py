"""Three Gemini roles: counseling plan, chat analysis, chatbot. Plan/analysis stay internal."""

from __future__ import annotations

import time
from typing import Any

from .gemini_client import GeminiService, parse_json_response
from .prompts import (
    analysis_for_chatbot,
    build_chat_analysis_prompt,
    build_counseling_plan_prompt,
    build_dialogue_prompt,
    build_thought_coach_prompt,
)


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
        )
        return parse_json_response(raw)
    except Exception:
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
    )
    latency = int((time.perf_counter() - started) * 1000)
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
    )
