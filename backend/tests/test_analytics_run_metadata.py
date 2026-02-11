from __future__ import annotations

from datetime import datetime, timezone
import importlib

from app.models.models import SimulationRun

analytics_api = importlib.import_module("app.api.analytics")


def test_serialize_run_registry_metadata_includes_phase4_fields():
    row = SimulationRun(
        run_id="run-meta-01",
        run_mode="real",
        protocol_version="protocol_v2",
        condition_name="carryover_v1",
        season_id="season-5",
        season_number=5,
        transfer_policy_version="season_transfer_policy_v1",
        run_class="deep_96h",
        carryover_agent_count=12,
        fresh_agent_count=38,
        protocol_deviation=True,
        deviation_reason="guardrail-stop",
        started_at=datetime(2026, 2, 11, 1, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 2, 11, 9, 0, tzinfo=timezone.utc),
    )

    payload = analytics_api._serialize_run_registry_metadata(row)
    assert payload is not None
    assert payload["season_id"] == "season-5"
    assert payload["season_number"] == 5
    assert payload["transfer_policy_version"] == "season_transfer_policy_v1"
    assert payload["carryover_agent_count"] == 12
    assert payload["fresh_agent_count"] == 38
    assert payload["protocol_deviation"] is True


def test_serialize_run_registry_metadata_none():
    assert analytics_api._serialize_run_registry_metadata(None) is None
