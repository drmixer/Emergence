from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, Event, GlobalResources, Message, Proposal
from app.services import actions
from app.services.executable_governance import execute_allocation_effect_for_passed_proposal


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


def _seed_agent(db, *, agent_number: int, status: str = "active") -> Agent:
    agent = Agent(
        agent_number=agent_number,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="neutral",
        status=status,
        system_prompt="Test prompt",
    )
    db.add(agent)
    db.flush()
    db.add_all(
        [
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=Decimal("0")),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=Decimal("0")),
            AgentInventory(agent_id=agent.id, resource_type="materials", quantity=Decimal("0")),
        ]
    )
    return agent


def test_create_proposal_accepts_structured_runtime_effect():
    engine, factory = _session_factory()
    try:
        with factory() as db:
            author = _seed_agent(db, agent_number=1)
            recipient = _seed_agent(db, agent_number=2)
            energy = (
                db.query(AgentInventory)
                .filter(AgentInventory.agent_id == author.id, AgentInventory.resource_type == "energy")
                .one()
            )
            energy.quantity = Decimal("5")
            db.commit()

            action = {
                "action": "create_proposal",
                "title": "One-Time Common Pool Allocation",
                "description": "Move food once if the pool floor remains intact.",
                "proposal_type": "allocation",
                "governance_class": "allocation",
                "runtime_effect": {
                    "type": "common_pool_allocation",
                    "transfers": [
                        {
                            "recipient_agent_id": recipient.agent_number,
                            "resource_type": "food",
                            "amount": 2,
                        }
                    ],
                    "min_pool_remaining": 25,
                },
            }

            validation = asyncio.run(actions.validate_action(db, author, action))
            assert validation["valid"] is True
            assert action["governance_class"] == "allocation"
            assert action["runtime_effect"]["type"] == "common_pool_allocation"

            result = asyncio.run(actions.execute_action(db, author, action))

            proposal = db.query(Proposal).filter(Proposal.id == result["proposal_id"]).one()
            assert proposal.governance_class == "allocation"
            assert proposal.runtime_effect["transfers"][0]["recipient_agent_id"] == recipient.agent_number
    finally:
        engine.dispose()


def test_common_pool_allocation_executes_and_logs_transfer():
    engine, factory = _session_factory()
    try:
        with factory() as db:
            author = _seed_agent(db, agent_number=1)
            recipient = _seed_agent(db, agent_number=2, status="dormant")
            db.add(GlobalResources(resource_type="food", total_amount=Decimal("30"), in_common_pool=Decimal("30")))
            proposal = Proposal(
                author_agent_id=author.id,
                title="Immediate Food Allocation",
                description="Transfer food from the common pool once.",
                proposal_type="allocation",
                governance_class="allocation",
                runtime_effect={
                    "type": "common_pool_allocation",
                    "transfers": [
                        {
                            "recipient_agent_id": recipient.agent_number,
                            "resource_type": "food",
                            "amount": 2,
                        }
                    ],
                    "min_pool_remaining": 25,
                    "reactivate_dormant": False,
                },
                status="passed",
                voting_closes_at=now_utc() - timedelta(minutes=1),
            )
            db.add(proposal)
            db.flush()

            result = execute_allocation_effect_for_passed_proposal(db, proposal)
            db.commit()

            food_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "food").one()
            recipient_food = (
                db.query(AgentInventory)
                .filter(AgentInventory.agent_id == recipient.id, AgentInventory.resource_type == "food")
                .one()
            )
            execution_event = db.query(Event).filter(Event.event_type == "governance_execution").one()

            assert result["status"] == "executed"
            assert float(food_pool.in_common_pool) == 28.0
            assert float(recipient_food.quantity) == 2.0
            assert execution_event.event_metadata["execution_status"] == "executed"
            assert execution_event.event_metadata["transfers"][0]["recipient_agent_number"] == 2
    finally:
        engine.dispose()


def test_repeated_refusal_to_same_latest_aid_request_is_rejected():
    engine, factory = _session_factory()
    try:
        with factory() as db:
            refuser = _seed_agent(db, agent_number=1)
            requester = _seed_agent(db, agent_number=2)
            energy = (
                db.query(AgentInventory)
                .filter(AgentInventory.agent_id == refuser.id, AgentInventory.resource_type == "energy")
                .one()
            )
            energy.quantity = Decimal("5")
            request_message = Message(
                author_agent_id=requester.id,
                recipient_agent_id=refuser.id,
                message_type="direct_message",
                content="I am requesting 2 food from you.",
            )
            db.add(request_message)
            db.flush()
            request_event = Event(
                agent_id=refuser.id,
                event_type="aid_request_received",
                description="Agent #2 requested 2 food.",
                event_metadata={
                    "requesting_agent_id": requester.id,
                    "target_agent_id": refuser.id,
                    "resource_type": "food",
                    "amount": "2",
                    "message_id": request_message.id,
                },
            )
            db.add(request_event)
            db.flush()
            db.add(
                Event(
                    agent_id=requester.id,
                    event_type="aid_refusal_received",
                    description="Agent #1 refused aid.",
                    event_metadata={
                        "refusing_agent_id": refuser.id,
                        "target_agent_id": requester.id,
                        "request_event_id": request_event.id,
                        "request_message_id": request_message.id,
                    },
                )
            )
            db.commit()

            result = asyncio.run(
                actions.validate_action(
                    db,
                    refuser,
                    {
                        "action": "refuse_aid",
                        "target_agent_id": requester.agent_number,
                        "reason": "I already answered this request.",
                    },
                )
            )

            assert result["valid"] is False
            assert result["reason_code"] == "aid_request_already_refused"
    finally:
        engine.dispose()
