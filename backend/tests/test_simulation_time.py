from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import importlib
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, Event
from app.services import simulation_time

summaries = importlib.import_module("app.services.summaries")


@pytest.fixture
def simulation_session_factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Agent.__table__.create(bind=engine)
    Event.__table__.create(bind=engine)
    return sessionmaker(bind=engine, future=True)


def _seed_agent() -> Agent:
    return Agent(
        id=1,
        agent_number=1,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="freedom",
        system_prompt="Test system prompt",
    )


def test_simulation_day_uses_latest_non_summary_activity(simulation_session_factory, monkeypatch):
    session_factory = simulation_session_factory
    anchor = datetime(2026, 2, 10, 5, 2, 24, tzinfo=timezone.utc)
    latest_core = anchor + timedelta(hours=39, minutes=50)
    much_later_summary = anchor + timedelta(days=50)
    monkeypatch.setattr(
        simulation_time.runtime_config_service,
        "get_effective_value_cached",
        lambda key: 60 if key == "DAY_LENGTH_MINUTES" else "",
    )

    with session_factory() as db:
        db.add(_seed_agent())
        db.add(
            Event(
                agent_id=1,
                event_type="work",
                description="Start",
                created_at=anchor,
            )
        )
        db.add(
            Event(
                agent_id=1,
                event_type="work",
                description="Latest core activity",
                created_at=latest_core,
            )
        )
        db.add(
            Event(
                event_type="daily_summary",
                description="Late summary import",
                event_metadata={"day_number": 999},
                created_at=much_later_summary,
            )
        )
        db.commit()

        assert simulation_time.get_simulation_day_number(db) == 40
        assert simulation_time.get_completed_simulation_day_count(db) == 39


def test_summary_scheduler_does_not_backfill_idle_wall_clock_gap(
    monkeypatch,
    simulation_session_factory,
):
    session_factory = simulation_session_factory
    anchor = datetime(2026, 2, 10, 5, 2, 24, tzinfo=timezone.utc)
    latest_core = anchor + timedelta(minutes=90)
    much_later_now = anchor + timedelta(days=60)
    monkeypatch.setattr(
        simulation_time.runtime_config_service,
        "get_effective_value_cached",
        lambda key: 60 if key == "DAY_LENGTH_MINUTES" else "",
    )

    with session_factory() as db:
        db.add(_seed_agent())
        db.add(
            Event(
                agent_id=1,
                event_type="work",
                description="Start",
                created_at=anchor,
            )
        )
        db.add(
            Event(
                agent_id=1,
                event_type="work",
                description="Latest core activity",
                created_at=latest_core,
            )
        )
        db.add(
            Event(
                event_type="daily_summary",
                description="Day 1 Summary",
                event_metadata={"day_number": 1, "summary": "Done."},
                created_at=latest_core + timedelta(minutes=1),
            )
        )
        db.commit()

    monkeypatch.setattr(summaries, "SessionLocal", session_factory)
    monkeypatch.setattr(summaries.settings, "SUMMARIES_ENABLED", True, raising=False)
    monkeypatch.setattr(summaries, "now_utc", lambda: much_later_now)

    result = asyncio.run(summaries.summary_scheduler.check_and_generate())

    assert result is None
