from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Agent, Law
from app.services import law_effects
from app.services.live_run_scope import LiveRunWindow


def _session_factory():
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

    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, future=True)


def _seed_agent(db) -> Agent:
    agent = Agent(
        agent_number=1,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="Test prompt",
    )
    db.add(agent)
    db.flush()
    return agent


def _seed_law(db, *, agent: Agent, title: str, description: str, passed_at: datetime) -> Law:
    law = Law(
        title=title,
        description=description,
        author_agent_id=agent.id,
        active=True,
        passed_at=passed_at,
    )
    db.add(law)
    db.flush()
    return law


def test_common_pool_contribution_law_is_reserve_equivalent():
    assert law_effects.is_survival_reserve_law_value(
        title="Shared Resource Contribution and Aid Law",
        description=(
            "Establish a law for mandatory proportional contribution to the common pool "
            "for agents with surplus resources, and define criteria for aid distribution "
            "to agents facing dormancy."
        ),
    )


def test_active_survival_reserve_laws_are_scoped_to_live_run(monkeypatch):
    engine, factory = _session_factory()
    run_started_at = datetime(2026, 4, 28, 1, 21, tzinfo=timezone.utc)
    try:
        monkeypatch.setattr(
            law_effects,
            "get_live_run_window",
            lambda _db: LiveRunWindow(
                run_id="real-20260428T012055Z",
                started_at=run_started_at,
                ended_at=None,
            ),
        )

        with factory() as db:
            agent = _seed_agent(db)
            old_law = _seed_law(
                db,
                agent=agent,
                title="Shared Survival Reserve Law",
                description="Create a shared survival reserve for aid.",
                passed_at=run_started_at - timedelta(days=1),
            )
            current_law = _seed_law(
                db,
                agent=agent,
                title="Shared Resource Contribution and Aid Law",
                description="Require contribution to the common pool for aid during dormancy.",
                passed_at=run_started_at + timedelta(minutes=5),
            )
            db.commit()
            old_law_id = old_law.id
            current_law_id = current_law.id

            laws = law_effects.active_survival_reserve_laws(db)

        assert [law.id for law in laws] == [current_law_id]
        assert old_law_id not in [law.id for law in laws]
    finally:
        engine.dispose()


def test_active_survival_reserve_laws_empty_without_live_run(monkeypatch):
    engine, factory = _session_factory()
    try:
        monkeypatch.setattr(
            law_effects,
            "get_live_run_window",
            lambda _db: LiveRunWindow(run_id=None, started_at=None, ended_at=None),
        )

        with factory() as db:
            agent = _seed_agent(db)
            _seed_law(
                db,
                agent=agent,
                title="Shared Survival Reserve Law",
                description="Create a shared survival reserve for aid.",
                passed_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
            )
            db.commit()

            assert law_effects.active_survival_reserve_laws(db) == []
    finally:
        engine.dispose()
