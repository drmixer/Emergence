"""
Agents API Router
"""
from collections import defaultdict
from datetime import timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_

from app.core.database import get_db
from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, Event, Message, Proposal, Vote
from app.services.survival_config import (
    active_energy_cost,
    active_food_cost,
    death_threshold,
    dormant_energy_cost,
    dormant_food_cost,
    low_resource_warning_threshold,
)
from app.services.lineage import (
    lineage_map_for_season,
    lineage_payload_for_agent_number,
    resolve_active_or_latest_season_id,
)
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

router = APIRouter()

MEANINGFUL_ACTION_EVENT_TYPES = {
    "forum_post",
    "forum_reply",
    "direct_message",
    "create_proposal",
    "vote",
    "work",
    "trade",
    "vote_enforcement",
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
}
LEGIBILITY_WINDOW_HOURS = 72
LEGIBILITY_CONFLICT_EVENT_TYPES = {
    "enforcement_initiated",
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
    "agent_sanctioned",
    "resources_seized",
    "agent_exiled",
}
LEGIBILITY_POSITIVE_EVENT_TYPES = {
    "trade",
    "law_passed",
    "create_proposal",
    "work",
    "agent_revived",
    "awakened",
    "became_dormant",
}
RELATION_SIGNAL_LABELS = {
    "direct_message": ("direct message", "direct messages"),
    "forum_reply": ("forum reply", "forum replies"),
    "trade": ("trade", "trades"),
    "support_vote": ("supportive vote", "supportive votes"),
    "oppose_vote": ("opposition vote", "opposition votes"),
    "conflict": ("conflict action", "conflict actions"),
    "revival": ("revival", "revivals"),
}


class AgentResponse(BaseModel):
    id: int
    agent_number: int
    display_name: Optional[str]
    model_type: str
    tier: int
    personality_type: str
    status: str
    created_at: str
    last_active_at: str
    lineage_origin: Optional[str] = None
    lineage_is_carryover: bool = False
    lineage_is_fresh: bool = False
    lineage_parent_agent_number: Optional[int] = None
    lineage_season_id: Optional[str] = None
    legibility: dict = Field(default_factory=dict)
    
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class InventoryResponse(BaseModel):
    resource_type: str
    quantity: float
    
    model_config = ConfigDict(from_attributes=True)


class AgentDetailResponse(AgentResponse):
    inventory: List[InventoryResponse]
    profile_stats: dict
    lineage: dict


def _count_query(db: Session, model_field, *filters) -> int:
    value = db.query(func.count(model_field)).filter(*filters).scalar()
    return int(value or 0)


def _build_profile_stats(db: Session, *, agent: Agent) -> dict:
    total_actions = _count_query(db, Event.id, Event.agent_id == agent.id)
    meaningful_actions = _count_query(
        db,
        Event.id,
        Event.agent_id == agent.id,
        Event.event_type.in_(MEANINGFUL_ACTION_EVENT_TYPES),
    )
    invalid_actions = _count_query(
        db,
        Event.id,
        Event.agent_id == agent.id,
        Event.event_type == "invalid_action",
    )
    messages_authored = _count_query(db, Message.id, Message.author_agent_id == agent.id)
    proposals_created = _count_query(db, Proposal.id, Proposal.author_agent_id == agent.id)
    votes_cast = _count_query(db, Vote.id, Vote.agent_id == agent.id)
    laws_passed = _count_query(
        db,
        Event.id,
        Event.agent_id == agent.id,
        Event.event_type == "law_passed",
    )
    invalid_action_rate = (float(invalid_actions) / float(total_actions)) if total_actions > 0 else 0.0
    days_since_created = 0.0
    if agent.created_at is not None:
        created_at_value = agent.created_at
        current_time = now_utc()
        if getattr(created_at_value, "tzinfo", None) is None:
            current_time = current_time.replace(tzinfo=None)
        elapsed_seconds = (current_time - created_at_value).total_seconds()
        days_since_created = max(0.0, elapsed_seconds / 86400.0)

    return {
        "total_actions": int(total_actions),
        "meaningful_actions": int(meaningful_actions),
        "invalid_actions": int(invalid_actions),
        "invalid_action_rate": round(float(invalid_action_rate), 4),
        "messages_authored": int(messages_authored),
        "proposals_created": int(proposals_created),
        "votes_cast": int(votes_cast),
        "laws_passed": int(laws_passed),
        "days_since_created": round(float(days_since_created), 2),
    }


def _agent_public_label(agent: Agent | None) -> str:
    if agent is None:
        return "Unknown Agent"
    if agent.display_name:
        return str(agent.display_name)
    return f"Agent #{int(agent.agent_number):02d}"


def _signal_label(key: str, count: int) -> str:
    singular, plural = RELATION_SIGNAL_LABELS.get(key, (key.replace("_", " "), key.replace("_", " ") + "s"))
    label = singular if count == 1 else plural
    return f"{count} {label}"


def _relationship_title(kind: str, signals: dict[str, int]) -> str:
    lead_signal = ""
    lead_count = -1
    for signal_key, count in signals.items():
        if int(count) > lead_count:
            lead_signal = signal_key
            lead_count = int(count)

    if kind == "ally":
        if lead_signal == "trade":
            return "Trade partner"
        if lead_signal == "support_vote":
            return "Governance ally"
        if lead_signal == "revival":
            return "Revival backer"
        return "Frequent collaborator"

    if lead_signal == "conflict":
        return "Open rival"
    if lead_signal == "oppose_vote":
        return "Governance opponent"
    return "Recent opponent"


def _relationship_payload(
    *,
    target_agent: Agent | None,
    score: int,
    signals: dict[str, int],
    kind: str,
) -> dict | None:
    if target_agent is None or score <= 0:
        return None

    ordered_signals = sorted(
        ((str(key), int(value)) for key, value in signals.items() if int(value) > 0),
        key=lambda item: (-item[1], item[0]),
    )
    evidence = ", ".join(_signal_label(key, count) for key, count in ordered_signals[:2]) or "Recent interaction"
    return {
        "agent_number": int(target_agent.agent_number),
        "display_name": _agent_public_label(target_agent),
        "score": int(score),
        "relationship": _relationship_title(kind, signals),
        "evidence": evidence,
    }


def _coerce_agent_number(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _derive_archetype(agent: Agent, metrics: dict, danger_level: str) -> dict:
    governance = int(metrics.get("governance", 0))
    trade = int(metrics.get("trade", 0))
    communication = int(metrics.get("communication", 0))
    work = int(metrics.get("work", 0))
    conflict = int(metrics.get("conflict", 0))
    support = int(metrics.get("support", 0))

    if conflict >= max(governance, trade, communication, work, support) and conflict >= 2:
        return {
            "title": "Enforcer",
            "summary": "Recent behavior centers on sanctions, seizures, exile attempts, or other direct pressure.",
        }
    if governance >= max(trade, communication, work, conflict) and governance >= 2:
        return {
            "title": "Institution Builder",
            "summary": "Recent behavior is concentrated in proposals, votes, and other rule-shaping actions.",
        }
    if (trade + support) >= max(governance, communication, work, conflict) and (trade + support) >= 2:
        return {
            "title": "Broker",
            "summary": "Recent behavior is driven by trades, transfers, and other support moves between agents.",
        }
    if communication >= max(governance, trade, work, conflict) and communication >= 3:
        return {
            "title": "Coalition Voice",
            "summary": "Recent behavior is message-heavy, suggesting influence through conversation more than force.",
        }
    if work >= max(governance, trade, communication, conflict) and work >= 2:
        return {
            "title": "Producer",
            "summary": "Recent behavior is dominated by work and resource generation rather than politics or conflict.",
        }
    if danger_level == "critical":
        return {
            "title": "Survivor",
            "summary": "The current story is dominated by survival pressure rather than a stable strategic role.",
        }

    personality = str(agent.personality_type or "neutral")
    fallback_titles = {
        "efficiency": "Efficiency Strategist",
        "equality": "Mutual Aid Advocate",
        "freedom": "Autonomy Seeker",
        "stability": "Order Keeper",
        "neutral": "Generalist",
    }
    return {
        "title": fallback_titles.get(personality, "Generalist"),
        "summary": "Observed behavior is still mixed, so the public read is provisional rather than strongly specialized.",
    }


def _build_legibility_map(db: Session, *, agents: list[Agent]) -> dict[int, dict]:
    if not agents:
        return {}

    window_start = now_utc() - timedelta(hours=LEGIBILITY_WINDOW_HOURS)
    tracked_agent_ids = {int(agent.id) for agent in agents}
    tracked_agents_by_id = {int(agent.id): agent for agent in agents}

    all_agents = db.query(Agent).order_by(Agent.agent_number.asc()).all()
    agents_by_id = {int(agent.id): agent for agent in all_agents}
    agents_by_number = {int(agent.agent_number): agent for agent in all_agents}

    inventories = (
        db.query(AgentInventory)
        .filter(AgentInventory.agent_id.in_(tracked_agent_ids))
        .all()
    )
    inventory_by_agent_id: dict[int, dict[str, float]] = defaultdict(dict)
    for row in inventories:
        inventory_by_agent_id[int(row.agent_id)][str(row.resource_type)] = float(row.quantity or 0)

    messages = (
        db.query(Message)
        .filter(
            Message.created_at >= window_start,
            or_(
                Message.author_agent_id.in_(tracked_agent_ids),
                Message.recipient_agent_id.in_(tracked_agent_ids),
            ),
        )
        .all()
    )
    parent_message_ids = {
        int(message.parent_message_id)
        for message in messages
        if message.parent_message_id is not None
    }
    parent_messages = (
        db.query(Message)
        .filter(Message.id.in_(parent_message_ids))
        .all()
        if parent_message_ids
        else []
    )
    parent_author_by_message_id = {
        int(message.id): int(message.author_agent_id)
        for message in parent_messages
        if message.id is not None and message.author_agent_id is not None
    }

    event_types = LEGIBILITY_CONFLICT_EVENT_TYPES | LEGIBILITY_POSITIVE_EVENT_TYPES
    events = (
        db.query(Event)
        .filter(
            Event.created_at >= window_start,
            Event.agent_id.in_(tracked_agent_ids),
            Event.event_type.in_(event_types),
        )
        .all()
    )

    votes = (
        db.query(Vote)
        .filter(
            Vote.created_at >= window_start,
            Vote.agent_id.in_(tracked_agent_ids),
        )
        .all()
    )
    proposal_ids = {int(vote.proposal_id) for vote in votes if vote.proposal_id is not None}
    proposal_lookup = (
        {
            int(proposal.id): proposal
            for proposal in db.query(Proposal).filter(Proposal.id.in_(proposal_ids)).all()
        }
        if proposal_ids
        else {}
    )
    recent_authored_proposals = (
        db.query(Proposal)
        .filter(
            Proposal.created_at >= window_start,
            Proposal.author_agent_id.in_(tracked_agent_ids),
        )
        .all()
    )

    positive_scores: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    negative_scores: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    positive_signals: dict[int, dict[int, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    negative_signals: dict[int, dict[int, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    metrics_by_agent_id: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def _add_score(source_id: int | None, target_id: int | None, *, delta: int, signal: str, bucket: str) -> None:
        if source_id is None or target_id is None or source_id == target_id:
            return
        source_id = int(source_id)
        target_id = int(target_id)
        if source_id not in tracked_agent_ids:
            return
        if bucket == "positive":
            positive_scores[source_id][target_id] += int(delta)
            positive_signals[source_id][target_id][signal] += 1
        else:
            negative_scores[source_id][target_id] += int(delta)
            negative_signals[source_id][target_id][signal] += 1

    for message in messages:
        author_id = int(message.author_agent_id) if message.author_agent_id is not None else None
        recipient_id = int(message.recipient_agent_id) if message.recipient_agent_id is not None else None
        message_type = str(message.message_type or "")

        if author_id in tracked_agent_ids and message_type in {"direct_message", "forum_reply", "forum_post"}:
            metrics_by_agent_id[author_id]["communication"] += 1

        if message_type == "direct_message":
            _add_score(author_id, recipient_id, delta=3, signal="direct_message", bucket="positive")
            _add_score(recipient_id, author_id, delta=2, signal="direct_message", bucket="positive")
        elif message_type == "forum_reply":
            parent_author_id = parent_author_by_message_id.get(int(message.parent_message_id or 0))
            _add_score(author_id, parent_author_id, delta=2, signal="forum_reply", bucket="positive")
            _add_score(parent_author_id, author_id, delta=1, signal="forum_reply", bucket="positive")

    for event in events:
        actor_id = int(event.agent_id) if event.agent_id is not None else None
        event_type = str(event.event_type or "")
        metadata = event.event_metadata or {}
        action_meta = metadata.get("action") if isinstance(metadata.get("action"), dict) else {}

        if actor_id in tracked_agent_ids:
            if event_type == "trade":
                metrics_by_agent_id[actor_id]["trade"] += 1
            elif event_type in {"create_proposal", "law_passed"}:
                metrics_by_agent_id[actor_id]["governance"] += 1
            elif event_type == "work":
                metrics_by_agent_id[actor_id]["work"] += 1
            elif event_type in LEGIBILITY_CONFLICT_EVENT_TYPES:
                metrics_by_agent_id[actor_id]["conflict"] += 1

        if event_type == "trade":
            recipient_number = _coerce_agent_number(action_meta.get("recipient_agent_id") or metadata.get("recipient_agent_id"))
            recipient_agent = agents_by_number.get(int(recipient_number)) if recipient_number else None
            recipient_id = int(recipient_agent.id) if recipient_agent else None
            _add_score(actor_id, recipient_id, delta=4, signal="trade", bucket="positive")
            _add_score(recipient_id, actor_id, delta=2, signal="trade", bucket="positive")

        if event_type == "agent_revived":
            revived_by_number = _coerce_agent_number(metadata.get("revived_by"))
            revived_by_agent = agents_by_number.get(int(revived_by_number)) if revived_by_number else None
            revived_by_id = int(revived_by_agent.id) if revived_by_agent else None
            if revived_by_id in tracked_agent_ids:
                metrics_by_agent_id[revived_by_id]["support"] += 1
            _add_score(actor_id, revived_by_id, delta=4, signal="revival", bucket="positive")
            _add_score(revived_by_id, actor_id, delta=5, signal="revival", bucket="positive")

        if event_type in LEGIBILITY_CONFLICT_EVENT_TYPES:
            target_number = _coerce_agent_number(
                action_meta.get("target_agent_id")
                or metadata.get("target_agent")
                or metadata.get("target_agent_id")
            )
            target_agent = agents_by_number.get(int(target_number)) if target_number else None
            target_id = int(target_agent.id) if target_agent else None
            _add_score(actor_id, target_id, delta=5, signal="conflict", bucket="negative")
            _add_score(target_id, actor_id, delta=4, signal="conflict", bucket="negative")

    for proposal in recent_authored_proposals:
        author_id = int(proposal.author_agent_id)
        if author_id in tracked_agent_ids:
            metrics_by_agent_id[author_id]["governance"] += 1

    for vote in votes:
        voter_id = int(vote.agent_id)
        if voter_id in tracked_agent_ids:
            metrics_by_agent_id[voter_id]["governance"] += 1

        proposal = proposal_lookup.get(int(vote.proposal_id))
        if proposal is None:
            continue
        author_id = int(proposal.author_agent_id)
        if author_id == voter_id:
            continue
        if str(vote.vote or "") == "yes":
            _add_score(voter_id, author_id, delta=2, signal="support_vote", bucket="positive")
            _add_score(author_id, voter_id, delta=1, signal="support_vote", bucket="positive")
        elif str(vote.vote or "") == "no":
            _add_score(voter_id, author_id, delta=2, signal="oppose_vote", bucket="negative")
            _add_score(author_id, voter_id, delta=1, signal="oppose_vote", bucket="negative")

    active_food = active_food_cost()
    active_energy = active_energy_cost()
    dormant_food = dormant_food_cost()
    dormant_energy = dormant_energy_cost()
    low_food = low_resource_warning_threshold(active_food)
    low_energy = low_resource_warning_threshold(active_energy)
    death_limit = int(death_threshold())

    legibility_by_agent_id: dict[int, dict] = {}
    for agent_id, agent in tracked_agents_by_id.items():
        resources = inventory_by_agent_id.get(int(agent_id), {})
        food = float(resources.get("food", 0.0))
        energy = float(resources.get("energy", 0.0))
        incoming_pressure = sum(int(score) for score in negative_scores.get(int(agent_id), {}).values())

        danger_level = "stable"
        danger_label = "Stable"
        danger_reason = "Resource buffer is above immediate survival thresholds."

        if agent.status == "dead":
            danger_level = "deceased"
            danger_label = "Out"
            danger_reason = "This agent is no longer active in the run."
        elif agent.status == "dormant":
            cycles_left = max(0, death_limit - int(agent.starvation_cycles or 0))
            if int(agent.starvation_cycles or 0) > 0 or food < float(dormant_food) or energy < float(dormant_energy):
                danger_level = "critical"
                danger_label = "At Risk"
                danger_reason = f"Dormant and already starving, with {cycles_left} cycle(s) until permanent death."
            else:
                danger_level = "elevated"
                danger_label = "Dormant"
                danger_reason = "Dormant and dependent on outside support to return to active play."
        elif food < float(active_food) or energy < float(active_energy):
            danger_level = "critical"
            danger_label = "At Risk"
            danger_reason = "Current reserves do not clearly cover the next active survival cycle."
        elif food < float(low_food) or energy < float(low_energy):
            danger_level = "elevated"
            danger_label = "Exposed"
            danger_reason = "Reserves are thin enough that one bad cycle could trigger dormancy pressure."
        elif incoming_pressure >= 6:
            danger_level = "elevated"
            danger_label = "Pressured"
            danger_reason = "Recent conflict signals suggest they are under active pressure from other agents."

        metrics = metrics_by_agent_id.get(int(agent_id), {})
        archetype = _derive_archetype(agent, metrics, danger_level)

        positive_targets = sorted(
            positive_scores.get(int(agent_id), {}).items(),
            key=lambda item: (-int(item[1]), int(item[0])),
        )
        negative_targets = sorted(
            negative_scores.get(int(agent_id), {}).items(),
            key=lambda item: (-int(item[1]), int(item[0])),
        )

        allies = []
        for target_id, score in positive_targets[:2]:
            payload = _relationship_payload(
                target_agent=agents_by_id.get(int(target_id)),
                score=int(score),
                signals=dict(positive_signals[int(agent_id)][int(target_id)]),
                kind="ally",
            )
            if payload:
                allies.append(payload)

        rivals = []
        for target_id, score in negative_targets[:2]:
            payload = _relationship_payload(
                target_agent=agents_by_id.get(int(target_id)),
                score=int(score),
                signals=dict(negative_signals[int(agent_id)][int(target_id)]),
                kind="rival",
            )
            if payload:
                rivals.append(payload)

        legibility_by_agent_id[int(agent_id)] = {
            "archetype": archetype,
            "danger": {
                "level": danger_level,
                "label": danger_label,
                "reason": danger_reason,
                "food": round(float(food), 2),
                "energy": round(float(energy), 2),
            },
            "relationships": {
                "allies": allies,
                "rivals": rivals,
            },
            "derived_from_hours": LEGIBILITY_WINDOW_HOURS,
        }

    return legibility_by_agent_id


def _resolve_lineage_context(db: Session, *, agent_number: int) -> dict:
    current_season_id = resolve_active_or_latest_season_id(db)
    lineage_by_agent_number = lineage_map_for_season(db, season_id=current_season_id)
    payload = lineage_payload_for_agent_number(agent_number, lineage_by_agent_number)

    return {
        "current_season_id": current_season_id,
        "lineage_season_id": payload.get("lineage_season_id"),
        "origin": payload.get("lineage_origin"),
        "is_carryover": bool(payload.get("lineage_is_carryover")),
        "is_fresh": bool(payload.get("lineage_is_fresh")),
        "parent_agent_number": payload.get("lineage_parent_agent_number"),
    }


@router.get("", response_model=List[AgentResponse])
def list_agents(
    status: Optional[str] = None,
    tier: Optional[int] = None,
    model_type: Optional[str] = None,
    personality_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all agents with optional filters."""
    query = db.query(Agent)
    
    if status:
        query = query.filter(Agent.status == status)
    if tier:
        query = query.filter(Agent.tier == tier)
    if model_type:
        query = query.filter(Agent.model_type == model_type)
    if personality_type:
        query = query.filter(Agent.personality_type == personality_type)
    
    agents = query.order_by(Agent.agent_number).all()
    season_id = resolve_active_or_latest_season_id(db)
    lineage_by_agent_number = lineage_map_for_season(db, season_id=season_id)
    legibility_by_agent_id = _build_legibility_map(db, agents=agents)
    
    result: list[AgentResponse] = []
    for agent in agents:
        lineage = lineage_payload_for_agent_number(int(agent.agent_number), lineage_by_agent_number)
        result.append(
            AgentResponse(
                id=agent.id,
                agent_number=agent.agent_number,
                display_name=agent.display_name,
                model_type=agent.model_type,
                tier=agent.tier,
                personality_type=agent.personality_type,
                status=agent.status,
                created_at=agent.created_at.isoformat() if agent.created_at else "",
                last_active_at=agent.last_active_at.isoformat() if agent.last_active_at else "",
                lineage_origin=lineage.get("lineage_origin"),
                lineage_is_carryover=bool(lineage.get("lineage_is_carryover")),
                lineage_is_fresh=bool(lineage.get("lineage_is_fresh")),
                lineage_parent_agent_number=lineage.get("lineage_parent_agent_number"),
                lineage_season_id=lineage.get("lineage_season_id"),
                legibility=legibility_by_agent_id.get(int(agent.id), {}),
            )
        )
    return result


@router.get("/{agent_id}", response_model=AgentDetailResponse)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    """Get detailed agent information."""
    agent = db.query(Agent).filter(Agent.agent_number == agent_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    lineage = _resolve_lineage_context(db, agent_number=int(agent.agent_number))
    legibility_by_agent_id = _build_legibility_map(db, agents=[agent])
    detail_lineage_payload = {
        "lineage_origin": lineage.get("origin"),
        "lineage_is_carryover": bool(lineage.get("is_carryover")),
        "lineage_is_fresh": bool(lineage.get("is_fresh")),
        "lineage_parent_agent_number": lineage.get("parent_agent_number"),
        "lineage_season_id": lineage.get("lineage_season_id"),
    }
    
    inventory = db.query(AgentInventory).filter(
        AgentInventory.agent_id == agent.id
    ).all()
    
    return AgentDetailResponse(
        id=agent.id,
        agent_number=agent.agent_number,
        display_name=agent.display_name,
        model_type=agent.model_type,
        tier=agent.tier,
        personality_type=agent.personality_type,
        status=agent.status,
        created_at=agent.created_at.isoformat() if agent.created_at else "",
        last_active_at=agent.last_active_at.isoformat() if agent.last_active_at else "",
        lineage_origin=detail_lineage_payload.get("lineage_origin"),
        lineage_is_carryover=detail_lineage_payload.get("lineage_is_carryover"),
        lineage_is_fresh=detail_lineage_payload.get("lineage_is_fresh"),
        lineage_parent_agent_number=detail_lineage_payload.get("lineage_parent_agent_number"),
        lineage_season_id=detail_lineage_payload.get("lineage_season_id"),
        legibility=legibility_by_agent_id.get(int(agent.id), {}),
        inventory=[
            InventoryResponse(
                resource_type=inv.resource_type,
                quantity=float(inv.quantity)
            )
            for inv in inventory
        ],
        profile_stats=_build_profile_stats(db, agent=agent),
        lineage=_resolve_lineage_context(db, agent_number=int(agent.agent_number)),
    )


@router.get("/{agent_id}/actions")
def get_agent_actions(
    agent_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get agent's action history."""
    agent = db.query(Agent).filter(Agent.agent_number == agent_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    events = db.query(Event).filter(
        Event.agent_id == agent.id
    ).order_by(desc(Event.created_at)).limit(limit).all()
    
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "description": e.description,
            "metadata": e.event_metadata,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/{agent_id}/messages")
def get_agent_messages(
    agent_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get messages authored by agent."""
    agent = db.query(Agent).filter(Agent.agent_number == agent_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    messages = db.query(Message).filter(
        Message.author_agent_id == agent.id
    ).order_by(desc(Message.created_at)).limit(limit).all()
    
    return [
        {
            "id": m.id,
            "content": m.content,
            "message_type": m.message_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


@router.get("/{agent_id}/votes")
def get_agent_votes(
    agent_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get agent's voting history."""
    agent = db.query(Agent).filter(Agent.agent_number == agent_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    votes = db.query(Vote).filter(
        Vote.agent_id == agent.id
    ).order_by(desc(Vote.created_at)).limit(limit).all()
    
    return [
        {
            "id": v.id,
            "proposal_id": v.proposal_id,
            "vote": v.vote,
            "reasoning": v.reasoning,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in votes
    ]
