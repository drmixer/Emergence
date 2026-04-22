from __future__ import annotations

import asyncio

import worker
from app.services.run_guardrails import StopDecision


def test_worker_idles_after_scheduled_stop_instead_of_exiting(monkeypatch):
    runtime_values = {
        "SIMULATION_ACTIVE": True,
        "SIMULATION_PAUSED": False,
    }
    start_calls: list[str] = []
    stop_calls: list[tuple[object, object]] = []
    guardrail_calls = {"count": 0}

    def fake_runtime_value(key: str):
        return runtime_values.get(key)

    async def fake_start_health_server():
        return None

    async def fake_start_runtime_systems():
        start_calls.append("started")
        return "event-task", "summary-task"

    async def fake_stop_runtime_systems(event_task, summary_task):
        stop_calls.append((event_task, summary_task))

    def fake_evaluate_and_enforce():
        guardrail_calls["count"] += 1
        if guardrail_calls["count"] == 1:
            runtime_values["SIMULATION_ACTIVE"] = False
            runtime_values["SIMULATION_PAUSED"] = True
            return StopDecision(True, "scheduled_stop_reached", {"scheduled_run_id": "run-1"})
        return StopDecision(False)

    async def fake_sleep(_seconds: float):
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        worker.runtime_config_service,
        "get_effective_value_cached",
        fake_runtime_value,
    )
    monkeypatch.setattr(worker.run_guardrail_service, "evaluate_and_enforce", fake_evaluate_and_enforce)
    monkeypatch.setattr(worker, "_start_health_server", fake_start_health_server)
    monkeypatch.setattr(worker, "_start_runtime_systems", fake_start_runtime_systems)
    monkeypatch.setattr(worker, "_stop_runtime_systems", fake_stop_runtime_systems)
    monkeypatch.setattr(worker.asyncio, "sleep", fake_sleep)

    asyncio.run(worker.main())

    assert start_calls == ["started"]
    assert stop_calls == [("event-task", "summary-task")]
    assert guardrail_calls["count"] == 1
