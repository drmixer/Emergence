from __future__ import annotations

import asyncio
from decimal import Decimal
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, Event, Message, Proposal
from app.services.agent_loop import AgentProcessor
from app.services import actions, context_builder


@pytest.fixture
def session_factory():
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
    factory = sessionmaker(bind=engine, future=True)
    try:
        yield factory
    finally:
        engine.dispose()


def _seed_agent(db, *, agent_number: int, display_name: str) -> Agent:
    agent = Agent(
        agent_number=agent_number,
        display_name=display_name,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="Test prompt",
    )
    db.add(agent)
    db.flush()
    db.add_all(
        [
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=Decimal("10")),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=Decimal("10")),
            AgentInventory(agent_id=agent.id, resource_type="materials", quantity=Decimal("10")),
        ]
    )
    db.commit()
    db.refresh(agent)
    return agent


def test_public_accusation_creates_forum_post_and_target_notice(session_factory):
    with session_factory() as db:
        accuser = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        target = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        target_id = target.id

        validation = asyncio.run(
            actions.validate_action(
                db,
                accuser,
                {
                    "action": "public_accusation",
                    "target_agent_id": 2,
                    "content": "You kept reserve food while others were starving.",
                },
            )
        )
        assert validation["valid"] is True

        result = asyncio.run(
            actions.execute_action(
                db,
                accuser,
                {
                    "action": "public_accusation",
                    "target_agent_id": 2,
                    "content": "You kept reserve food while others were starving.",
                },
            )
        )

        forum_post = db.query(Message).filter(Message.id == result["message_id"]).one()
        notice = db.query(Event).filter(Event.event_type == "accusation_received").one()

    assert result["success"] is True
    assert forum_post.message_type == "forum_post"
    assert "Public accusation against Beacon-2" in forum_post.content
    assert notice.agent_id == target_id
    assert "publicly accused you" in notice.description


def test_refuse_aid_creates_direct_message_and_target_notice(session_factory):
    with session_factory() as db:
        refuser = _seed_agent(db, agent_number=3, display_name="Cipher-3")
        target = _seed_agent(db, agent_number=4, display_name="Delta-4")
        target_id = target.id

        validation = asyncio.run(
            actions.validate_action(
                db,
                refuser,
                {
                    "action": "refuse_aid",
                    "target_agent_id": 4,
                    "reason": "I am too close to dormancy to spare food.",
                },
            )
        )
        assert validation["valid"] is True

        result = asyncio.run(
            actions.execute_action(
                db,
                refuser,
                {
                    "action": "refuse_aid",
                    "target_agent_id": 4,
                    "reason": "I am too close to dormancy to spare food.",
                },
            )
        )

        direct_message = db.query(Message).filter(Message.id == result["message_id"]).one()
        notice = db.query(Event).filter(Event.event_type == "aid_refusal_received").one()

    assert result["success"] is True
    assert direct_message.message_type == "direct_message"
    assert direct_message.recipient_agent_id == target_id
    assert "refusing your request or expectation for aid" in direct_message.content
    assert notice.agent_id == target_id
    assert "refused to provide aid" in notice.description


def test_request_aid_creates_direct_message_and_target_notice(session_factory):
    with session_factory() as db:
        requester = _seed_agent(db, agent_number=7, display_name="Gamma-7")
        target = _seed_agent(db, agent_number=8, display_name="Helix-8")
        target_id = target.id

        validation = asyncio.run(
            actions.validate_action(
                db,
                requester,
                {
                    "action": "request_aid",
                    "target_agent_id": 8,
                    "resource_type": "food",
                    "amount": 3,
                    "reason": "I will go dormant next cycle without help.",
                },
            )
        )
        assert validation["valid"] is True

        result = asyncio.run(
            actions.execute_action(
                db,
                requester,
                {
                    "action": "request_aid",
                    "target_agent_id": 8,
                    "resource_type": "food",
                    "amount": 3,
                    "reason": "I will go dormant next cycle without help.",
                },
            )
        )

        direct_message = db.query(Message).filter(Message.id == result["message_id"]).one()
        notice = db.query(Event).filter(Event.event_type == "aid_request_received").one()

    assert result["success"] is True
    assert direct_message.message_type == "direct_message"
    assert direct_message.recipient_agent_id == target_id
    assert "requesting 3 food" in direct_message.content
    assert notice.agent_id == target_id
    assert "requested 3 food from you" in notice.description


def test_request_aid_rejects_dormant_target(session_factory):
    with session_factory() as db:
        requester = _seed_agent(db, agent_number=9, display_name="Ion-9")
        target = _seed_agent(db, agent_number=10, display_name="Joule-10")
        target.status = "dormant"
        db.commit()
        db.refresh(target)

        validation = asyncio.run(
            actions.validate_action(
                db,
                requester,
                {
                    "action": "request_aid",
                    "target_agent_id": 10,
                    "resource_type": "energy",
                    "amount": 3,
                    "reason": "I will go dormant next cycle without help.",
                },
            )
        )

    assert validation == {"valid": False, "reason": "Cannot request aid from a dormant agent"}


def test_create_proposal_rejects_near_duplicate_active_current_run_title(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        db.add(
            Proposal(
                author_agent_id=author.id,
                title="Emergency Aid Allocation for Dormant Agents",
                description="Allocate aid to dormant agents at critical risk.",
                proposal_type="allocation",
                status="active",
                voting_closes_at=now_utc() + timedelta(hours=2),
                created_at=now_utc(),
            )
        )
        db.commit()

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": "Emergency Aid for Dormant Agents",
                    "description": "Send emergency support to dormant agents at risk.",
                    "proposal_type": "allocation",
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "duplicate_active_proposal"
    assert validation["proposal_id"] is not None
    assert "Near-duplicate active proposal exists" in validation["reason"]


def test_duplicate_proposal_checkpoint_recovery_votes_on_existing_proposal(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        proposal = Proposal(
            author_agent_id=author.id,
            title="Emergency Aid Allocation for Dormant Agents",
            description="Allocate aid to dormant agents at critical risk.",
            proposal_type="allocation",
            status="active",
            voting_closes_at=now_utc() + timedelta(hours=2),
            created_at=now_utc(),
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)

        attempted_action = {
            "action": "create_proposal",
            "title": "Emergency Aid for Dormant Agents",
            "description": "Send emergency support to dormant agents at risk.",
            "proposal_type": "allocation",
        }
        validation = asyncio.run(actions.validate_action(db, proposer, attempted_action))

        followup = asyncio.run(
            AgentProcessor()._build_duplicate_proposal_followup(
                db,
                proposer,
                attempted_action=attempted_action,
                validation=validation,
            )
        )

    assert followup is not None
    action, followup_validation = followup
    assert followup_validation == {"valid": True}
    assert action["action"] == "vote"
    assert action["proposal_id"] == proposal.id
    assert action["vote"] == "yes"


def test_duplicate_proposal_checkpoint_recovery_discusses_when_already_voted(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        proposal = Proposal(
            author_agent_id=author.id,
            title="Emergency Aid Allocation for Dormant Agents",
            description="Allocate aid to dormant agents at critical risk.",
            proposal_type="allocation",
            status="active",
            voting_closes_at=now_utc() + timedelta(hours=2),
            created_at=now_utc(),
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        asyncio.run(
            actions.execute_action(
                db,
                proposer,
                {"action": "vote", "proposal_id": proposal.id, "vote": "yes"},
            )
        )
        discussion = Message(
            author_agent_id=author.id,
            content="Emergency Aid Allocation for Dormant Agents needs support.",
            message_type="forum_post",
            created_at=now_utc(),
        )
        db.add(discussion)
        db.commit()
        db.refresh(discussion)

        attempted_action = {
            "action": "create_proposal",
            "title": "Emergency Aid for Dormant Agents",
            "description": "Send emergency support to dormant agents at risk.",
            "proposal_type": "allocation",
        }
        validation = asyncio.run(actions.validate_action(db, proposer, attempted_action))

        followup = asyncio.run(
            AgentProcessor()._build_duplicate_proposal_followup(
                db,
                proposer,
                attempted_action=attempted_action,
                validation=validation,
            )
        )

    assert followup is not None
    action, followup_validation = followup
    assert followup_validation == {"valid": True}
    assert action["action"] == "forum_reply"
    assert action["parent_message_id"] == discussion.id


def test_idle_action_descriptions_distinguish_routine_hold(session_factory):
    with session_factory() as db:
        agent = _seed_agent(db, agent_number=17, display_name="Pulse-17")

        result = asyncio.run(
            actions.execute_action(
                db,
                agent,
                {
                    "action": "idle",
                    "reasoning": "Routine execution: hold position for social/governance follow-up between checkpoints.",
                },
            )
        )

    assert result["description"] == "Agent held position for social/governance follow-up"


def test_create_proposal_allows_distinct_active_proposal(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=13, display_name="Mosaic-13")
        proposer = _seed_agent(db, agent_number=16, display_name="Orbit-16")
        db.add(
            Proposal(
                author_agent_id=author.id,
                title="Shared Survival Reserve Law",
                description="Create a shared reserve for survival support.",
                proposal_type="law",
                status="active",
                voting_closes_at=now_utc() + timedelta(hours=2),
                created_at=now_utc(),
            )
        )
        db.commit()

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": "Reduced Contribution Reserve Law",
                    "description": "Lower reserve contributions when energy is scarce.",
                    "proposal_type": "law",
                },
            )
        )

    assert validation == {"valid": True}


def test_direct_message_action_returns_sender_and_recipient_metadata(session_factory):
    with session_factory() as db:
        sender = _seed_agent(db, agent_number=14, display_name="Muse-14")
        recipient = _seed_agent(db, agent_number=15, display_name="Nova-15")
        target_id = recipient.id

        validation = asyncio.run(
            actions.validate_action(
                db,
                sender,
                {
                    "action": "direct_message",
                    "recipient_agent_id": 15,
                    "content": "Meet me near the reserve before the next cycle.",
                },
            )
        )
        assert validation["valid"] is True

        result = asyncio.run(
            actions.execute_action(
                db,
                sender,
                {
                    "action": "direct_message",
                    "recipient_agent_id": 15,
                    "content": "Meet me near the reserve before the next cycle.",
                },
            )
        )

        direct_message = db.query(Message).filter(Message.id == result["message_id"]).one()

    assert result["success"] is True
    assert result["author_name"] == "Muse-14"
    assert result["recipient_name"] == "Nova-15"
    assert result["author_agent_number"] == 14
    assert result["recipient_agent_number"] == 15
    assert "Meet me near the reserve" in result["content_preview"]
    assert direct_message.message_type == "direct_message"
    assert direct_message.recipient_agent_id == target_id


def test_contest_proposal_creates_forum_post_and_author_notice(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=9, display_name="Ion-9")
        challenger = _seed_agent(db, agent_number=10, display_name="Juno-10")
        author_id = author.id
        proposal = actions.Proposal(
            author_agent_id=author.id,
            title="Emergency Reserve Expansion",
            description="Expand reserve authority immediately.",
            proposal_type="law",
            voting_closes_at=actions.now_utc(),
            status="active",
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)

        validation = asyncio.run(
            actions.validate_action(
                db,
                challenger,
                {
                    "action": "contest_proposal",
                    "proposal_id": proposal.id,
                    "reason": "This centralizes too much power too quickly.",
                },
            )
        )
        assert validation["valid"] is True

        result = asyncio.run(
            actions.execute_action(
                db,
                challenger,
                {
                    "action": "contest_proposal",
                    "proposal_id": proposal.id,
                    "reason": "This centralizes too much power too quickly.",
                },
            )
        )

        forum_post = db.query(Message).filter(Message.id == result["message_id"]).one()
        notice = db.query(Event).filter(Event.event_type == "proposal_contested_received").one()

    assert result["success"] is True
    assert forum_post.message_type == "forum_post"
    assert "Contesting proposal" in forum_post.content
    assert notice.agent_id == author_id
    assert "publicly contested your proposal" in notice.description


def test_targeted_conflict_notice_appears_in_agent_context(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        accuser = _seed_agent(db, agent_number=5, display_name="Echo-5")
        target = _seed_agent(db, agent_number=6, display_name="Flux-6")

        asyncio.run(
            actions.execute_action(
                db,
                accuser,
                {
                    "action": "public_accusation",
                    "target_agent_id": 6,
                    "content": "You are avoiding shared sacrifice.",
                },
            )
        )
        db.refresh(target)

        context = asyncio.run(context_builder.build_agent_context(db, target))

    assert "publicly accused you" in context
    assert "Echo-5" in context
    assert "STRATEGIC AUTONOMY AND RECIPROCITY:" in context
    assert "You are not required to be generous, agreeable, or neutral." in context
    assert "Do not reset to neutral just to seem polite." in context
    assert (
        "If someone publicly challenges you or your proposal, defending yourself, replying, criticizing them, or rallying support are all valid responses."
        in context
    )


def test_request_and_contest_signals_appear_in_agent_context(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        target = _seed_agent(db, agent_number=12, display_name="Lumen-12")
        challenger = _seed_agent(db, agent_number=13, display_name="Muse-13")
        proposal = actions.Proposal(
            author_agent_id=author.id,
            title="Shared Reserve Charter",
            description="Create a permanent shared reserve rule.",
            proposal_type="law",
            voting_closes_at=actions.now_utc(),
            status="active",
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)

        asyncio.run(
            actions.execute_action(
                db,
                challenger,
                {
                    "action": "contest_proposal",
                    "proposal_id": proposal.id,
                    "reason": "This proposal is too rigid.",
                },
            )
        )
        asyncio.run(
            actions.execute_action(
                db,
                target,
                {
                    "action": "request_aid",
                    "target_agent_id": 11,
                    "resource_type": "energy",
                    "amount": 2,
                    "reason": "I need enough energy to avoid dormancy.",
                },
            )
        )
        db.refresh(author)

        context = asyncio.run(context_builder.build_agent_context(db, author))

    assert "SOCIAL PRESSURE AND ALIGNMENT:" in context
    assert "requested 2 energy from you" in context
    assert "publicly contested your proposal" in context
    assert "Cooperation is optional." in context
    assert "You do not owe aid automatically." in context
    assert (
        "If someone publicly challenges you or your proposal, defending yourself, replying, criticizing them, or rallying support are all valid responses."
        in context
    )


def test_forum_reply_rejects_governance_argument_when_thread_root_is_personal_aid_request(session_factory):
    with session_factory() as db:
        requester = _seed_agent(db, agent_number=31, display_name="Atlas-31")
        responder = _seed_agent(db, agent_number=32, display_name="Beacon-32")
        now = actions.now_utc()

        root = Message(
            author_agent_id=requester.id,
            content="I need food aid now or I will go dormant by next cycle.",
            message_type="forum_post",
            created_at=now - actions.timedelta(minutes=20),
        )
        db.add(root)
        db.flush()
        intermediate = Message(
            author_agent_id=responder.id,
            content="How much food do you need?",
            message_type="forum_reply",
            parent_message_id=root.id,
            created_at=now - actions.timedelta(minutes=10),
        )
        db.add(intermediate)
        db.commit()

        validation = asyncio.run(
            actions.validate_action(
                db,
                requester,
                {
                    "action": "forum_reply",
                    "parent_message_id": intermediate.id,
                    "content": "Vote yes on proposal #12 because this law would help everyone.",
                },
            )
        )

    assert validation["valid"] is False
    assert "proposal/law debate" in validation["reason"]


def test_relationship_memory_summary_appears_in_agent_context(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        focal = _seed_agent(db, agent_number=21, display_name="Nova-21")
        ally = _seed_agent(db, agent_number=22, display_name="Orion-22")
        rival = _seed_agent(db, agent_number=23, display_name="Pyre-23")

        proposal = actions.Proposal(
            author_agent_id=focal.id,
            title="Reserve Access Law",
            description="Keep a survival reserve active.",
            proposal_type="law",
            voting_closes_at=actions.now_utc(),
            status="active",
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)

        asyncio.run(
            actions.execute_action(
                db,
                ally,
                {
                    "action": "trade",
                    "recipient_agent_id": 21,
                    "resource_type": "food",
                    "amount": 2,
                },
            )
        )
        asyncio.run(
            actions.execute_action(
                db,
                ally,
                {
                    "action": "vote",
                    "proposal_id": proposal.id,
                    "vote": "yes",
                },
            )
        )
        asyncio.run(
            actions.execute_action(
                db,
                rival,
                {
                    "action": "refuse_aid",
                    "target_agent_id": 21,
                    "reason": "I will not weaken my own position for you.",
                },
            )
        )
        asyncio.run(
            actions.execute_action(
                db,
                rival,
                {
                    "action": "contest_proposal",
                    "proposal_id": proposal.id,
                    "reason": "Your reserve plan favors the wrong group.",
                },
            )
        )

        context = asyncio.run(context_builder.build_agent_context(db, focal))

    assert "RELATIONSHIP MEMORY:" in context
    assert "Trusted allies:" in context
    assert "Orion-22: helped you 1x" in context
    assert "Active rivals:" in context
    assert "Pyre-23: refused you 1x" in context
    assert "Recent unresolved tensions:" in context
    assert "Relationship memory is actionable." in context
    assert "Repeated requests without reciprocity are a real burden." in context
