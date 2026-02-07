from __future__ import annotations

from datetime import date

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
            calls_groq=22,
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
