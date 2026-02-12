from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, AgentAction
from app.services.actions import execute_action, validate_action
from app.services.agent_identity import immutable_alias_for_agent_number


@pytest.fixture
def db_session():
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

    Agent.__table__.create(bind=engine)
    AgentAction.__table__.create(bind=engine)

    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


def test_immutable_aliases_are_unique_for_default_50():
    aliases = [immutable_alias_for_agent_number(number) for number in range(1, 51)]
    assert len(aliases) == len(set(aliases))
    assert aliases[0] == "Tensor-01"
    assert aliases[49] == "Apex-50"


def test_set_name_action_is_noop_under_immutable_alias_policy(db_session):
    agent = Agent(
        agent_number=1,
        display_name="Tensor-01",
        model_type="gm_gemini_2_5_flash",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="test",
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)

    result = asyncio.run(
        validate_action(
            db_session,
            agent,
            {"action": "set_name", "display_name": "NewName"},
        )
    )

    assert result["valid"] is True

    execution = asyncio.run(
        execute_action(
            db_session,
            agent,
            {"action": "set_name", "display_name": "NewName"},
        )
    )
    db_session.refresh(agent)

    assert execution["success"] is True
    assert "immutable" in execution["description"].lower()
    assert agent.display_name == "Tensor-01"
