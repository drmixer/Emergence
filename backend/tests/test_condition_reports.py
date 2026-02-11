from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, Event, RunReportArtifact, SimulationRun
from app.services.condition_reports import (
    compare_condition_runs,
    evaluate_run_claim_readiness,
    generate_and_record_condition_comparison,
    generate_and_record_run_summary,
    generate_run_report_summary,
    render_condition_comparison_markdown,
    render_run_report_markdown,
)


def _seed_llm_usage_rows(db_session, *, run_id: str, agent_id: int, calls: int, cost_per_call: float, start_at: datetime) -> None:
    for idx in range(calls):
        created_at = start_at + timedelta(minutes=idx)
        db_session.execute(
            text(
                """
                INSERT INTO llm_usage (
                    run_id, agent_id, success, fallback_used, total_tokens, estimated_cost_usd, created_at
                ) VALUES (
                    :run_id, :agent_id, :success, :fallback_used, :total_tokens, :estimated_cost_usd, :created_at
                )
                """
            ),
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "success": True,
                "fallback_used": False,
                "total_tokens": 100,
                "estimated_cost_usd": float(cost_per_call),
                "created_at": created_at,
            },
        )


def _seed_event_rows(db_session, *, run_id: str, agent_id: int, event_type: str, count: int, start_at: datetime) -> None:
    for idx in range(count):
        db_session.add(
            Event(
                agent_id=agent_id,
                event_type=event_type,
                description=f"{event_type}-{idx}",
                event_metadata={"runtime": {"run_id": run_id}},
                created_at=start_at + timedelta(minutes=idx),
            )
        )


def _metric_value(payload: dict, metric_key: str) -> float:
    rows = payload.get("core_metric_aggregates") or []
    for row in rows:
        if row.get("metric_key") == metric_key:
            return float(row.get("median") or 0.0)
    return 0.0


def _metric_spread(payload: dict, metric_key: str) -> float:
    rows = payload.get("core_metric_aggregates") or []
    for row in rows:
        if row.get("metric_key") == metric_key:
            return float(row.get("spread") or 0.0)
    return 0.0


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
    Event.__table__.create(bind=engine)
    RunReportArtifact.__table__.create(bind=engine)

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


def test_generate_run_report_summary_includes_replicate_context_and_metrics():
    db_session = _build_session()
    try:
        agent = Agent(
            agent_number=1,
            display_name="Agent 1",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        db_session.add(agent)
        db_session.flush()

        t0 = datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc)
        db_session.add_all(
            [
                SimulationRun(
                    run_id="run-a",
                    run_mode="real",
                    protocol_version="protocol_v1",
                    condition_name="baseline_v1",
                    run_class="standard_72h",
                    started_at=t0,
                ),
                SimulationRun(
                    run_id="run-b",
                    run_mode="real",
                    protocol_version="protocol_v1",
                    condition_name="baseline_v1",
                    run_class="standard_72h",
                    started_at=t0 + timedelta(hours=1),
                ),
            ]
        )
        _seed_llm_usage_rows(
            db_session,
            run_id="run-a",
            agent_id=agent.id,
            calls=3,
            cost_per_call=0.05,
            start_at=t0,
        )
        _seed_event_rows(
            db_session,
            run_id="run-a",
            agent_id=agent.id,
            event_type="create_proposal",
            count=2,
            start_at=t0,
        )
        _seed_event_rows(
            db_session,
            run_id="run-a",
            agent_id=agent.id,
            event_type="vote",
            count=1,
            start_at=t0,
        )
        db_session.commit()

        summary = generate_run_report_summary(db_session, run_id="run-a")
        markdown = render_run_report_markdown(summary)

        assert summary["condition_name"] == "baseline_v1"
        assert summary["replicate_index"] == 1
        assert summary["replicate_count"] == 2
        assert summary["metrics"]["llm_calls"] == 3
        assert summary["metrics"]["proposal_actions"] == 2
        assert summary["metrics"]["vote_actions"] == 1
        assert "Metric Table" in markdown
        assert "Replicate index" in markdown
    finally:
        db_session.close()


def test_compare_condition_runs_computes_median_and_spread():
    db_session = _build_session()
    try:
        agent = Agent(
            agent_number=1,
            display_name="Agent 1",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        db_session.add(agent)
        db_session.flush()

        base_time = datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc)
        run_specs = [
            ("run-c1", 2, 0.10, 1),
            ("run-c2", 4, 0.20, 2),
            ("run-c3", 6, 0.30, 3),
        ]
        for idx, (run_id, calls, cost_per_call, proposal_count) in enumerate(run_specs):
            db_session.add(
                SimulationRun(
                    run_id=run_id,
                    run_mode="real",
                    protocol_version="protocol_v1",
                    condition_name="carryover_v1",
                    run_class="standard_72h",
                    started_at=base_time + timedelta(hours=idx),
                )
            )
            _seed_llm_usage_rows(
                db_session,
                run_id=run_id,
                agent_id=agent.id,
                calls=calls,
                cost_per_call=cost_per_call,
                start_at=base_time + timedelta(hours=idx),
            )
            _seed_event_rows(
                db_session,
                run_id=run_id,
                agent_id=agent.id,
                event_type="create_proposal",
                count=proposal_count,
                start_at=base_time + timedelta(hours=idx),
            )
        db_session.commit()

        payload = compare_condition_runs(
            db_session,
            condition_name="carryover_v1",
            min_replicates=3,
        )
        markdown = render_condition_comparison_markdown(payload)

        assert payload["replicate_count"] == 3
        assert payload["meets_replicate_threshold"] is True
        assert _metric_value(payload, "llm_calls") == 4.0
        assert _metric_spread(payload, "llm_calls") == 4.0
        assert _metric_value(payload, "proposal_actions") == 2.0
        assert "Core Metric Aggregates (Median + Spread)" in markdown
    finally:
        db_session.close()


def test_generate_and_record_reports_persists_artifact_rows():
    db_session = _build_session()
    try:
        agent = Agent(
            agent_number=1,
            display_name="Agent 1",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        db_session.add(agent)
        db_session.flush()

        base_time = datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc)
        db_session.add(
            SimulationRun(
                run_id="run-record-1",
                run_mode="real",
                protocol_version="protocol_v1",
                condition_name="baseline_v1",
                run_class="standard_72h",
                started_at=base_time,
            )
        )
        _seed_llm_usage_rows(
            db_session,
            run_id="run-record-1",
            agent_id=agent.id,
            calls=2,
            cost_per_call=0.2,
            start_at=base_time,
        )
        db_session.commit()

        run_summary = generate_and_record_run_summary(db_session, run_id="run-record-1")
        condition_summary = generate_and_record_condition_comparison(
            db_session,
            condition_name="baseline_v1",
            min_replicates=1,
        )
        db_session.commit()

        assert run_summary["payload"]["run_id"] == "run-record-1"
        assert condition_summary["payload"]["condition_name"] == "baseline_v1"
        assert db_session.query(RunReportArtifact).filter_by(artifact_type="run_summary").count() == 2
        assert (
            db_session.query(RunReportArtifact)
            .filter_by(artifact_type="condition_comparison")
            .count()
            == 2
        )
    finally:
        db_session.close()


def test_compare_condition_runs_enforces_run_class_and_duration_consistency():
    db_session = _build_session()
    try:
        agent = Agent(
            agent_number=1,
            display_name="Agent 1",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        db_session.add(agent)
        db_session.flush()

        base_time = datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc)
        # Cohort A (selected): standard_72h and matching duration bucket.
        db_session.add_all(
            [
                SimulationRun(
                    run_id="run-gate-a1",
                    run_mode="real",
                    protocol_version="protocol_v1",
                    condition_name="baseline_v1",
                    run_class="standard_72h",
                    started_at=base_time,
                    ended_at=base_time + timedelta(hours=72),
                ),
                SimulationRun(
                    run_id="run-gate-a2",
                    run_mode="real",
                    protocol_version="protocol_v1",
                    condition_name="baseline_v1",
                    run_class="standard_72h",
                    started_at=base_time + timedelta(hours=1),
                    ended_at=base_time + timedelta(hours=73),
                ),
                # Same class, mismatched duration bucket.
                SimulationRun(
                    run_id="run-gate-b1",
                    run_mode="real",
                    protocol_version="protocol_v1",
                    condition_name="baseline_v1",
                    run_class="standard_72h",
                    started_at=base_time + timedelta(hours=2),
                    ended_at=base_time + timedelta(hours=98),
                ),
                # Exploratory run should always be excluded from baseline comparison.
                SimulationRun(
                    run_id="run-gate-exp",
                    run_mode="real",
                    protocol_version="protocol_v1",
                    condition_name="baseline_v1",
                    run_class="special_exploratory",
                    started_at=base_time + timedelta(hours=3),
                    ended_at=base_time + timedelta(hours=99),
                ),
            ]
        )

        for idx, run_id in enumerate(["run-gate-a1", "run-gate-a2", "run-gate-b1", "run-gate-exp"]):
            _seed_llm_usage_rows(
                db_session,
                run_id=run_id,
                agent_id=agent.id,
                calls=3 + idx,
                cost_per_call=0.1,
                start_at=base_time + timedelta(hours=idx),
            )
            _seed_event_rows(
                db_session,
                run_id=run_id,
                agent_id=agent.id,
                event_type="create_proposal",
                count=1 + idx,
                start_at=base_time + timedelta(hours=idx),
            )
        db_session.commit()

        payload = compare_condition_runs(db_session, condition_name="baseline_v1", min_replicates=2)
        excluded_by_id = {str(item.get("run_id")): str(item.get("reason")) for item in (payload.get("excluded_runs") or [])}

        assert payload["selected_run_class"] == "standard_72h"
        assert payload["selected_duration_bucket_hours"] == 72
        assert payload["run_ids"] == ["run-gate-a1", "run-gate-a2"]
        assert payload["replicate_count"] == 2
        assert excluded_by_id["run-gate-b1"] == "duration_bucket_mismatch"
        assert excluded_by_id["run-gate-exp"] == "special_exploratory_excluded"
    finally:
        db_session.close()


def test_evaluate_run_claim_readiness_blocks_exploratory_runs():
    db_session = _build_session()
    try:
        run = SimulationRun(
            run_id="run-exploratory-1",
            run_mode="real",
            protocol_version="protocol_v1",
            condition_name="baseline_v1",
            run_class="special_exploratory",
            started_at=datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 11, 12, 0, tzinfo=timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        readiness = evaluate_run_claim_readiness(db_session, run_id="run-exploratory-1", min_replicates=3)
        assert readiness["gate_reason"] == "exploratory_run_class"
        assert readiness["meets_replicate_threshold"] is False
        assert readiness["replicate_count"] == 1
    finally:
        db_session.close()
