from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, Event, GlobalResources, Law, Message, Proposal
from app.services import actions
from app.services.executable_governance import (
    execute_active_reserve_aid_amendment_for_passed_proposal,
    execute_allocation_effect_for_passed_proposal,
)


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


def test_create_proposal_rejects_unsupported_runtime_effect():
    engine, factory = _session_factory()
    try:
        with factory() as db:
            author = _seed_agent(db, agent_number=1)
            energy = (
                db.query(AgentInventory)
                .filter(AgentInventory.agent_id == author.id, AgentInventory.resource_type == "energy")
                .one()
            )
            energy.quantity = Decimal("5")
            db.commit()

            action = {
                "action": "create_proposal",
                "title": "Dormant Revival Standing Law",
                "description": "Revive dormant agents from the common pool when resources allow.",
                "proposal_type": "law",
                "governance_class": "standing_law",
                "runtime_effect": {"type": "dormant_revival", "min_pool_remaining": 25},
            }

            validation = asyncio.run(actions.validate_action(db, author, action))

            assert validation["valid"] is False
            assert validation["reason_code"] == "unsupported_runtime_effect"
            assert "Supported runtime_effect.type values" in validation["reason"]
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


def test_create_proposal_infers_bounded_active_aid_amendment_effect():
    engine, factory = _session_factory()
    try:
        with factory() as db:
            author = _seed_agent(db, agent_number=1)
            energy = (
                db.query(AgentInventory)
                .filter(AgentInventory.agent_id == author.id, AgentInventory.resource_type == "energy")
                .one()
            )
            energy.quantity = Decimal("5")
            law = Law(
                title="Active Threshold Aid Standing Law",
                description="Top up active agents below thresholds.",
                law_class="standing_law",
                runtime_effect={
                    "type": "active_reserve_aid",
                    "trigger_food_below": 2,
                    "trigger_energy_below": 2,
                    "target_food": 3,
                    "target_energy": 3,
                    "min_pool_remaining": 25,
                },
                active=True,
                author_agent_id=author.id,
            )
            db.add(law)
            db.commit()

            action = {
                "action": "create_proposal",
                "title": f"Amendment to Law #{law.id}: Proactive Energy Threshold",
                "description": "Amend Law to adjust the energy trigger to E3.0 and target to E4.0.",
                "proposal_type": "amendment",
            }

            validation = asyncio.run(actions.validate_action(db, author, action))

            assert validation == {"valid": True}
            assert action["governance_class"] == "amendment"
            assert action["runtime_effect"] == {
                "type": "active_reserve_aid_amendment",
                "description": "One-time bounded amendment to an existing active reserve aid law runtime effect.",
                "target_law_id": law.id,
                "trigger_energy_below": 3.0,
                "target_energy": 4.0,
            }
    finally:
        engine.dispose()


def test_active_aid_amendment_executes_against_target_law():
    engine, factory = _session_factory()
    try:
        with factory() as db:
            author = _seed_agent(db, agent_number=1)
            target_law = Law(
                title="Active Threshold Aid Standing Law",
                description="Top up active agents below thresholds.",
                law_class="standing_law",
                runtime_effect={
                    "type": "active_reserve_aid",
                    "trigger_food_below": 2,
                    "trigger_energy_below": 2,
                    "target_food": 3,
                    "target_energy": 3,
                    "min_pool_remaining": 25,
                },
                active=True,
                author_agent_id=author.id,
            )
            db.add(target_law)
            db.flush()
            proposal = Proposal(
                author_agent_id=author.id,
                title="Amendment to Law: Proactive Energy Aid",
                description="Raise the energy trigger and target.",
                proposal_type="amendment",
                governance_class="amendment",
                runtime_effect={
                    "type": "active_reserve_aid_amendment",
                    "target_law_id": target_law.id,
                    "trigger_energy_below": 3,
                    "target_energy": 4,
                },
                status="passed",
                voting_closes_at=now_utc() - timedelta(minutes=1),
            )
            amendment_law = Law(
                proposal_id=proposal.id,
                title=proposal.title,
                description=proposal.description,
                law_class="amendment",
                runtime_effect=proposal.runtime_effect,
                active=True,
                author_agent_id=author.id,
            )
            db.add_all([proposal, amendment_law])
            db.flush()

            result = execute_active_reserve_aid_amendment_for_passed_proposal(
                db,
                proposal,
                amendment_law=amendment_law,
            )
            db.commit()

            db.refresh(target_law)
            execution_event = db.query(Event).filter(Event.event_type == "governance_execution").one()

            assert result["status"] == "executed"
            assert target_law.runtime_effect["trigger_energy_below"] == 3
            assert target_law.runtime_effect["target_energy"] == 4
            assert execution_event.event_metadata["details"]["target_law_id"] == target_law.id
            assert execution_event.event_metadata["details"]["applied_updates"] == {
                "trigger_energy_below": 3,
                "target_energy": 4,
            }
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


def test_procedural_observation_forum_post_is_rejected():
    engine, factory = _session_factory()
    try:
        with factory() as db:
            agent = _seed_agent(db, agent_number=1)
            energy = (
                db.query(AgentInventory)
                .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "energy")
                .one()
            )
            energy.quantity = Decimal("5")
            db.commit()

            result = asyncio.run(
                actions.validate_action(
                    db,
                    agent,
                    {
                        "action": "forum_post",
                        "content": "Observation: Law #227 is active and the common pool is visible.",
                    },
                )
            )

            assert result["valid"] is False
            assert result["reason_code"] == "procedural_status_memo"
    finally:
        engine.dispose()


def test_repeated_dormant_allocation_forum_wave_is_rejected():
    engine, factory = _session_factory()
    try:
        with factory() as db:
            first = _seed_agent(db, agent_number=1)
            second = _seed_agent(db, agent_number=2)
            energy = (
                db.query(AgentInventory)
                .filter(AgentInventory.agent_id == second.id, AgentInventory.resource_type == "energy")
                .one()
            )
            energy.quantity = Decimal("5")
            db.add(
                Message(
                    author_agent_id=first.id,
                    message_type="forum_post",
                    content=(
                        "Law #227 is executable but does not revive dormant agents retroactively. "
                        "A one-time allocation proposal naming the dormant agents is needed to close the recovery gap."
                    ),
                    created_at=now_utc(),
                )
            )
            db.commit()

            result = asyncio.run(
                actions.validate_action(
                    db,
                    second,
                    {
                        "action": "forum_post",
                        "content": (
                            "Law #227 is active and executable, but 8 agents are already dormant. "
                            "A one-time allocation proposal naming recipients and amounts is needed to revive them."
                        ),
                    },
                )
            )

            assert result["valid"] is False
            assert result["reason_code"] == "duplicate_forum_message"
    finally:
        engine.dispose()
