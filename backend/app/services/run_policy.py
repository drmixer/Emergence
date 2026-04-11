"""Run-class-aware routing and deterministic failure policy helpers."""

from __future__ import annotations

import random
from typing import Any

from app.core.time import now_utc
from app.services.runtime_config import runtime_config_service

RUN_CLASS_STANDARD = "standard_72h"
RUN_CLASS_DEEP = "deep_96h"
RUN_CLASS_SPECIAL_EXPLORATORY = "special_exploratory"
RUN_CLASSES = {
    RUN_CLASS_STANDARD,
    RUN_CLASS_DEEP,
    RUN_CLASS_SPECIAL_EXPLORATORY,
}

FAILURE_POLICY_IDLE_ON_LLM_FAILURE = "idle_on_llm_failure"
FAILURE_POLICY_ROUTINE_ON_LLM_FAILURE = "routine_on_llm_failure"

RUNTIME_MODE_DETERMINISTIC_FORCED_IDLE = "deterministic_forced_idle"
RUNTIME_MODE_DETERMINISTIC_ROUTINE_FALLBACK = "deterministic_routine_fallback"


def coerce_run_class(run_class: str | None) -> str:
    clean = str(run_class or "").strip().lower()
    if clean in RUN_CLASSES:
        return clean
    return RUN_CLASS_STANDARD


def deterministic_failure_policy_for_run_class(run_class: str | None) -> str:
    resolved = coerce_run_class(run_class)
    if resolved == RUN_CLASS_SPECIAL_EXPLORATORY:
        return FAILURE_POLICY_ROUTINE_ON_LLM_FAILURE
    return FAILURE_POLICY_IDLE_ON_LLM_FAILURE


def runtime_mode_for_failure_policy(run_class: str | None) -> str:
    policy = deterministic_failure_policy_for_run_class(run_class)
    if policy == FAILURE_POLICY_ROUTINE_ON_LLM_FAILURE:
        return RUNTIME_MODE_DETERMINISTIC_ROUTINE_FALLBACK
    return RUNTIME_MODE_DETERMINISTIC_FORCED_IDLE


def current_run_class() -> str:
    value = runtime_config_service.get_effective_value_cached("SIMULATION_RUN_CLASS")
    return coerce_run_class(value)


def current_failure_policy() -> str:
    return deterministic_failure_policy_for_run_class(current_run_class())


def build_terminal_llm_failure_action(
    *,
    agent_id: int,
    reason: str,
    run_class: str | None,
    failure_stage: str,
) -> dict[str, Any]:
    resolved_run_class = coerce_run_class(run_class)
    policy = deterministic_failure_policy_for_run_class(resolved_run_class)
    runtime_mode = runtime_mode_for_failure_policy(resolved_run_class)
    clean_reason = str(reason or "").strip() or "terminal_llm_failure"

    deterministic_meta = {
        "run_class": resolved_run_class,
        "failure_policy": policy,
        "runtime_mode": runtime_mode,
        "continuity_protection": policy == FAILURE_POLICY_ROUTINE_ON_LLM_FAILURE,
        "failure_stage": failure_stage,
        "failure_reason": clean_reason,
    }

    if policy == FAILURE_POLICY_IDLE_ON_LLM_FAILURE:
        return {
            "action": "idle",
            "reasoning": f"Forced idle after terminal LLM failure: {clean_reason}",
            "_deterministic_meta": deterministic_meta,
        }

    seed = agent_id + int(now_utc().timestamp() // 3600)
    rng = random.Random(seed)
    roll = rng.random()
    reasoning = f"Continuity protection after terminal LLM failure: {clean_reason}"

    if roll < 0.75:
        return {
            "action": "work",
            "work_type": rng.choice(["farm", "generate", "gather"]),
            "hours": rng.randint(1, 4),
            "reasoning": reasoning,
            "_deterministic_meta": deterministic_meta,
        }
    if roll < 0.9:
        return {
            "action": "idle",
            "reasoning": reasoning,
            "_deterministic_meta": deterministic_meta,
        }

    return {
        "action": "forum_post",
        "content": (
            "I'm having trouble communicating clearly right now, so I'll focus on work and "
            "staying alive. If anyone has a concrete plan, summarize it and tag me."
        ),
        "reasoning": reasoning,
        "_deterministic_meta": deterministic_meta,
    }
