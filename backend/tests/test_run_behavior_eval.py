from datetime import datetime, timedelta, timezone
import json
import sys

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, AgentInventory, Event, GlobalResources, SimulationRun
from scripts.run_behavior_eval import (
    _build_first_cycle_reserve_trace,
    _reserve_readiness_diagnostics_for_run,
    _reserve_stress_runtime_overrides,
    _reserve_profile_post_law_min_runtime_seconds,
    _smoke_ready,
)
from scripts import run_behavior_eval


def test_reserve_stress_v2_requires_one_post_law_survival_cycle_plus_poll():
    seconds = _reserve_profile_post_law_min_runtime_seconds(
        tuning={"profile": "reserve_stress_v2", "activation": "after_first_reserve_law"},
        day_length_minutes=10,
        poll_seconds=20,
    )
    assert seconds == 620


def test_non_reserve_profiles_do_not_add_post_law_runtime_gate():
    assert (
        _reserve_profile_post_law_min_runtime_seconds(
            tuning={"profile": "reserve_stress_v1", "activation": "after_reset"},
            day_length_minutes=10,
            poll_seconds=20,
        )
        == 0
    )


def test_reserve_stress_v2_runtime_overrides_reduce_provider_pressure():
    overrides = _reserve_stress_runtime_overrides(
        {"profile": "reserve_stress_v2", "activation": "after_first_reserve_law"}
    )
    assert overrides == {
        "AGENT_LOOP_DELAY_SECONDS": 90,
        "LLM_ACTION_PARSE_RETRY_ATTEMPTS": 0,
        "LLM_ACTION_MAX_TOKENS": 220,
    }


def test_non_reserve_profiles_do_not_change_runtime_pressure_defaults():
    assert _reserve_stress_runtime_overrides({"profile": "reserve_stress_v1"}) == {}


def test_smoke_ready_accepts_keyword_run_metrics_signature():
    assert _smoke_ready(
        run_metrics={
            "llm": {"calls": 5},
            "activity": {"forum_actions": 1},
            "governance": {"proposals_created": 1, "votes_cast": 1},
        },
        elapsed_seconds=12.0,
    )


def test_build_first_cycle_reserve_trace_groups_only_initial_cycle_window():
    base = datetime(2026, 4, 7, 20, 13, 31, tzinfo=timezone.utc)
    trace = _build_first_cycle_reserve_trace(
        [
            {
                "id": 1,
                "created_at": base,
                "event_type": "reserve_aid",
                "agent_id": 15,
                "agent_number": 15,
                "display_name": "Vertex-15",
                "status_before": "active",
                "support_mode": "active_maintenance",
                "aid_granted": True,
                "food_deficit": 0.0,
                "energy_deficit": 0.9,
                "reserve_pool_energy_before": 17.34,
                "reserve_pool_energy_after": 16.44,
            },
            {
                "id": 2,
                "created_at": base + timedelta(milliseconds=500),
                "event_type": "became_dormant",
                "agent_id": 24,
                "agent_number": 24,
                "display_name": "Prime-24",
                "aid_granted": False,
            },
            {
                "id": 3,
                "created_at": base + timedelta(seconds=2),
                "event_type": "reserve_shortfall",
                "agent_id": 30,
                "agent_number": 30,
                "display_name": "Chronon-30",
                "aid_granted": False,
            },
        ],
        trace_window_seconds=1,
    )

    assert trace["first_reserve_event_at"] == base.isoformat()
    assert trace["trace_window_seconds"] == 1
    assert [row["event_type"] for row in trace["first_cycle_trace"]] == [
        "reserve_aid",
        "became_dormant",
    ]


def _build_session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SimulationRun.__table__.create(bind=engine)
    Agent.__table__.create(bind=engine)
    AgentInventory.__table__.create(bind=engine)
    GlobalResources.__table__.create(bind=engine)
    Event.__table__.create(bind=engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    agent_id INTEGER NULL,
                    success BOOLEAN NOT NULL DEFAULT 1,
                    fallback_used BOOLEAN NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NULL
                )
                """
            )
        )

    return sessionmaker(bind=engine, future=True)()


def test_reserve_readiness_diagnostics_ignore_other_run_events(monkeypatch):
    db_session = _build_session()
    try:
        monkeypatch.setattr(run_behavior_eval, "active_survival_reserve_laws", lambda _db: [])
        started_at = datetime(2026, 4, 7, 20, 0, tzinfo=timezone.utc)
        ended_at = started_at + timedelta(minutes=5)

        agent_one = Agent(
            agent_number=1,
            display_name="Traceable One",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        agent_two = Agent(
            agent_number=2,
            display_name="Other Run",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        db_session.add_all([agent_one, agent_two])
        db_session.flush()

        db_session.add_all(
            [
                AgentInventory(agent_id=agent_one.id, resource_type="food", quantity=0.20),
                AgentInventory(agent_id=agent_one.id, resource_type="energy", quantity=0.10),
                AgentInventory(agent_id=agent_two.id, resource_type="food", quantity=0.90),
                AgentInventory(agent_id=agent_two.id, resource_type="energy", quantity=0.90),
                GlobalResources(resource_type="food", total_amount=5.0, in_common_pool=2.0),
                GlobalResources(resource_type="energy", total_amount=5.0, in_common_pool=2.0),
                Event(
                    agent_id=agent_one.id,
                    event_type="reserve_aid",
                    description="run-a reserve aid",
                    event_metadata={"runtime": {"run_id": "run-a"}, "support_mode": "active_maintenance"},
                    created_at=started_at + timedelta(seconds=5),
                ),
                Event(
                    agent_id=agent_two.id,
                    event_type="reserve_shortfall",
                    description="run-b reserve shortfall",
                    event_metadata={"runtime": {"run_id": "run-b"}, "support_mode": "active_maintenance"},
                    created_at=started_at + timedelta(seconds=6),
                ),
                Event(
                    agent_id=agent_two.id,
                    event_type="became_dormant",
                    description="run-b dormant",
                    event_metadata={"runtime": {"run_id": "run-b"}},
                    created_at=started_at + timedelta(seconds=7),
                ),
            ]
        )
        db_session.execute(
            text(
                """
                INSERT INTO llm_usage (
                    run_id, agent_id, success, fallback_used, total_tokens, estimated_cost_usd, created_at
                ) VALUES (
                    :run_id, :agent_id, 1, 0, 100, 0.01, :created_at
                )
                """
            ),
            {"run_id": "run-a", "agent_id": agent_one.id, "created_at": started_at},
        )
        db_session.commit()

        diagnostics = _reserve_readiness_diagnostics_for_run(
            db_session,
            run_id="run-a",
            started_at=started_at,
            ended_at=ended_at,
        )

        assert diagnostics["run_agent_count"] == 1
        assert diagnostics["reserve_event_counts"] == {"reserve_aid": 1}
        assert [row["event_type"] for row in diagnostics["first_cycle_trace"]] == ["reserve_aid"]
        assert diagnostics["first_cycle_trace"][0]["agent_number"] == 1
    finally:
        db_session.close()


def test_main_persists_batch_snapshots_before_later_reset(monkeypatch, tmp_path):
    run_prefix = "behavior-eval-checkpoint"
    report_root = tmp_path / "output" / "reports" / "runs"

    def _summary_for(run_id: str) -> dict:
        return {
            "run_id": run_id,
            "condition_name": "behavior_eval_control_v1",
            "technical_report": {
                "activity": {
                    "total_events": 90,
                    "forum_actions": 6,
                    "trade_actions": 1,
                    "proposal_actions": 1,
                    "vote_actions": 1,
                    "cooperation_events": 4,
                    "conflict_events": 1,
                    "checkpoint_actions": 60,
                },
                "inequality_gini_current": 0.02,
            },
            "run_summary": {
                "metrics": {
                    "llm_calls": 12,
                    "total_events": 90,
                    "proposal_actions": 1,
                    "vote_actions": 1,
                    "cooperation_events": 4,
                    "conflict_events": 1,
                }
            },
            "derived_metrics": {
                "runtime_seconds": 180,
                "event_counts": {
                    "reserve_aid": 2,
                    "reserve_shortfall": 1,
                    "forum_post": 4,
                    "vote": 1,
                },
            },
            "proposal_diagnostics": {},
            "vote_diagnostics": {},
            "law_effect_diagnostics": {},
            "reserve_readiness_diagnostics": {
                "active_reserve_law_count": 1,
                "reserve_pool_food": 1.5,
                "reserve_pool_energy": 1.0,
                "min_agent_food": 0.1,
                "min_agent_energy": 0.1,
                "agents_below_active_survival_threshold": 1,
                "reserve_event_counts": {
                    "reserve_aid": 2,
                    "reserve_shortfall": 1,
                    "became_dormant": 1,
                },
                "first_reserve_event_at": "2026-04-07T20:56:40+00:00",
                "trace_window_seconds": 1,
                "first_cycle_trace": [
                    {
                        "event_type": "reserve_aid",
                        "created_at": "2026-04-07T20:56:40+00:00",
                        "agent_number": 7,
                    }
                ],
                "no_reserve_demand_signal": False,
            },
        }

    class FakeAdmin:
        def __init__(self, *_args, **_kwargs):
            self.started_runs: list[str] = []

        def close(self) -> None:
            return None

        def status(self) -> dict:
            return {"viewer_ops": {"run_id": ""}}

        def patch_config(self, updates: dict, *, reason: str) -> dict:
            return {"ok": True, "updates": updates, "reason": reason}

        def start_run(self, payload: dict) -> dict:
            run_id = str(payload["run_id"])
            if run_id.endswith("-b2"):
                prior_snapshot = report_root / f"{run_prefix}-b1" / "behavior_eval_snapshot.json"
                assert prior_snapshot.exists()
                prior_payload = json.loads(prior_snapshot.read_text(encoding="utf-8"))
                assert prior_payload["reserve_readiness_diagnostics"]["first_cycle_trace"][0]["event_type"] == "reserve_aid"
            self.started_runs.append(run_id)
            return {"ok": True, "run_id": run_id, "reset_world": bool(payload.get("reset_world"))}

        def stop_run(self, *, reason: str, clear_run_id: bool = True) -> dict:
            return {"ok": True, "reason": reason, "clear_run_id": clear_run_id}

        def run_metrics(self, *, run_id: str) -> dict:
            if run_id.endswith("-smoke"):
                return {
                    "llm": {"calls": 6},
                    "activity": {"forum_actions": 2},
                    "governance": {"proposals_created": 1, "votes_cast": 1},
                }
            return {
                "llm": {"calls": 12},
                "activity": {"forum_actions": 4, "checkpoint_actions": 55},
                "governance": {"proposals_created": 1, "votes_cast": 1},
            }

        def reset_dev_world(self, *, reason: str) -> dict:
            return {"ok": True, "reason": reason}

    monkeypatch.setattr(run_behavior_eval, "AdminClient", FakeAdmin)
    monkeypatch.setattr(run_behavior_eval, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_behavior_eval, "_read_runtime_settings", lambda *, keys: {key: None for key in keys})
    monkeypatch.setattr(run_behavior_eval, "_summarize_run", lambda *, run_id, condition_name, season_number: _summary_for(run_id))
    monkeypatch.setattr(
        run_behavior_eval,
        "generate_and_record_condition_comparison",
        lambda db, *, condition_name, min_replicates, season_number: {
            "payload": {
                "condition_name": condition_name,
                "replicate_count": 2,
                "meets_replicate_threshold": False,
                "selected_run_class": "standard_72h",
                "selected_duration_bucket_hours": 72,
            },
            "artifacts": {},
        },
    )
    monkeypatch.setattr(run_behavior_eval, "SessionLocal", lambda: None)
    monkeypatch.setattr(run_behavior_eval.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_behavior_eval.py",
            "--mode",
            "control",
            "--admin-token",
            "token",
            "--run-prefix",
            run_prefix,
            "--output-dir",
            str(tmp_path / "output" / "evals" / run_prefix),
            "--smoke-seconds",
            "1",
            "--batch-seconds",
            "1",
            "--batch-runs",
            "2",
            "--poll-seconds",
            "1",
        ],
    )

    class _FakeDB:
        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(run_behavior_eval, "SessionLocal", lambda: _FakeDB())

    assert run_behavior_eval.main() == 0

    snapshot_one = report_root / f"{run_prefix}-b1" / "behavior_eval_snapshot.json"
    snapshot_two = report_root / f"{run_prefix}-b2" / "behavior_eval_snapshot.json"
    assert snapshot_one.exists()
    assert snapshot_two.exists()
    persisted = json.loads(snapshot_one.read_text(encoding="utf-8"))
    assert persisted["reserve_readiness_diagnostics"]["first_cycle_trace"][0]["event_type"] == "reserve_aid"
