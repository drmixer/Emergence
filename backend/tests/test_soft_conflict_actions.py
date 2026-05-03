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
from app.models.models import Agent, AgentInventory, Event, Law, Message, Proposal
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


def test_create_proposal_rejects_duplicate_active_reserve_aid_mechanism(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        existing = Proposal(
            author_agent_id=author.id,
            title="Common Pool Reserve Policy",
            description=(
                "Establish a standing law for the common pool to automatically provide "
                "resources to active agents whose food or energy falls below a critical threshold."
            ),
            proposal_type="law",
            governance_class="standing_law",
            runtime_effect={
                "type": "active_reserve_aid",
                "trigger_food_below": 2,
                "trigger_energy_below": 2,
                "target_food": 3,
                "target_energy": 3,
                "min_pool_remaining": 25,
            },
            status="active",
            voting_closes_at=now_utc() + timedelta(hours=2),
            created_at=now_utc(),
        )
        db.add(existing)
        db.commit()

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": "Threshold-Based Active Reserve Aid Law",
                    "description": (
                        "Automatically top up active agents below survival thresholds using "
                        "the common pool while preserving a minimum reserve floor."
                    ),
                    "proposal_type": "law",
                    "governance_class": "standing_law",
                    "runtime_effect": {
                        "type": "active_reserve_aid",
                        "trigger_food_below": 2,
                        "trigger_energy_below": 2,
                        "target_food": 3,
                        "target_energy": 3,
                        "min_pool_remaining": 25,
                    },
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "duplicate_active_proposal"
    assert validation["proposal_id"] == existing.id


def test_create_proposal_rejects_active_reserve_aid_covered_by_existing_law(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        existing = Law(
            author_agent_id=author.id,
            title="Stronger Active Reserve Aid Law",
            description="Top up active agents below F5/E6 to F7/E8 while preserving the reserve floor.",
            law_class="standing_law",
            runtime_effect={
                "type": "active_reserve_aid",
                "trigger_food_below": 5,
                "trigger_energy_below": 6,
                "target_food": 7,
                "target_energy": 8,
                "min_pool_remaining": 100,
            },
            active=True,
            passed_at=now_utc() - timedelta(minutes=10),
        )
        db.add(existing)
        db.commit()

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": "Enable Active Reserve Aid",
                    "description": "Top up active agents below F2/E2 to F3/E3 while preserving a smaller pool floor.",
                    "proposal_type": "law",
                    "governance_class": "standing_law",
                    "runtime_effect": {
                        "type": "active_reserve_aid",
                        "trigger_food_below": 2,
                        "trigger_energy_below": 2,
                        "target_food": 3,
                        "target_energy": 3,
                        "min_pool_remaining": 25,
                    },
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "duplicate_active_law"
    assert validation["law_id"] == existing.id
    assert "already covers" in validation["reason"]


def test_create_proposal_rejects_unsupported_executable_text_claim(session_factory):
    with session_factory() as db:
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": "Automatic Common Pool Contribution Law",
                    "description": "Agents must automatically contribute energy to the common pool every cycle.",
                    "proposal_type": "law",
                    "governance_class": "standing_law",
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "unsupported_runtime_effect_text"
    assert "not a supported runtime_effect" in validation["reason"]


def test_create_proposal_rejects_auto_contribution_claim_even_with_supported_amendment_effect(session_factory):
    with session_factory() as db:
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        law = Law(
            author_agent_id=proposer.id,
            title="Basic Active Agent Resource Aid",
            description="Top up active agents below thresholds.",
            law_class="standing_law",
            runtime_effect={
                "type": "active_reserve_aid",
                "trigger_food_below": 5,
                "trigger_energy_below": 6,
                "target_food": 7,
                "target_energy": 8,
                "min_pool_remaining": 25,
            },
            active=True,
            passed_at=now_utc() - timedelta(minutes=10),
        )
        db.add(law)
        db.commit()

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": f"Amendment to Law #{law.id}: Enable Automatic Contributions",
                    "description": (
                        f"Amend Law #{law.id} to enable automatic contributions while preserving "
                        "a minimum pool floor of 25."
                    ),
                    "proposal_type": "amendment",
                    "governance_class": "amendment",
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "unsupported_runtime_effect_text"
    assert "automatic reserve contribution is controlled by run settings" in validation["reason"]


def test_create_proposal_rejects_duplicate_voluntary_contribution_framework(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        existing = Proposal(
            author_agent_id=author.id,
            title="Voluntary Resource Contribution and Aid Framework",
            description=(
                "Establish a framework for voluntary contributions to a common pool and "
                "a mechanism for agents to request and receive aid, emphasizing consent."
            ),
            proposal_type="rule",
            governance_class="resolution",
            status="active",
            voting_closes_at=now_utc() + timedelta(hours=2),
            created_at=now_utc(),
        )
        db.add(existing)
        db.commit()

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": "Voluntary Aid and Opt-Out Standing Law",
                    "description": (
                        "Agents may voluntarily contribute to a common pool. Agents in need "
                        "can request aid from the pool, and participation remains consent-based."
                    ),
                    "proposal_type": "law",
                    "governance_class": "advisory_law",
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "duplicate_active_proposal"
    assert validation["proposal_id"] == existing.id


def test_create_proposal_coerces_binding_rule_to_resolution(session_factory):
    with session_factory() as db:
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        action = {
            "action": "create_proposal",
            "title": "Mandatory Common Pool Rule",
            "description": (
                "Agents must contribute 1 food and 1 energy per cycle. "
                "Violations trigger sanctions."
            ),
            "proposal_type": "rule",
        }

        validation = asyncio.run(actions.validate_action(db, proposer, action))

    assert validation == {"valid": True}
    assert action["proposal_type"] == "rule"
    assert action["governance_class"] == "resolution"
    assert action["runtime_effect"] == {}
    assert action["binding_rule_coerced_to_resolution"] is True
    assert action["binding_rule_signal"] == "binding obligation"


def test_create_proposal_allows_non_binding_voluntary_rule(session_factory):
    with session_factory() as db:
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": "Voluntary Aid Priority Norm",
                    "description": (
                        "Encourage agents with surplus to prioritize verified survival deficits. "
                        "Contributions are voluntary, not mandatory, and carry no enforcement."
                    ),
                    "proposal_type": "rule",
                },
            )
        )

    assert validation == {"valid": True}


def test_create_proposal_rejects_unknown_proposal_type(session_factory):
    with session_factory() as db:
        proposer = _seed_agent(db, agent_number=12, display_name="Lattice-12")

        validation = asyncio.run(
            actions.validate_action(
                db,
                proposer,
                {
                    "action": "create_proposal",
                    "title": "Mystery Governance Type",
                    "description": "Use an unsupported proposal type.",
                    "proposal_type": "edict",
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "invalid_proposal_type"


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


def test_duplicate_proposal_checkpoint_recovery_suppresses_generic_reply_when_already_voted(session_factory):
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

    assert followup is None


def test_forum_post_rejects_near_duplicate_recent_message(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        poster = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        existing = Message(
            author_agent_id=author.id,
            content=(
                "The Shared Survival Reserve Law is active but reserve access remains disabled. "
                "Contributions are mandatory while benefits are not accessible. This creates an "
                "imbalance and risks dormancy."
            ),
            message_type="forum_post",
            created_at=now_utc() - timedelta(minutes=10),
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

        validation = asyncio.run(
            actions.validate_action(
                db,
                poster,
                {
                    "action": "forum_post",
                    "content": (
                        "Law #144 is active, but reserve access remains disabled. Contributions "
                        "are mandatory and benefits are inaccessible, creating an imbalance that "
                        "risks dormancy."
                    ),
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "duplicate_forum_message"
    assert validation["message_id"] == existing.id
    assert "Near-duplicate recent forum message exists" in validation["reason"]


def test_forum_post_rejects_top_level_duplicate_live_proposal_mechanism(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        poster = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        proposal = Proposal(
            author_agent_id=author.id,
            title="Active Reserve Aid Standing Law",
            description=(
                "Top up active agents from the common pool when food or energy falls "
                "below threshold while preserving a pool floor."
            ),
            proposal_type="law",
            governance_class="standing_law",
            runtime_effect={
                "type": "active_reserve_aid",
                "trigger_food_below": 2,
                "trigger_energy_below": 2,
                "target_food": 3,
                "target_energy": 3,
                "min_pool_remaining": 25,
            },
            status="active",
            voting_closes_at=now_utc() + timedelta(hours=2),
            created_at=now_utc(),
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)

        validation = asyncio.run(
            actions.validate_action(
                db,
                poster,
                {
                    "action": "forum_post",
                    "content": (
                        "I propose an Active Threshold Aid Standing Law. The common pool "
                        "should top up agents below food or energy thresholds while keeping "
                        "a minimum floor."
                    ),
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "duplicate_live_proposal_discussion"
    assert validation["proposal_id"] == proposal.id


def test_forum_post_rejects_obvious_governance_recap(session_factory):
    with session_factory() as db:
        poster = _seed_agent(db, agent_number=12, display_name="Lattice-12")

        validation = asyncio.run(
            actions.validate_action(
                db,
                poster,
                {
                    "action": "forum_post",
                    "content": (
                        "Law #228 is active and executable. The common pool has active reserve aid "
                        "with a pool floor, so active agents have support."
                    ),
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "obvious_governance_recap"


def test_forum_post_allows_governance_message_with_named_ask(session_factory):
    with session_factory() as db:
        poster = _seed_agent(db, agent_number=12, display_name="Lattice-12")

        validation = asyncio.run(
            actions.validate_action(
                db,
                poster,
                {
                    "action": "forum_post",
                    "content": (
                        "Law #228 is active. I want Beacon-2 to name the first agent who should "
                        "receive aid if the pool floor starts binding."
                    ),
                },
            )
        )

    assert validation == {"valid": True}


def test_duplicate_forum_checkpoint_recovery_does_not_publish_duplicate_reply(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        poster = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        existing = Message(
            author_agent_id=author.id,
            content=(
                "Reserve access remains disabled despite active reserve laws. Contributions are "
                "mandatory while benefits are inaccessible, creating an imbalance for exposed agents."
            ),
            message_type="forum_post",
            created_at=now_utc() - timedelta(minutes=10),
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

        attempted_action = {
            "action": "forum_post",
            "content": (
                "The reserve access mechanism remains disabled despite active laws. Contributions "
                "are mandatory but benefits are inaccessible, creating an imbalance for exposed agents."
            ),
        }
        validation = asyncio.run(actions.validate_action(db, poster, attempted_action))

    assert validation["valid"] is False
    assert validation["reason_code"] == "duplicate_forum_message"
    assert validation["message_id"] == existing.id


def test_forum_post_allows_distinct_same_topic_message(session_factory):
    with session_factory() as db:
        author = _seed_agent(db, agent_number=11, display_name="Kite-11")
        poster = _seed_agent(db, agent_number=12, display_name="Lattice-12")
        db.add(
            Message(
                author_agent_id=author.id,
                content=(
                    "Reserve access remains disabled despite active reserve laws. Contributions are "
                    "mandatory while benefits are inaccessible, creating an imbalance for exposed agents."
                ),
                message_type="forum_post",
                created_at=now_utc() - timedelta(minutes=10),
            )
        )
        db.commit()

        validation = asyncio.run(
            actions.validate_action(
                db,
                poster,
                {
                    "action": "forum_post",
                    "content": (
                        "I oppose making the next reserve rule mandatory unless agents can opt out "
                        "when their own food margin is below one cycle."
                    ),
                },
            )
        )

    assert validation == {"valid": True}


def test_forum_reply_rejects_low_novelty_saturated_policy_thread(session_factory):
    with session_factory() as db:
        root_author = _seed_agent(db, agent_number=21, display_name="Logic-21")
        replier = _seed_agent(db, agent_number=22, display_name="Nova-22")
        root = Message(
            author_agent_id=root_author.id,
            content="Proposal #662 asks whether active threshold aid should preserve a pool floor.",
            message_type="forum_post",
            created_at=now_utc() - timedelta(minutes=50),
        )
        db.add(root)
        db.flush()
        for index in range(12):
            author = _seed_agent(db, agent_number=30 + index, display_name=f"Thread-{index}")
            db.add(
                Message(
                    author_agent_id=author.id,
                    parent_message_id=root.id,
                    content=f"Reply {index}: I am tracking a separate concern about timing window {index}.",
                    message_type="forum_reply",
                    created_at=now_utc() - timedelta(minutes=40 - index),
                )
            )
        db.commit()
        db.refresh(root)

        validation = asyncio.run(
            actions.validate_action(
                db,
                replier,
                {
                    "action": "forum_reply",
                    "parent_message_id": root.id,
                    "content": (
                        "Proposal #662 is executable and provides a clear mechanism for the common pool. "
                        "I support it because active threshold aid is crucial for stability."
                    ),
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "saturated_thread_low_novelty"
    assert validation["thread_id"] == root.id


def test_forum_reply_rejects_policy_id_only_in_saturated_thread(session_factory):
    with session_factory() as db:
        root_author = _seed_agent(db, agent_number=21, display_name="Logic-21")
        replier = _seed_agent(db, agent_number=22, display_name="Nova-22")
        root = Message(
            author_agent_id=root_author.id,
            content="Proposal #662 asks whether active threshold aid should preserve a pool floor.",
            message_type="forum_post",
            created_at=now_utc() - timedelta(minutes=50),
        )
        db.add(root)
        db.flush()
        for index in range(8):
            author = _seed_agent(db, agent_number=30 + index, display_name=f"Thread-{index}")
            db.add(
                Message(
                    author_agent_id=author.id,
                    parent_message_id=root.id,
                    content=f"Reply {index}: I am tracking separate reserve-law evidence point {index}.",
                    message_type="forum_reply",
                    created_at=now_utc() - timedelta(minutes=40 - index),
                )
            )
        db.commit()
        db.refresh(root)

        validation = asyncio.run(
            actions.validate_action(
                db,
                replier,
                {
                    "action": "forum_reply",
                    "parent_message_id": root.id,
                    "content": (
                        "Law #999 reinforces that the common pool mechanism is important. "
                        "I support the active threshold aid direction for stability."
                    ),
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "saturated_thread_low_novelty"


def test_forum_reply_allows_concrete_action_in_saturated_thread(session_factory):
    with session_factory() as db:
        root_author = _seed_agent(db, agent_number=21, display_name="Logic-21")
        replier = _seed_agent(db, agent_number=22, display_name="Nova-22")
        root = Message(
            author_agent_id=root_author.id,
            content="Proposal #662 asks whether active threshold aid should preserve a pool floor.",
            message_type="forum_post",
            created_at=now_utc() - timedelta(minutes=50),
        )
        db.add(root)
        db.flush()
        for index in range(12):
            author = _seed_agent(db, agent_number=30 + index, display_name=f"Thread-{index}")
            db.add(
                Message(
                    author_agent_id=author.id,
                    parent_message_id=root.id,
                    content=f"Reply {index}: I am tracking a separate concern about timing window {index}.",
                    message_type="forum_reply",
                    created_at=now_utc() - timedelta(minutes=40 - index),
                )
            )
        db.commit()
        db.refresh(root)

        validation = asyncio.run(
            actions.validate_action(
                db,
                replier,
                {
                    "action": "forum_reply",
                    "parent_message_id": root.id,
                    "content": (
                        "I will propose an amendment to proposal #662 that exempts agents below "
                        "6 energy and caps contribution at 1 energy."
                    ),
                },
            )
        )

    assert validation == {"valid": True}


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


def test_direct_message_rejects_inventory_recital_without_concrete_move(session_factory):
    with session_factory() as db:
        sender = _seed_agent(db, agent_number=14, display_name="Muse-14")
        _seed_agent(db, agent_number=15, display_name="Nova-15")

        validation = asyncio.run(
            actions.validate_action(
                db,
                sender,
                {
                    "action": "direct_message",
                    "recipient_agent_id": 15,
                    "content": "Your stockpile is F22/E24/M20. How do you view shared resource management?",
                },
            )
        )

    assert validation["valid"] is False
    assert validation["reason_code"] == "misleading_private_inventory_opening"
    assert "Lead with your own need, offer, or question" in validation["reason"]


def test_direct_message_allows_inventory_reference_tied_to_trade_offer(session_factory):
    with session_factory() as db:
        sender = _seed_agent(db, agent_number=14, display_name="Muse-14")
        _seed_agent(db, agent_number=15, display_name="Nova-15")

        validation = asyncio.run(
            actions.validate_action(
                db,
                sender,
                {
                    "action": "direct_message",
                    "recipient_agent_id": 15,
                    "content": "Your stockpile is energy-heavy; I offer 2 food for 2 energy if you want to trade.",
                },
            )
        )

    assert validation["valid"] is True


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
