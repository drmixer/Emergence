from __future__ import annotations

from datetime import datetime, timezone
import importlib


simulation_control = importlib.import_module("scripts.simulation_control")


def test_resolve_start_runtime_updates_generates_fresh_run_defaults(monkeypatch):
    monkeypatch.setattr(
        simulation_control,
        "now_utc",
        lambda: datetime(2026, 4, 20, 12, 48, 49, tzinfo=timezone.utc),
    )

    updates, run_id, run_mode = simulation_control._resolve_start_runtime_updates(
        requested_run_mode=None,
        requested_run_id=None,
        requested_run_class=None,
        requested_condition=None,
        requested_season_number=None,
        current_run_mode="real",
    )

    assert run_mode == "real"
    assert run_id == "real-20260420T124849Z"
    assert updates == {
        "SIMULATION_ACTIVE": True,
        "SIMULATION_PAUSED": False,
        "SIMULATION_RUN_MODE": "real",
        "SIMULATION_RUN_ID": "real-20260420T124849Z",
        "SIMULATION_RUN_CLASS": "standard_72h",
        "SIMULATION_CONDITION_NAME": "",
        "SIMULATION_SEASON_NUMBER": 0,
    }


def test_resolve_start_runtime_updates_preserves_explicit_values():
    updates, run_id, run_mode = simulation_control._resolve_start_runtime_updates(
        requested_run_mode="real",
        requested_run_id="real-explicit-run",
        requested_run_class="special_exploratory",
        requested_condition="scarcity_canary_v2",
        requested_season_number=3,
        current_run_mode="test",
    )

    assert run_mode == "real"
    assert run_id == "real-explicit-run"
    assert updates["SIMULATION_RUN_CLASS"] == "special_exploratory"
    assert updates["SIMULATION_CONDITION_NAME"] == "scarcity_canary_v2"
    assert updates["SIMULATION_SEASON_NUMBER"] == 3
