from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.run_guardrails import RunGuardrailService, StopDecision
from app.services.usage_budget import BudgetSnapshot


def _install_runtime_values(monkeypatch, overrides: dict):
    defaults = {
        "STOP_CONDITION_ENFORCEMENT_ENABLED": True,
        "SIMULATION_PAUSED": False,
        "SIMULATION_ACTIVE": True,
        "LLM_DAILY_BUDGET_USD_HARD": 1.0,
        "STOP_PROVIDER_FAILURE_THRESHOLD": 999999,
        "STOP_PROVIDER_FAILURE_WINDOW_MINUTES": 15,
        "STOP_DB_POOL_UTILIZATION_THRESHOLD": 0.95,
        "STOP_DB_POOL_CONSECUTIVE_CHECKS": 3,
        "SIMULATION_RUN_ID": "real-20260416T112049Z",
        "SIMULATION_AUTO_STOP_AT": "",
        "SIMULATION_AUTO_STOP_RUN_ID": "",
    }
    defaults.update(overrides)
    monkeypatch.setattr(
        "app.services.run_guardrails.runtime_config_service.get_effective_value_cached",
        lambda key: defaults.get(key),
    )


def test_enforcement_disabled_skips_checks(monkeypatch):
    _install_runtime_values(monkeypatch, {"STOP_CONDITION_ENFORCEMENT_ENABLED": False})
    service = RunGuardrailService()
    decision = service.evaluate()
    assert decision.should_stop is False
    assert decision.reason is None


def test_hard_budget_stop_triggers(monkeypatch):
    _install_runtime_values(monkeypatch, {"LLM_DAILY_BUDGET_USD_HARD": 1.0})
    monkeypatch.setattr(
        "app.services.run_guardrails.usage_budget.get_snapshot",
        lambda: BudgetSnapshot(
            day_key=date.today(),
            calls_total=42,
            calls_openrouter_free=20,
            estimated_cost_usd=1.1,
        ),
    )
    monkeypatch.setattr(
        RunGuardrailService,
        "_check_provider_failures",
        staticmethod(lambda: StopDecision(False)),
    )
    service = RunGuardrailService()
    monkeypatch.setattr(
        service,
        "_check_db_pool_pressure",
        lambda: StopDecision(False),
    )

    decision = service.evaluate()
    assert decision.should_stop is True
    assert decision.reason == "hard_budget_exceeded"
    assert decision.details["hard_budget_usd"] == 1.0


def test_db_pool_pressure_requires_consecutive_breaches(monkeypatch):
    _install_runtime_values(
        monkeypatch,
        {
            "STOP_DB_POOL_UTILIZATION_THRESHOLD": 0.8,
            "STOP_DB_POOL_CONSECUTIVE_CHECKS": 2,
        },
    )

    class FakePool:
        _max_overflow = 0

        @staticmethod
        def checkedout():
            return 9

        @staticmethod
        def size():
            return 10

    class FakeEngine:
        pool = FakePool()

    monkeypatch.setattr("app.services.run_guardrails.engine", FakeEngine())

    service = RunGuardrailService()
    first = service._check_db_pool_pressure()
    second = service._check_db_pool_pressure()

    assert first.should_stop is False
    assert second.should_stop is True
    assert second.reason == "db_pool_pressure"
    assert second.details["consecutive_checks_observed"] == 2


def test_scheduled_stop_triggers_for_matching_run(monkeypatch):
    _install_runtime_values(
        monkeypatch,
        {
            "SIMULATION_RUN_ID": "real-20260416T112049Z",
            "SIMULATION_AUTO_STOP_RUN_ID": "real-20260416T112049Z",
            "SIMULATION_AUTO_STOP_AT": "2026-04-16T21:21:52+00:00",
        },
    )
    monkeypatch.setattr("app.services.run_guardrails.now_utc", lambda: datetime(2026, 4, 16, 21, 25, tzinfo=timezone.utc))
    monkeypatch.setattr(
        RunGuardrailService,
        "_check_budget_hard_stop",
        staticmethod(lambda: StopDecision(False)),
    )
    monkeypatch.setattr(
        RunGuardrailService,
        "_check_provider_failures",
        staticmethod(lambda: StopDecision(False)),
    )
    service = RunGuardrailService()
    monkeypatch.setattr(service, "_check_db_pool_pressure", lambda: StopDecision(False))

    decision = service.evaluate()

    assert decision.should_stop is True
    assert decision.reason == "scheduled_stop_reached"
    assert decision.details["scheduled_run_id"] == "real-20260416T112049Z"


def test_scheduled_stop_clears_when_run_id_no_longer_matches(monkeypatch):
    _install_runtime_values(
        monkeypatch,
        {
            "SIMULATION_RUN_ID": "real-20260416T999999Z",
            "SIMULATION_AUTO_STOP_RUN_ID": "real-20260416T112049Z",
            "SIMULATION_AUTO_STOP_AT": "2026-04-16T21:21:52+00:00",
        },
    )
    monkeypatch.setattr("app.services.run_guardrails.now_utc", lambda: datetime(2026, 4, 16, 21, 25, tzinfo=timezone.utc))
    cleared: list[dict] = []
    monkeypatch.setattr(
        RunGuardrailService,
        "_clear_scheduled_stop",
        staticmethod(lambda *, reason, details=None: cleared.append({"reason": reason, "details": details or {}})),
    )
    monkeypatch.setattr(
        RunGuardrailService,
        "_check_budget_hard_stop",
        staticmethod(lambda: StopDecision(False)),
    )
    monkeypatch.setattr(
        RunGuardrailService,
        "_check_provider_failures",
        staticmethod(lambda: StopDecision(False)),
    )
    service = RunGuardrailService()
    monkeypatch.setattr(service, "_check_db_pool_pressure", lambda: StopDecision(False))

    decision = service.evaluate()

    assert decision.should_stop is False
    assert len(cleared) == 1
    assert cleared[0]["reason"] == "scheduled_stop_stale_run_mismatch"
