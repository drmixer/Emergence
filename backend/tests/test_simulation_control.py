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


def test_retire_inherited_governance_state_commits(monkeypatch):
    class FakeCleanup:
        proposals_expired = 2
        laws_deactivated = 3

    class FakeSession:
        committed = False
        rolled_back = False
        closed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FakeSession()
    calls = []

    monkeypatch.setattr(simulation_control, "SessionLocal", lambda: session)

    def fake_retire(db, *, run_id):
        calls.append((db, run_id))
        return FakeCleanup()

    monkeypatch.setattr(simulation_control, "retire_inherited_governance_state", fake_retire)

    result = simulation_control._retire_inherited_governance_state_for_start("real-test")

    assert result == {"proposals_expired": 2, "laws_deactivated": 3}
    assert calls == [(session, "real-test")]
    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True
