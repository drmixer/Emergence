from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, AgentLineage, Event, SimulationRun
from app.services.epoch_tournament import select_epoch_tournament_candidates


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
    AgentLineage.__table__.create(bind=engine)

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


def _seed_agent(db_session, agent_number: int) -> Agent:
    agent = Agent(
        agent_number=agent_number,
        display_name=f"Agent {agent_number}",
        model_type="gm_gemini_2_5_flash",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="prompt",
    )
    db_session.add(agent)
    db_session.flush()
    return agent


def _seed_run(db_session, *, run_id: str, season_id: str, epoch_id: str, started_at: datetime) -> None:
    db_session.add(
        SimulationRun(
            run_id=run_id,
            run_mode="real",
            protocol_version="protocol_v1",
            condition_name="carryover_v1",
            season_id=season_id,
            season_number=1,
            epoch_id=epoch_id,
            run_class="standard_72h",
            started_at=started_at,
            ended_at=started_at + timedelta(hours=72),
        )
    )


def _seed_agent_run_activity(
    db_session,
    *,
    run_id: str,
    season_id: str,
    agent_id: int,
    agent_number: int,
    meaningful_actions: int = 12,
    llm_calls: int = 10,
) -> None:
    base_time = datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc)
    for idx in range(meaningful_actions):
        db_session.add(
            Event(
                agent_id=agent_id,
                event_type="work",
                description=f"work-{agent_number}-{idx}",
                event_metadata={"runtime": {"run_id": run_id, "season_id": season_id}},
                created_at=base_time + timedelta(minutes=idx),
            )
        )

    for idx in range(llm_calls):
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
                "total_tokens": 120,
                "estimated_cost_usd": 0.01,
                "created_at": base_time + timedelta(minutes=idx),
            },
        )


def test_select_epoch_tournament_candidates_deterministic_top_two_per_season():
    db_session = _build_session()
    try:
        t0 = datetime(2026, 2, 10, 0, 0, tzinfo=timezone.utc)
        _seed_run(db_session, run_id="run-s1", season_id="season-1", epoch_id="epoch-1", started_at=t0)
        _seed_run(db_session, run_id="run-s2", season_id="season-2", epoch_id="epoch-1", started_at=t0 + timedelta(days=4))

        agents = {number: _seed_agent(db_session, number) for number in (1, 2, 3, 4, 5)}
        db_session.commit()

        _seed_agent_run_activity(db_session, run_id="run-s1", season_id="season-1", agent_id=agents[1].id, agent_number=1)
        _seed_agent_run_activity(db_session, run_id="run-s1", season_id="season-1", agent_id=agents[2].id, agent_number=2)
        _seed_agent_run_activity(db_session, run_id="run-s1", season_id="season-1", agent_id=agents[3].id, agent_number=3)
        _seed_agent_run_activity(db_session, run_id="run-s2", season_id="season-2", agent_id=agents[4].id, agent_number=4)
        _seed_agent_run_activity(db_session, run_id="run-s2", season_id="season-2", agent_id=agents[5].id, agent_number=5)
        db_session.commit()

        result = select_epoch_tournament_candidates(
            db_session,
            epoch_id="epoch-1",
            champions_per_season=2,
            target_total_champions=None,
            write_artifacts=False,
        )

        payload = result["payload"]
        assert payload["candidate_count"] == 5
        assert payload["eligible_count"] == 5
        assert payload["selected_count"] == 4

        selected = payload["selected"]
        assert [(row["season_id"], row["agent_number"]) for row in selected] == [
            ("season-1", 1),
            ("season-1", 2),
            ("season-2", 4),
            ("season-2", 5),
        ]
        assert all(row["selection_status"] == "selected_primary" for row in selected)
    finally:
        db_session.close()


def test_select_epoch_tournament_candidates_applies_wildcard_fill_for_season_deficit():
    db_session = _build_session()
    try:
        t0 = datetime(2026, 2, 10, 0, 0, tzinfo=timezone.utc)
        _seed_run(db_session, run_id="run-w1", season_id="season-a", epoch_id="epoch-w", started_at=t0)
        _seed_run(db_session, run_id="run-w2", season_id="season-b", epoch_id="epoch-w", started_at=t0 + timedelta(days=4))

        agents = {number: _seed_agent(db_session, number) for number in (1, 2, 3, 4)}
        db_session.commit()

        _seed_agent_run_activity(db_session, run_id="run-w1", season_id="season-a", agent_id=agents[1].id, agent_number=1)
        _seed_agent_run_activity(db_session, run_id="run-w2", season_id="season-b", agent_id=agents[2].id, agent_number=2)
        _seed_agent_run_activity(db_session, run_id="run-w2", season_id="season-b", agent_id=agents[3].id, agent_number=3)
        _seed_agent_run_activity(db_session, run_id="run-w2", season_id="season-b", agent_id=agents[4].id, agent_number=4)
        db_session.commit()

        result = select_epoch_tournament_candidates(
            db_session,
            epoch_id="epoch-w",
            champions_per_season=2,
            target_total_champions=None,
            write_artifacts=False,
        )

        payload = result["payload"]
        assert payload["selected_count"] == 4

        selected = payload["selected"]
        assert ("season-a", 1) in {(row["season_id"], row["agent_number"]) for row in selected}

        wildcard_rows = [row for row in selected if row["selection_status"] == "selected_wildcard"]
        assert len(wildcard_rows) == 1
        assert wildcard_rows[0]["season_id"] == "season-b"
        assert wildcard_rows[0]["agent_number"] == 4
    finally:
        db_session.close()
