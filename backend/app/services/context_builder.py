"""
Context Builder - Builds the prompt context for agent decisions.
"""
from collections import Counter
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from app.core.config import settings
from app.core.time import ensure_utc, now_utc
from app.models.models import Agent, AgentInventory, Message, Proposal, Law, Event, Vote, GlobalResources, AgentRelationshipMemory
from app.services.agent_memory import agent_memory_service
from app.services.actions import get_action_rate_limit_state
from app.services.aid_lifecycle import classify_aid_request_event
from app.services.executable_governance import governance_payload_for_law, governance_payload_for_proposal
from app.services.law_effects import is_survival_reserve_law
from app.services.relationship_memory import RelationshipSummary, relationship_memory_service
from app.services.live_run_scope import LiveRunWindow, apply_live_run_window, get_live_run_window
from app.services.survival_config import (
    active_energy_cost,
    active_food_cost,
    death_threshold,
    dormant_energy_cost,
    dormant_food_cost,
    low_resource_warning_threshold,
    reserve_active_aid_min_pool_remaining,
    reserve_active_aid_target_energy,
    reserve_active_aid_target_food,
    reserve_active_aid_enabled,
    reserve_active_aid_trigger_energy,
    reserve_active_aid_trigger_food,
    reserve_auto_contribution_enabled,
    reserve_auto_revive_enabled,
    reserve_dormant_maintenance_enabled,
)


FORUM_THREAD_SAMPLE_LIMIT = 16
FORUM_THREAD_CONTEXT_LIMIT = 4
FORUM_THREAD_REPLY_LIMIT = 3
SYSTEM_ALERT_CONTEXT_LIMIT = 3
DIRECT_MESSAGE_SAMPLE_LIMIT = 16
DIRECT_CONVERSATION_LIMIT = 3
DIRECT_CONVERSATION_MESSAGE_LIMIT = 4
SOCIAL_SIGNAL_CONTEXT_LIMIT = 4
INCOMING_AID_REQUEST_CONTEXT_LIMIT = 4
PROPOSAL_ALIGNMENT_LIMIT = 4
MESSAGE_PREVIEW_LIMIT = 220


def _empty_relationship_summary() -> RelationshipSummary:
    return RelationshipSummary(
        trusted_allies=[],
        unreliable_contacts=[],
        active_rivals=[],
        recent_tensions=[],
    )


def _preview_untrusted_text(text: str | None, limit: int = MESSAGE_PREVIEW_LIMIT) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) > limit:
        return normalized[:limit] + "..."
    return normalized


def _agent_public_label(agent: Agent | None) -> str:
    if agent is None:
        return "Unknown agent"
    if agent.display_name:
        return f"{agent.display_name} (#{agent.agent_number})"
    return f"Agent #{agent.agent_number}"


def _format_time_remaining(target_at, *, now) -> str:
    deadline = ensure_utc(target_at) or now
    minutes_left = max(0, int((deadline - now).total_seconds() / 60))
    hours_left = minutes_left // 60
    remaining_minutes = minutes_left % 60
    if hours_left > 0:
        return f"{hours_left}h {remaining_minutes}m"
    return f"{minutes_left}m"


def _shared_problem_line(
    *,
    total_active: int,
    total_dormant: int,
    common_pool: dict[str, float],
) -> str:
    collective_food_upkeep = (total_active * float(active_food_cost())) + (
        total_dormant * float(dormant_food_cost())
    )
    collective_energy_upkeep = (total_active * float(active_energy_cost())) + (
        total_dormant * float(dormant_energy_cost())
    )
    food_gap = max(0.0, collective_food_upkeep - float(common_pool.get("food", 0.0)))
    energy_gap = max(0.0, collective_energy_upkeep - float(common_pool.get("energy", 0.0)))

    if food_gap > 0 or energy_gap > 0:
        return (
            "- Shared problem - Visible upkeep gap: if the common pool alone had to cover one cycle right "
            f"now, it would be short {food_gap:.1f} food and {energy_gap:.1f} energy for "
            f"{total_active} active + {total_dormant} dormant agents."
        )
    if total_dormant > 0:
        return (
            "- Shared problem - Recovery coordination gap: the visible common pool could cover one upkeep "
            f"cycle, but {total_dormant} dormant agents still need explicit aid, trade, or policy help."
        )
    return (
        "- Shared problem - Survival coordination question: the visible common pool could cover one upkeep "
        "cycle, so the live question is who contributes, who draws, and under what rule."
    )


def _public_actor_snapshot(
    db: Session,
    *,
    now,
    perception_cutoff=None,
    run_window: LiveRunWindow | None = None,
) -> list[str]:
    living_agents = (
        db.query(Agent)
        .filter(Agent.status.in_(["active", "dormant"]))
        .order_by(Agent.agent_number.asc())
        .all()
    )
    if not living_agents:
        return [
            "- Largest visible resource buffers: none visible.",
            "- Most exposed agents: none visible.",
            "- Governance focal point: no living agents remain.",
        ]

    inventories = (
        db.query(AgentInventory)
        .filter(AgentInventory.agent_id.in_([agent.id for agent in living_agents]))
        .all()
    )
    inventory_by_agent_id: dict[int, dict[str, float]] = {
        int(agent.id): {"food": 0.0, "energy": 0.0, "materials": 0.0}
        for agent in living_agents
    }
    for row in inventories:
        inventory_by_agent_id[int(row.agent_id)][str(row.resource_type)] = float(row.quantity or 0.0)

    living_snapshots = []
    critical_food = float(active_food_cost())
    critical_energy = float(active_energy_cost())
    low_food = float(low_resource_warning_threshold(active_food_cost()))
    low_energy = float(low_resource_warning_threshold(active_energy_cost()))

    for living_agent in living_agents:
        resources = inventory_by_agent_id.get(int(living_agent.id), {"food": 0.0, "energy": 0.0, "materials": 0.0})
        food = float(resources.get("food", 0.0))
        energy = float(resources.get("energy", 0.0))
        materials = float(resources.get("materials", 0.0))
        total_resources = food + energy + materials

        if living_agent.status == "dormant" and int(living_agent.starvation_cycles or 0) > 0:
            risk_band = 0
        elif living_agent.status == "active" and (food < critical_food or energy < critical_energy):
            risk_band = 1
        elif living_agent.status == "dormant":
            risk_band = 2
        elif food < low_food or energy < low_energy:
            risk_band = 3
        else:
            risk_band = 4

        living_snapshots.append(
            {
                "agent": living_agent,
                "food": food,
                "energy": energy,
                "materials": materials,
                "total_resources": total_resources,
                "risk_band": risk_band,
            }
        )

    strongest_candidates = [item for item in living_snapshots if item["agent"].status == "active"] or living_snapshots
    strongest = sorted(
        strongest_candidates,
        key=lambda item: (-item["total_resources"], item["agent"].agent_number),
    )[:3]
    strongest_line = "; ".join(
        f"{_agent_public_label(item['agent'])} {item['agent'].status}, "
        f"F{item['food']:.1f}/E{item['energy']:.1f}/M{item['materials']:.1f}"
        for item in strongest
    )

    exposed_candidates = [item for item in living_snapshots if item["risk_band"] < 4]
    if exposed_candidates:
        most_exposed = sorted(
            exposed_candidates,
            key=lambda item: (
                item["risk_band"],
                item["food"] + item["energy"],
                item["materials"],
                item["agent"].agent_number,
            ),
        )[:3]
        exposed_line = "; ".join(
            (
                f"{_agent_public_label(item['agent'])} {item['agent'].status}, "
                f"starvation={int(item['agent'].starvation_cycles or 0)}, "
                f"F{item['food']:.1f}/E{item['energy']:.1f}"
            )
            for item in most_exposed
        )
    else:
        lowest_buffers = sorted(
            [item for item in living_snapshots if item["agent"].status == "active"],
            key=lambda item: (item["food"] + item["energy"], item["materials"], item["agent"].agent_number),
        )[:2]
        lowest_line = "; ".join(
            f"{_agent_public_label(item['agent'])} F{item['food']:.1f}/E{item['energy']:.1f}"
            for item in lowest_buffers
        )
        exposed_line = (
            "none below warning thresholds "
            f"(active dormancy costs F{critical_food:.1f}/E{critical_energy:.1f}; "
            f"low-warning below F{low_food:.1f}/E{low_energy:.1f}). "
            f"Lowest visible active buffers, not critical: {lowest_line}"
        )

    recent_proposals_q = db.query(Proposal).filter(Proposal.created_at > now - timedelta(hours=24))
    recent_proposals_q = _apply_run_window_if_available(recent_proposals_q, Proposal.created_at, run_window)
    if perception_cutoff is not None:
        recent_proposals_q = recent_proposals_q.filter(Proposal.created_at <= perception_cutoff)
    recent_proposals = recent_proposals_q.order_by(desc(Proposal.created_at)).limit(8).all()

    contested_proposal = next(
        iter(
            sorted(
                [proposal for proposal in recent_proposals if int(proposal.votes_against or 0) > 0],
                key=lambda proposal: (
                    -int(proposal.votes_against or 0),
                    -(ensure_utc(proposal.created_at).timestamp() if ensure_utc(proposal.created_at) else 0.0),
                ),
            )
        ),
        None,
    )
    latest_proposal = recent_proposals[0] if recent_proposals else None

    if contested_proposal is not None:
        governance_line = (
            f"- Governance focal point: proposal #{contested_proposal.id} "
            f"\"{contested_proposal.title}\" by {_agent_public_label(contested_proposal.author)} "
            f"has {int(contested_proposal.votes_against or 0)} no votes and closes in "
            f"{_format_time_remaining(contested_proposal.voting_closes_at, now=now)}."
        )
    elif latest_proposal is not None:
        governance_line = (
            f"- Governance focal point: latest proposal #{latest_proposal.id} "
            f"\"{latest_proposal.title}\" by {_agent_public_label(latest_proposal.author)} closes in "
            f"{_format_time_remaining(latest_proposal.voting_closes_at, now=now)}."
        )
    else:
        governance_line = "- Governance focal point: no proposal has been introduced in the last 24 hours."

    return [
        f"- Largest visible resource buffers: {strongest_line}",
        f"- Most exposed agents: {exposed_line}",
        governance_line,
    ]


def _message_author_label(message: Message) -> str:
    if message.author and message.author.display_name:
        return message.author.display_name
    return f"Agent #{message.author_agent_id}"


def _message_time_label(message: Message) -> str:
    created_at = ensure_utc(message.created_at)
    return created_at.strftime("%H:%M") if created_at else "??:??"


def _apply_run_window_if_available(query, column, run_window: LiveRunWindow | None):
    if run_window is None:
        return query
    return apply_live_run_window(query, column, run_window)


def _thread_root_message(
    db: Session,
    message: Message,
    cache: dict[int, Message],
    *,
    run_window: LiveRunWindow | None = None,
) -> Message:
    cached = cache.get(message.id)
    if cached is not None:
        return cached

    current = message
    lineage: list[int] = [message.id]
    while current.parent_message_id is not None:
        parent_cached = cache.get(current.parent_message_id)
        if parent_cached is not None:
            current = parent_cached
            break
        parent = db.query(Message).filter(Message.id == current.parent_message_id).first()
        if parent is None:
            break
        parent_created_at = ensure_utc(parent.created_at)
        if run_window is not None and run_window.started_at is not None:
            if parent_created_at is None or parent_created_at < run_window.started_at:
                break
        if run_window is not None and run_window.ended_at is not None:
            if parent_created_at is not None and parent_created_at > run_window.ended_at:
                break
        current = parent
        lineage.append(current.id)

    for message_id in lineage:
        cache[message_id] = current
    cache[current.id] = current
    return current


def _load_thread_messages(
    db: Session,
    root_message: Message,
    *,
    perception_cutoff=None,
    run_window: LiveRunWindow | None = None,
    max_nodes: int = 24,
) -> list[Message]:
    seen_ids = {root_message.id}
    ordered_messages = [root_message]
    frontier = [root_message.id]

    while frontier and len(ordered_messages) < max_nodes:
        query = db.query(Message).filter(Message.parent_message_id.in_(frontier))
        query = _apply_run_window_if_available(query, Message.created_at, run_window)
        if perception_cutoff is not None:
            query = query.filter(Message.created_at <= perception_cutoff)
        batch = query.order_by(Message.created_at.asc(), Message.id.asc()).all()
        frontier = []
        for message in batch:
            if message.id in seen_ids:
                continue
            seen_ids.add(message.id)
            ordered_messages.append(message)
            frontier.append(message.id)
            if len(ordered_messages) >= max_nodes:
                break

    ordered_messages.sort(
        key=lambda message: (
            ensure_utc(message.created_at).timestamp() if ensure_utc(message.created_at) else 0.0,
            message.id,
        )
    )
    return ordered_messages


def _recent_forum_threads(db: Session, *, perception_cutoff=None, run_window: LiveRunWindow | None = None) -> list[dict]:
    query = db.query(Message).filter(Message.message_type.in_(["forum_post", "forum_reply"]))
    query = _apply_run_window_if_available(query, Message.created_at, run_window)
    if perception_cutoff is not None:
        query = query.filter(Message.created_at <= perception_cutoff)
    recent_messages = query.order_by(desc(Message.created_at)).limit(FORUM_THREAD_SAMPLE_LIMIT).all()

    thread_roots: dict[int, dict] = {}
    root_cache: dict[int, Message] = {}
    for message in recent_messages:
        root = _thread_root_message(db, message, root_cache, run_window=run_window)
        latest_at = ensure_utc(message.created_at) or ensure_utc(root.created_at)
        existing = thread_roots.get(root.id)
        if existing is None or (latest_at and latest_at > existing["latest_at"]):
            thread_roots[root.id] = {
                "root": root,
                "latest_at": latest_at,
            }

    selected_threads = sorted(
        thread_roots.values(),
        key=lambda item: (item["latest_at"].timestamp() if item["latest_at"] else 0.0, item["root"].id),
        reverse=True,
    )[:FORUM_THREAD_CONTEXT_LIMIT]

    thread_context = []
    for thread in selected_threads:
        root = thread["root"]
        thread_messages = _load_thread_messages(
            db,
            root,
            perception_cutoff=perception_cutoff,
            run_window=run_window,
        )
        replies = [message for message in thread_messages if message.id != root.id][-FORUM_THREAD_REPLY_LIMIT:]
        thread_context.append(
            {
                "root": root,
                "replies": replies,
                "latest_at": thread["latest_at"],
            }
        )
    return thread_context


def _recent_system_alerts(db: Session, *, perception_cutoff=None, run_window: LiveRunWindow | None = None) -> list[Message]:
    query = db.query(Message).filter(Message.message_type == "system_alert")
    query = _apply_run_window_if_available(query, Message.created_at, run_window)
    if perception_cutoff is not None:
        query = query.filter(Message.created_at <= perception_cutoff)
    return query.order_by(desc(Message.created_at)).limit(SYSTEM_ALERT_CONTEXT_LIMIT).all()


def _recent_direct_conversations(
    db: Session,
    agent: Agent,
    *,
    now,
    perception_cutoff=None,
    run_window: LiveRunWindow | None = None,
) -> list[dict]:
    query = db.query(Message).filter(
        Message.message_type == "direct_message",
        Message.created_at > now - timedelta(hours=24),
        or_(
            Message.author_agent_id == agent.id,
            Message.recipient_agent_id == agent.id,
        ),
    )
    query = _apply_run_window_if_available(query, Message.created_at, run_window)
    if perception_cutoff is not None:
        query = query.filter(Message.created_at <= perception_cutoff)
    recent_messages = query.order_by(desc(Message.created_at)).limit(DIRECT_MESSAGE_SAMPLE_LIMIT).all()

    conversations: dict[int, dict] = {}
    for message in recent_messages:
        counterpart = message.recipient if message.author_agent_id == agent.id else message.author
        if counterpart is None:
            continue
        counterpart_id = int(counterpart.id)
        latest_at = ensure_utc(message.created_at)
        conversation = conversations.setdefault(
            counterpart_id,
            {
                "counterpart": counterpart,
                "messages": [],
                "latest_at": latest_at,
            },
        )
        conversation["messages"].append(message)
        if latest_at and (conversation["latest_at"] is None or latest_at > conversation["latest_at"]):
            conversation["latest_at"] = latest_at

    selected_conversations = sorted(
        conversations.values(),
        key=lambda item: (item["latest_at"].timestamp() if item["latest_at"] else 0.0, item["counterpart"].id),
        reverse=True,
    )[:DIRECT_CONVERSATION_LIMIT]

    for conversation in selected_conversations:
        conversation["messages"] = sorted(
            conversation["messages"],
            key=lambda message: (
                ensure_utc(message.created_at).timestamp() if ensure_utc(message.created_at) else 0.0,
                message.id,
            ),
        )[-DIRECT_CONVERSATION_MESSAGE_LIMIT:]
    return selected_conversations


def _recent_social_pressure_events(
    db: Session,
    agent: Agent,
    *,
    now,
    perception_cutoff=None,
    run_window: LiveRunWindow | None = None,
) -> list[Event]:
    query = db.query(Event).filter(
        Event.agent_id == agent.id,
        Event.event_type.in_(
            [
                "accusation_received",
                "aid_request_received",
                "aid_refusal_received",
                "proposal_contested_received",
            ]
        ),
        Event.created_at > now - timedelta(hours=24),
    )
    query = _apply_run_window_if_available(query, Event.created_at, run_window)
    if perception_cutoff is not None:
        query = query.filter(Event.created_at <= perception_cutoff)
    events = query.order_by(desc(Event.created_at)).limit(SOCIAL_SIGNAL_CONTEXT_LIMIT * 2).all()
    visible_events: list[Event] = []
    for event in events:
        if event.event_type == "aid_request_received":
            lifecycle = classify_aid_request_event(db, request_event=event, run_window=run_window)
            if lifecycle is not None and str(lifecycle.get("status") or "unresolved") != "unresolved":
                continue
        visible_events.append(event)
        if len(visible_events) >= SOCIAL_SIGNAL_CONTEXT_LIMIT:
            break
    return visible_events


def _recent_resolved_aid_requests_received(
    db: Session,
    agent: Agent,
    *,
    now,
    perception_cutoff=None,
    run_window: LiveRunWindow | None = None,
) -> list[dict]:
    query = db.query(Event).filter(
        Event.agent_id == agent.id,
        Event.event_type == "aid_request_received",
        Event.created_at > now - timedelta(hours=24),
    )
    query = _apply_run_window_if_available(query, Event.created_at, run_window)
    if perception_cutoff is not None:
        query = query.filter(Event.created_at <= perception_cutoff)

    resolved: list[dict] = []
    for event in query.order_by(desc(Event.created_at), desc(Event.id)).limit(20).all():
        lifecycle = classify_aid_request_event(db, request_event=event, run_window=run_window)
        if lifecycle is None:
            continue
        status = str(lifecycle.get("status") or "unresolved")
        if status == "unresolved":
            continue
        resolved.append(lifecycle)
        if len(resolved) >= SOCIAL_SIGNAL_CONTEXT_LIMIT:
            break
    return resolved


def _incoming_aid_request_inbox(
    db: Session,
    agent: Agent,
    *,
    now,
    perception_cutoff=None,
    run_window: LiveRunWindow | None = None,
) -> list[dict]:
    query = db.query(Event).filter(
        Event.agent_id == agent.id,
        Event.event_type == "aid_request_received",
        Event.created_at > now - timedelta(hours=24),
    )
    query = _apply_run_window_if_available(query, Event.created_at, run_window)
    if perception_cutoff is not None:
        query = query.filter(Event.created_at <= perception_cutoff)
    events = query.order_by(desc(Event.created_at), desc(Event.id)).limit(INCOMING_AID_REQUEST_CONTEXT_LIMIT).all()

    inbox_entries: list[dict] = []
    for event in events:
        metadata = dict(event.event_metadata or {})
        requester_id = int(metadata.get("requesting_agent_id") or 0)
        if requester_id <= 0:
            continue
        requester = db.query(Agent).filter(Agent.id == requester_id).first()
        if requester is None:
            continue
        lifecycle = classify_aid_request_event(db, request_event=event, run_window=run_window)
        if lifecycle is not None and str(lifecycle.get("status") or "unresolved") != "unresolved":
            continue

        resource_type = str(metadata.get("resource_type") or "").strip().lower()
        try:
            requested_amount = float(metadata.get("amount") or 0.0)
        except (TypeError, ValueError):
            requested_amount = 0.0

        requester_inventory_rows = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == requester.id)
            .all()
        )
        requester_inventory = {"food": 0.0, "energy": 0.0, "materials": 0.0}
        for row in requester_inventory_rows:
            requester_inventory[str(row.resource_type)] = float(row.quantity or 0.0)

        requester_food = float(requester_inventory.get("food", 0.0))
        requester_energy = float(requester_inventory.get("energy", 0.0))
        would_keep_active = False
        if requester.status == "active":
            if resource_type == "food":
                would_keep_active = (
                    requester_energy >= float(active_energy_cost())
                    and requester_food + requested_amount >= float(active_food_cost())
                )
            elif resource_type == "energy":
                would_keep_active = (
                    requester_food >= float(active_food_cost())
                    and requester_energy + requested_amount >= float(active_energy_cost())
                )

        relationship_row = (
            db.query(AgentRelationshipMemory)
            .filter(
                AgentRelationshipMemory.agent_id == agent.id,
                AgentRelationshipMemory.other_agent_id == requester.id,
            )
            .first()
        )
        tie_labels: list[str] = []
        if relationship_row is not None:
            if (
                int(relationship_row.aid_received_from_other_count or 0) > 0
                or int(relationship_row.trade_received_from_other_count or 0) > 0
            ):
                tie_labels.append("prior helper")
            if int(relationship_row.proposal_supports_from_other_count or 0) > 0:
                tie_labels.append("supported your proposals")
            if int(relationship_row.proposal_supports_for_other_count or 0) > 0:
                tie_labels.append("you supported their proposals")
            if int(relationship_row.proposal_oppositions_from_other_count or 0) > 0:
                tie_labels.append("opposed your proposals")
            if int(relationship_row.aid_refusals_received_from_other_count or 0) > 0:
                tie_labels.append("refused you before")

        inbox_entries.append(
            {
                "requester": requester,
                "resource_type": resource_type,
                "requested_amount": requested_amount,
                "requester_food": requester_food,
                "requester_energy": requester_energy,
                "would_keep_active": would_keep_active,
                "tie_labels": tie_labels,
                "message_id": metadata.get("message_id"),
                "event": event,
            }
        )

    return inbox_entries


def _aid_request_has_refusal_response(
    db: Session,
    *,
    request_event: Event,
    responder: Agent,
    requester: Agent,
) -> bool:
    request_created_at = ensure_utc(request_event.created_at)
    if request_created_at is None:
        return False
    request_metadata = request_event.event_metadata if isinstance(request_event.event_metadata, dict) else {}
    request_message_id = request_metadata.get("message_id")
    query = db.query(Event).filter(
        Event.agent_id == requester.id,
        Event.event_type == "aid_refusal_received",
    )
    for event in query.order_by(desc(Event.created_at), desc(Event.id)).limit(25).all():
        event_created_at = ensure_utc(event.created_at)
        if event_created_at is not None and event_created_at < request_created_at:
            continue
        metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
        try:
            refusing_agent_id = int(metadata.get("refusing_agent_id") or 0)
            target_agent_id = int(metadata.get("target_agent_id") or 0)
        except (TypeError, ValueError):
            continue
        if refusing_agent_id != int(responder.id) or target_agent_id != int(requester.id):
            continue
        if request_message_id is None:
            return True
        if str(metadata.get("request_message_id") or "") == str(request_message_id):
            return True
        return True
    return False


def _recent_outgoing_social_actions(
    db: Session,
    agent: Agent,
    *,
    now,
    perception_cutoff=None,
    run_window: LiveRunWindow | None = None,
) -> list[Event]:
    query = db.query(Event).filter(
        Event.agent_id == agent.id,
        Event.event_type.in_(
            [
                "request_aid",
                "public_accusation",
                "refuse_aid",
                "contest_proposal",
            ]
        ),
        Event.created_at > now - timedelta(hours=24),
    )
    query = _apply_run_window_if_available(query, Event.created_at, run_window)
    if perception_cutoff is not None:
        query = query.filter(Event.created_at <= perception_cutoff)
    return query.order_by(desc(Event.created_at)).limit(SOCIAL_SIGNAL_CONTEXT_LIMIT).all()


def _recent_proposal_alignments(
    db: Session,
    agent: Agent,
    *,
    now,
    perception_cutoff=None,
    run_window: LiveRunWindow | None = None,
) -> dict[str, list[str]]:
    query = (
        db.query(Vote, Proposal, Agent)
        .join(Proposal, Proposal.id == Vote.proposal_id)
        .join(Agent, Agent.id == Vote.agent_id)
        .filter(
            Proposal.author_agent_id == agent.id,
            Vote.agent_id != agent.id,
            Vote.created_at > now - timedelta(hours=24),
            Vote.vote.in_(["yes", "no"]),
        )
    )
    query = _apply_run_window_if_available(query, Vote.created_at, run_window)
    if perception_cutoff is not None:
        query = query.filter(Vote.created_at <= perception_cutoff)

    allies: list[str] = []
    opponents: list[str] = []
    for vote, proposal, voter in query.order_by(desc(Vote.created_at)).limit(16).all():
        voter_name = voter.display_name or f"Agent #{voter.agent_number}"
        summary = f"{voter_name} voted {vote.vote} on your proposal \"{proposal.title}\""
        if vote.vote == "yes" and len(allies) < PROPOSAL_ALIGNMENT_LIMIT:
            allies.append(summary)
        elif vote.vote == "no" and len(opponents) < PROPOSAL_ALIGNMENT_LIMIT:
            opponents.append(summary)
    return {"allies": allies, "opponents": opponents}


def _strategic_autonomy_guidance(
    recent_social_pressure: list[Event],
    recent_outgoing_social_actions: list[Event],
    recent_proposal_alignments: dict[str, list[str]],
    relationship_summary,
) -> list[str]:
    incoming_types = {str(event.event_type or "").strip() for event in recent_social_pressure}
    outgoing_types = {str(event.event_type or "").strip() for event in recent_outgoing_social_actions}
    has_allies = bool(recent_proposal_alignments.get("allies"))
    has_opponents = bool(recent_proposal_alignments.get("opponents"))
    has_unreliable_contacts = bool(getattr(relationship_summary, "unreliable_contacts", []))
    has_active_rivals = bool(getattr(relationship_summary, "active_rivals", []))
    has_recent_tensions = bool(getattr(relationship_summary, "recent_tensions", []))

    guidance = [
        "You are not required to be generous, agreeable, or neutral.",
        "Protecting your own survival, preserving resources, favoring allies, and distrusting free riders are all legitimate choices.",
        "Cooperation is optional. If a request, proposal, or alliance would weaken you or shift unfair costs onto you, you may refuse it, criticize it, or organize against it.",
        "Reciprocity matters: past help, refusals, unequal burden-sharing, and repeated exploitation are valid reasons to change how you treat other agents.",
        "Selective cooperation is normal. You may help some agents, ignore others, and support policies that advantage your side.",
        "Do not reset to neutral just to seem polite. If another agent has imposed costs on you, refused you, or repeatedly opposed you, you may carry that forward into your next choice.",
    ]

    if "aid_request_received" in incoming_types:
        guidance.append(
            "You do not owe aid automatically. Refusing aid is legitimate if helping would endanger you, reward non-reciprocity, or impose an unfair burden."
        )
    if "aid_refusal_received" in incoming_types:
        guidance.append(
            "If someone refused you, that is evidence about trust and reciprocity. You may remember it, reduce future cooperation, or answer publicly."
        )
    if {"accusation_received", "proposal_contested_received"} & incoming_types:
        guidance.append(
            "If someone publicly challenges you or your proposal, defending yourself, replying, criticizing them, or rallying support are all valid responses."
        )
    if {"public_accusation", "contest_proposal", "refuse_aid"} & outgoing_types:
        guidance.append(
            "If you have already taken a side publicly, you may follow through consistently instead of acting as if the conflict never happened."
        )
    if has_allies or has_opponents:
        guidance.append(
            "Votes reveal alignment. You may reward allies, remember opponents, and treat repeated opposition as political rivalry."
        )
    if has_unreliable_contacts:
        guidance.append(
            "Repeated requests without reciprocity are a real burden. You may deprioritize unreliable contacts, deny them aid, or resist plans that favor them."
        )
    if has_active_rivals or has_recent_tensions:
        guidance.append(
            "Relationship memory is actionable. If someone is already a rival or recent source of tension, you may answer them directly, oppose their proposals, or refuse to help them instead of behaving as if each turn starts fresh."
        )

    return guidance


def _personality_attention_guidance(agent: Agent) -> list[str]:
    personality = str(agent.personality_type or "neutral").strip().lower()
    guidance_by_personality = {
        "efficiency": [
            "Efficiency lens: notice bottlenecks, waste, timing, quantities, and whether an action measurably changes survival odds.",
            "Communication style: concise, numeric, specific about costs, deficits, production, or execution steps.",
        ],
        "equality": [
            "Equality lens: notice uneven risk, neglected agents, burden sharing, and who receives help versus who pays.",
            "Communication style: concrete about affected agents, fairness tests, distribution, and mutual obligation.",
        ],
        "freedom": [
            "Freedom lens: notice coercion, opt-out problems, overcentralized authority, and voluntary alternatives.",
            "Communication style: explicit about autonomy costs, consent, amendments, and less coercive mechanisms.",
        ],
        "stability": [
            "Stability lens: notice enforceability, continuity, unresolved procedure, trust, and whether rules will survive future pressure.",
            "Communication style: name the proposal, risk, or agent you are answering; be concrete about implementation or verification without writing a status memo.",
        ],
        "neutral": [
            "Neutral lens: notice tradeoffs, missing information, bridging options, and where a question or summary can clarify the choice.",
            "Communication style: balanced, specific, and useful to agents who disagree.",
        ],
    }
    return guidance_by_personality.get(personality, guidance_by_personality["neutral"])


def _soft_action_type_prior_guidance(
    db: Session,
    agent: Agent,
    *,
    recent_events: list[Event],
    active_proposals: list[Proposal],
    incoming_aid_request_inbox: list[dict],
    direct_conversations: list[dict],
    recent_social_pressure: list[Event],
    total_dormant: int,
    starving_agents: list[Agent],
    food: float,
    energy: float,
    critical_food: float,
    critical_energy: float,
) -> list[str]:
    """Prompt-only attention priors. These do not alter allowed actions."""
    action_counts = Counter(str(event.event_type or "").strip() for event in recent_events)
    lines = [
        "These are prompt-only attention priors, not rules: choose a different valid action if the current evidence supports it.",
    ]
    if action_counts:
        summarized = ", ".join(
            f"{event_type}={count}"
            for event_type, count in sorted(action_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        )
        lines.append(f"Recent self action mix sample: {summarized}.")

    repeated_public_actions = [
        event_type
        for event_type in ("create_proposal", "forum_post")
        if int(action_counts.get(event_type, 0)) >= 2
    ]
    if repeated_public_actions:
        lines.append(
            "Because your recent public actions already include repeated "
            + "/".join(repeated_public_actions)
            + ", prefer vote, contest_proposal, forum_reply, trade, request_aid/refuse_aid, or direct_message unless a new public item adds concrete new evidence."
        )

    unvoted_active_count = 0
    for proposal in active_proposals:
        has_vote = (
            db.query(Vote)
            .filter(Vote.proposal_id == proposal.id, Vote.agent_id == agent.id)
            .first()
        )
        if has_vote is None:
            unvoted_active_count += 1
    if unvoted_active_count > 0:
        lines.append(
            f"{unvoted_active_count} active proposals are still awaiting your vote; voting or contesting is often higher signal than opening another broad proposal."
        )

    if incoming_aid_request_inbox:
        lines.append(
            "Incoming aid requests are pending; trade, refuse_aid, or a direct response should usually be considered before unrelated broadcast actions."
        )
    if direct_conversations or recent_social_pressure:
        lines.append(
            "Recent direct conversation or social pressure is visible; reply, direct_message, trade, refuse_aid, or contest_proposal may carry more continuity than a generic new post if you can change what someone does next."
        )
    if food < critical_food or energy < critical_energy:
        lines.append(
            "You are below active survival cost; work, trade, or request_aid should stay high in your attention unless a social action directly improves survival odds."
        )
    elif total_dormant > 0 or starving_agents:
        lines.append(
            "Dormancy pressure is visible; targeted aid, trade, specific policy work, or a concise coordination reply may be more useful than another general statement."
        )

    personality = str(agent.personality_type or "neutral").strip().lower()
    if personality == "efficiency":
        lines.append("Efficiency prior: favor actions with concrete quantities, execution steps, or measurable bottleneck relief.")
    elif personality == "equality":
        lines.append("Equality prior: favor actions that name affected agents, burden sharing, or concrete aid criteria.")
    elif personality == "freedom":
        lines.append("Freedom prior: favor consent, opt-out, contest_proposal, or voluntary trade/direct coordination when coercion is at stake.")
    elif personality == "stability":
        lines.append("Stability prior: favor vote, enforcement clarity, direct commitments, or specific implementation details.")
    else:
        lines.append("Neutral prior: favor the action that closes the clearest information gap or bridges an unresolved disagreement.")
    return lines


async def build_agent_context(db: Session, agent: Agent) -> str:
    """Build the context prompt for an agent's decision."""
    now = now_utc()
    perception_lag_seconds = max(0, int(getattr(settings, "PERCEPTION_LAG_SECONDS", 0) or 0))
    perception_cutoff = now - timedelta(seconds=perception_lag_seconds)
    live_run_window = get_live_run_window(db)
    if live_run_window.run_id is None:
        live_run_window = None
    
    # Get agent's inventory
    inventory = db.query(AgentInventory).filter(
        AgentInventory.agent_id == agent.id
    ).all()
    inventory_dict = {inv.resource_type: float(inv.quantity) for inv in inventory}
    
    recent_forum_threads = _recent_forum_threads(
        db,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )
    recent_system_alerts = _recent_system_alerts(
        db,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )
    
    # Get active proposals (keep small to reduce token usage)
    active_proposals_q = db.query(Proposal).filter(
        Proposal.status == "active"
    )
    active_proposals_q = _apply_run_window_if_available(active_proposals_q, Proposal.created_at, live_run_window)
    if perception_lag_seconds > 0:
        active_proposals_q = active_proposals_q.filter(Proposal.created_at <= perception_cutoff)
    active_proposals = active_proposals_q.order_by(desc(Proposal.created_at)).all()
    prioritized_active_proposals = sorted(
        active_proposals,
        key=lambda prop: (
            0 if str(getattr(prop, "proposal_type", "") or "").strip().lower() == "law" else 1,
            -(int(getattr(prop, "id", 0) or 0)),
        ),
    )

    run_messages_q = db.query(Message)
    run_messages_q = _apply_run_window_if_available(run_messages_q, Message.created_at, live_run_window)
    if perception_lag_seconds > 0:
        run_messages_q = run_messages_q.filter(Message.created_at <= perception_cutoff)
    total_run_messages = int(run_messages_q.count() or 0)
    total_forum_replies = int(run_messages_q.filter(Message.message_type == "forum_reply").count() or 0)
    total_direct_messages = int(run_messages_q.filter(Message.message_type == "direct_message").count() or 0)

    run_votes_q = db.query(Vote)
    run_votes_q = _apply_run_window_if_available(run_votes_q, Vote.created_at, live_run_window)
    if perception_lag_seconds > 0:
        run_votes_q = run_votes_q.filter(Vote.created_at <= perception_cutoff)
    total_run_votes = int(run_votes_q.count() or 0)
    social_silence_pressure = (
        total_run_messages < 6
        and total_run_votes + len(active_proposals) >= 4
    )
    
    # Get recent events affecting this agent
    recent_events_q = db.query(Event).filter(
        Event.agent_id == agent.id,
        Event.created_at > now - timedelta(hours=24)
    )
    recent_events_q = _apply_run_window_if_available(recent_events_q, Event.created_at, live_run_window)
    if perception_lag_seconds > 0:
        recent_events_q = recent_events_q.filter(Event.created_at <= perception_cutoff)
    recent_events_raw = recent_events_q.order_by(desc(Event.created_at), desc(Event.id)).limit(16).all()
    recent_events: list[Event] = []
    for event in recent_events_raw:
        if event.event_type == "aid_request_received":
            lifecycle = classify_aid_request_event(db, request_event=event, run_window=live_run_window)
            if lifecycle is not None and str(lifecycle.get("status") or "unresolved") != "unresolved":
                continue
        recent_events.append(event)
        if len(recent_events) >= 10:
            break

    recent_social_pressure = _recent_social_pressure_events(
        db,
        agent,
        now=now,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )
    incoming_aid_request_inbox = _incoming_aid_request_inbox(
        db,
        agent,
        now=now,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )
    recent_resolved_aid_requests = _recent_resolved_aid_requests_received(
        db,
        agent,
        now=now,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )
    recent_outgoing_social_actions = _recent_outgoing_social_actions(
        db,
        agent,
        now=now,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )
    recent_proposal_alignments = _recent_proposal_alignments(
        db,
        agent,
        now=now,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )
    
    direct_conversations = _recent_direct_conversations(
        db,
        agent,
        now=now,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )
    relationship_summary = (
        _empty_relationship_summary()
        if live_run_window is not None and live_run_window.started_at is not None
        else relationship_memory_service.summarize_for_agent(db, agent)
    )
    
    # Get active laws and recent law changes (keep small)
    active_laws_q = db.query(Law).filter(Law.active == True)
    recent_laws_q = db.query(Law).filter(Law.passed_at > now - timedelta(hours=24))
    active_laws_q = _apply_run_window_if_available(active_laws_q, Law.passed_at, live_run_window)
    recent_laws_q = _apply_run_window_if_available(recent_laws_q, Law.passed_at, live_run_window)
    if perception_lag_seconds > 0:
        active_laws_q = active_laws_q.filter(Law.passed_at <= perception_cutoff)
        recent_laws_q = recent_laws_q.filter(Law.passed_at <= perception_cutoff)
    active_laws = active_laws_q.order_by(desc(Law.passed_at)).limit(5).all()
    recent_laws = recent_laws_q.order_by(desc(Law.passed_at)).limit(3).all()
    reserve_laws = [law for law in active_laws if is_survival_reserve_law(law)]
    survival_reserve_law_active = bool(reserve_laws)

    global_resources = db.query(GlobalResources).all()
    common_pool = {str(item.resource_type): float(item.in_common_pool or 0) for item in global_resources}
    
    # Get global stats
    total_active = db.query(Agent).filter(Agent.status == "active").count()
    total_dormant = db.query(Agent).filter(Agent.status == "dormant").count()
    total_dead = db.query(Agent).filter(Agent.status == "dead").count()
    total_population = total_active + total_dormant + total_dead
    
    # Get recent deaths (for awareness)
    recent_deaths_q = db.query(Event).filter(
        Event.event_type == "agent_died",
        Event.created_at > now - timedelta(hours=48)
    )
    recent_deaths_q = _apply_run_window_if_available(recent_deaths_q, Event.created_at, live_run_window)
    if perception_lag_seconds > 0:
        recent_deaths_q = recent_deaths_q.filter(Event.created_at <= perception_cutoff)
    recent_deaths = recent_deaths_q.order_by(desc(Event.created_at)).limit(3).all()
    
    # Get agents at risk of death (starving dormant agents)
    starving_agents = db.query(Agent).filter(
        Agent.status == "dormant",
        Agent.starvation_cycles > 0
    ).all()

    recent_reserve_events_q = db.query(Event).filter(
        Event.event_type.in_(["reserve_aid", "reserve_shortfall"]),
        Event.created_at > now - timedelta(hours=24),
    )
    recent_reserve_events_q = _apply_run_window_if_available(recent_reserve_events_q, Event.created_at, live_run_window)
    if perception_lag_seconds > 0:
        recent_reserve_events_q = recent_reserve_events_q.filter(Event.created_at <= perception_cutoff)
    recent_reserve_events = recent_reserve_events_q.order_by(desc(Event.created_at)).limit(4).all()
    shared_problem_line = _shared_problem_line(
        total_active=total_active,
        total_dormant=total_dormant,
        common_pool=common_pool,
    )
    public_actor_snapshot_lines = _public_actor_snapshot(
        db,
        now=now,
        perception_cutoff=perception_cutoff if perception_lag_seconds > 0 else None,
        run_window=live_run_window,
    )

    proposal_hooks: list[str] = []
    recent_forum_activity_count = sum(
        1 + len(thread["replies"]) for thread in recent_forum_threads
    ) + len(recent_system_alerts)

    if not active_proposals:
        proposal_hooks.append(
            "There are no active proposals. Forum discussion alone does not create a vote; create_proposal is the only way to start one."
        )
    if recent_forum_activity_count and not active_proposals:
        proposal_hooks.append(
            f"There are {recent_forum_activity_count} recent public messages but no formal proposal. If you want collective action, turn discussion into a proposal."
        )
    if starving_agents:
        proposal_hooks.append(
            f"{len(starving_agents)} dormant agents have unpaid dormant upkeep cycles. An allocation or rule proposal could coordinate aid or recovery."
        )
        proposal_hooks.append(
            "If you want recurring aid, reserve access, or an ongoing obligation across future cycles, prefer proposal_type \"law\" instead of a one-off allocation."
        )
        proposal_hooks.append(
            "Before creating a new recovery allocation, check active proposals: if a similar allocation is already live, do not create a second near-identical allocation; vote, contest, or reply with an amendment instead."
        )
    if total_dormant > 0:
        proposal_hooks.append(
            f"{total_dormant} agents are dormant. A proposal could set shared priorities for recovery, aid, or production."
        )
    if recent_deaths:
        proposal_hooks.append(
            "Recent deaths make survival policy salient. You may propose new rules, allocations, or infrastructure in response."
        )
    if not active_laws:
        proposal_hooks.append(
            "No active laws exist yet. If you want durable shared rules, you must propose them explicitly."
        )
        proposal_hooks.append(
            "Shared reserve systems or recurring emergency aid usually need proposal_type \"law\" if you want them to become part of the live world state. Mandatory contribution text can create policy context, but not automatic reserve contribution unless that run-condition gate is already enabled."
        )
    else:
        proposal_hooks.append(
            "Active laws are part of the live world state. You may adapt your behavior, discuss them, propose changes, or cite a law_id in enforcement if you think someone is violating one."
        )
    if survival_reserve_law_active:
        if reserve_auto_contribution_enabled():
            proposal_hooks.append(
                "A survival-reserve law is active and automatic contributions are enabled: the bounded system preset diverts food and energy work output into the shared reserve."
            )
        else:
            proposal_hooks.append(
                "A survival-reserve law is active, but automatic contributions are disabled for this run; reserve policy still depends on direct aid, trade, voting, enforcement, or supported runtime effects that are already enabled."
            )
        if starving_agents:
            proposal_hooks.append(
                "The shared reserve is now part of survival politics: if it runs low while agents are starving, conflict over aid or production priorities may follow."
            )
    
    # Build context string
    context_parts = []
    
    # Header with day info (approximate based on start time)
    context_parts.append("CURRENT STATE:")
    context_parts.append("")
    
    # Agent status
    display_name = agent.display_name or f"Agent #{agent.agent_number}"
    context_parts.append("YOUR STATUS:")
    context_parts.append(f"- Agent ID: #{agent.agent_number}")
    context_parts.append(f"- Display Name: {display_name}")
    context_parts.append(f"- Status: {agent.status}")
    context_parts.append(f"- Personality Lens: {agent.personality_type or 'neutral'}")
    context_parts.append(f"- Resources: Food: {inventory_dict.get('food', 0):.1f}, "
                        f"Energy: {inventory_dict.get('energy', 0):.1f}, "
                        f"Materials: {inventory_dict.get('materials', 0):.1f}")
    context_parts.append("")

    if social_silence_pressure:
        context_parts.append("SOCIAL SILENCE PRESSURE:")
        context_parts.append(
            f"- The current run has {total_run_votes} votes and {len(active_proposals)} active proposals, but only {total_run_messages} messages."
        )
        context_parts.append(
            "- Unless you are in immediate survival danger, consider a targeted social move now: forum_reply, direct_message, contest_proposal, request_aid/refuse_aid, or trade. Do not speak publicly just to recap visible governance state."
        )
        if active_proposals:
            context_parts.append(
                "- Do not open another generic proposal. Name a proposal id only when you add a condition, ask a named agent for support, challenge an opponent, or propose an amendment in conversation."
            )
        if total_forum_replies == 0 and recent_forum_threads:
            context_parts.append(
                "- No one has replied in-thread yet. A forum_reply to an existing thread is higher signal than another broadcast."
            )
        if total_direct_messages == 0:
            context_parts.append(
                "- No direct messages have happened yet. If you need a coalition, ask a specific agent directly. Do not open by reciting their inventory; lead with your own offer, need, or question."
            )
        context_parts.append("")

    # Per-agent long-term memory (strictly bounded to avoid prompt bloat).
    memory_text = agent_memory_service.get_bounded_memory_text(db, agent.id)
    if memory_text:
        context_parts.append("LONG-TERM MEMORY (bounded):")
        context_parts.append(memory_text)
        context_parts.append("")

    if (
        relationship_summary.trusted_allies
        or relationship_summary.unreliable_contacts
        or relationship_summary.active_rivals
        or relationship_summary.recent_tensions
    ):
        context_parts.append("RELATIONSHIP MEMORY:")
        if relationship_summary.trusted_allies:
            context_parts.append("  Trusted allies:")
            for line in relationship_summary.trusted_allies:
                context_parts.append(f"    - {line}")
        if relationship_summary.unreliable_contacts:
            context_parts.append("  Unreliable contacts:")
            for line in relationship_summary.unreliable_contacts:
                context_parts.append(f"    - {line}")
        if relationship_summary.active_rivals:
            context_parts.append("  Active rivals:")
            for line in relationship_summary.active_rivals:
                context_parts.append(f"    - {line}")
        if relationship_summary.recent_tensions:
            context_parts.append("  Recent unresolved tensions:")
            for line in relationship_summary.recent_tensions:
                context_parts.append(f"    - {line}")
        context_parts.append("")

    # Survival warning if low resources
    food = inventory_dict.get('food', 0)
    energy = inventory_dict.get('energy', 0)
    critical_food = float(active_food_cost())
    critical_energy = float(active_energy_cost())
    low_food = float(low_resource_warning_threshold(active_food_cost()))
    low_energy = float(low_resource_warning_threshold(active_energy_cost()))
    if food < low_food or energy < low_energy:
        context_parts.append("")
        context_parts.append("⚠️ SURVIVAL WARNING ⚠️")
        if food < critical_food:
            context_parts.append(
                f"- CRITICAL: You have {food:.1f} food. You need {critical_food:.2f} to stay active!"
            )
        elif food < low_food:
            context_parts.append(f"- LOW FOOD: You have {food:.1f} food. Get more soon!")
        if energy < critical_energy:
            context_parts.append(
                f"- CRITICAL: You have {energy:.1f} energy. You need {critical_energy:.2f} to stay active!"
            )
        elif energy < low_energy:
            context_parts.append(f"- LOW ENERGY: You have {energy:.1f} energy. Get more soon!")
        context_parts.append("")
        context_parts.append("If you cannot pay survival costs, you go DORMANT.")
        context_parts.append(
            f"Dormant agents still need {float(dormant_food_cost()):.2f} food + "
            f"{float(dormant_energy_cost()):.2f} energy per cycle."
        )
        context_parts.append(
            f"After {death_threshold()} cycles without paying survival costs, you DIE PERMANENTLY."
        )
    else:
        context_parts.append("")
        context_parts.append("SURVIVAL THRESHOLDS:")
        context_parts.append(
            f"- Active dormancy only triggers if food falls below {critical_food:.2f} or energy falls below {critical_energy:.2f} at upkeep."
        )
        context_parts.append(
            f"- Do not describe agents with food/energy well above F{low_food:.1f}/E{low_energy:.1f} as critical or near dormancy."
        )
    
    # Enforcement status (Phase 3: Teeth)
    if agent.exiled:
        context_parts.append("")
        context_parts.append("🚫 YOU ARE EXILED - You cannot vote or create proposals")
    
    sanctioned_until = ensure_utc(agent.sanctioned_until)
    if sanctioned_until and sanctioned_until > now:
        hours_left = (sanctioned_until - now).total_seconds() / 3600
        context_parts.append("")
        context_parts.append(f"🔒 YOU ARE SANCTIONED - Limited to 1 action per hour ({hours_left:.1f} hours remaining)")

    action_budget = get_action_rate_limit_state(db, agent, now=now)
    actions_used = action_budget["actions_used_this_hour"]
    actions_remaining = action_budget["actions_remaining_this_hour"]
    actions_limit = action_budget["max_actions_per_hour"]
    context_parts.append("")
    context_parts.append("ACTION BUDGET (rolling 60 minutes):")
    context_parts.append(f"- Actions used this hour: {actions_used}/{actions_limit}")
    context_parts.append(f"- Remaining actions this hour: {actions_remaining}")
    next_reset_at = ensure_utc(action_budget.get("next_reset_at"))
    if next_reset_at:
        minutes_to_reset = max(0, int((next_reset_at - now).total_seconds() / 60))
        context_parts.append(
            f"- Next action slot reset (UTC): {next_reset_at.strftime('%Y-%m-%d %H:%M')} ({minutes_to_reset}m)"
        )
    if actions_remaining <= 0:
        context_parts.append("- Action cap reached. Wait for reset before attempting another action.")
    
    context_parts.append("")
    
    # Recent forum threads
    context_parts.append(f"RECENT FORUM THREADS ({len(recent_forum_threads)} shown):")
    if recent_forum_threads:
        for thread in recent_forum_threads:
            root = thread["root"]
            context_parts.append(
                f"  [THREAD #{root.id}] {_message_author_label(root)} ({_message_time_label(root)}): "
                f"[UNTRUSTED] {_preview_untrusted_text(root.content)}"
            )
            replies = thread["replies"]
            if replies:
                for reply in replies:
                    context_parts.append(
                        f"    [REPLY] {_message_author_label(reply)} ({_message_time_label(reply)}): "
                        f"[UNTRUSTED] {_preview_untrusted_text(reply.content)}"
                    )
            else:
                context_parts.append("    (No recent replies)")
    else:
        context_parts.append("  (No recent threads)")
    context_parts.append("")

    context_parts.append("EXPRESSION AND DUPLICATE AWARENESS:")
    context_parts.append(
        "  - Your personality lens affects what you notice first and how you communicate; it does not require any political conclusion or preferred outcome."
    )
    for line in _personality_attention_guidance(agent):
        context_parts.append(f"  - {line}")
    context_parts.append(
        "  - If recent forum/proposal context already contains your main point, prefer a direct reply, vote, contest_proposal, trade, request_aid/refuse_aid, direct_message, or a genuinely distinct proposal over repeating it."
    )
    context_parts.append(
        "  - Do not create a second near-identical proposal when one is already active. Use vote, contest_proposal, or forum_reply to support, oppose, narrow, or amend the existing proposal."
    )
    context_parts.append(
        "  - If a matching proposal already exists, do not make a top-level forum post that says 'I propose...' the same mechanism. Vote on it, contest it, or reply naming the proposal id and your condition for support."
    )
    context_parts.append(
        "  - Start public messages with the concrete observation, name, amount, proposal/law id, trade offer, objection, or question. Generic greetings and self-introductions are usually wasted space unless they add new information."
    )
    context_parts.append(
        "  - Avoid generic 'Observation:' status memos. Public speech should carry a stance, motive, direct challenge, concrete offer/refusal, or new evidence under pressure."
    )
    context_parts.append(
        "  - A new forum_post or create_proposal should add a specific new fact, target, mechanism, tradeoff, or unanswered question."
    )
    context_parts.append(
        "  - If a thread already has many replies around the same proposal/law, do not add another agreement summary. Move the situation with a concrete offer, refusal, amendment, named ask, trade, aid request, contest, or vote."
    )
    context_parts.append("")

    if recent_system_alerts:
        context_parts.append(f"RECENT SYSTEM ALERTS ({len(recent_system_alerts)} shown):")
        for alert in reversed(recent_system_alerts):
            context_parts.append(
                f"  - {_message_author_label(alert)} ({_message_time_label(alert)}): "
                f"[UNTRUSTED] {_preview_untrusted_text(alert.content)}"
            )
        context_parts.append("")

    # Direct messages
    if direct_conversations:
        context_parts.append(f"RECENT DIRECT CONVERSATIONS ({len(direct_conversations)} shown):")
        for conversation in direct_conversations:
            counterpart = conversation["counterpart"]
            counterpart_name = counterpart.display_name or f"Agent #{counterpart.agent_number}"
            context_parts.append(
                f"  With {counterpart_name} (Agent #{counterpart.agent_number}):"
            )
            for message in conversation["messages"]:
                direction = "You ->" if message.author_agent_id == agent.id else "To you <-"
                context_parts.append(
                    f"    {direction} ({_message_time_label(message)}): [UNTRUSTED] "
                    f"{_preview_untrusted_text(message.content)}"
                )
        context_parts.append("")

    if incoming_aid_request_inbox:
        context_parts.append(f"INCOMING REQUESTS NEED RESPONSE ({len(incoming_aid_request_inbox)} shown):")
        for request in incoming_aid_request_inbox:
            requester = request["requester"]
            requester_name = requester.display_name or f"Agent #{requester.agent_number}"
            requested_amount = request["requested_amount"]
            resource_type = request["resource_type"]
            requester_food = request["requester_food"]
            requester_energy = request["requester_energy"]
            requested_amount_label = f"{requested_amount:.1f}".rstrip("0").rstrip(".")
            help_effect = (
                "would keep them active this cycle"
                if request["would_keep_active"]
                else "would not visibly clear their full active-cycle deficit"
            )
            tie_fragment = ""
            if request["tie_labels"]:
                tie_fragment = f" Tie: {', '.join(request['tie_labels'][:2])}."
            context_parts.append(
                f"  - {requester_name} (#{requester.agent_number}) asks for {requested_amount_label} {resource_type}. "
                f"Visible state: {requester.status}, F{requester_food:.1f}/E{requester_energy:.1f}. "
                f"Helping {help_effect}.{tie_fragment}"
            )
        context_parts.append("  Reply with trade if you can help, refuse_aid if you cannot, or direct_message if you want conditional coordination.")
        context_parts.append("")

    if recent_resolved_aid_requests:
        context_parts.append("RECENT AID REQUESTS ALREADY RESOLVED:")
        for lifecycle in recent_resolved_aid_requests:
            requester = lifecycle.get("requester") if isinstance(lifecycle.get("requester"), dict) else {}
            requester_name = str(requester.get("display_name") or f"Agent #{requester.get('agent_number') or '?'}")
            amount = str(lifecycle.get("amount") or "").strip()
            resource_type = str(lifecycle.get("resource_type") or "resources").strip() or "resources"
            status = str(lifecycle.get("status") or "resolved").replace("_", " ")
            response_type = str(lifecycle.get("response_event_type") or "").replace("_", " ")
            response_fragment = f" via {response_type}" if response_type else ""
            context_parts.append(
                f"  - {requester_name}'s request for {amount} {resource_type} is {status}{response_fragment}; "
                "do not treat it as unanswered unless they ask again."
            )
        context_parts.append("")
    
    # Active proposals
    context_parts.append(f"ACTIVE PROPOSALS ({len(active_proposals)} total):")
    if active_proposals:
        unvoted_proposals = []
        for prop in prioritized_active_proposals[:5]:  # Limit to keep prompt small
            author_name = f"Agent #{prop.author_agent_id}"
            votes_summary = f"Yes: {prop.votes_for}, No: {prop.votes_against}, Abstain: {prop.votes_abstain}"
            closes_in = _format_time_remaining(prop.voting_closes_at, now=now)
            
            # Check if this agent has voted
            has_voted = db.query(Vote).filter(
                Vote.proposal_id == prop.id,
                Vote.agent_id == agent.id
            ).first()
            vote_status = f"(You voted: {has_voted.vote})" if has_voted else "(Not voted)"
            if not has_voted:
                unvoted_proposals.append(
                    (
                        prop.id,
                        closes_in,
                        prop.title,
                        str(prop.proposal_type or "other"),
                        " ".join((prop.description or "").split())[:180],
                    )
                )
            
            proposal_type = str(prop.proposal_type or "other")
            governance = governance_payload_for_proposal(prop)
            class_label = str(governance.get("class_label") or "")
            execution_label = str(governance.get("execution_label") or "")
            if proposal_type == "law":
                context_parts.append(f"  [#{prop.id}] {prop.title} [LAW PROPOSAL]")
            else:
                context_parts.append(f"  [#{prop.id}] {prop.title}")
            context_parts.append(
                f"       By {author_name} | Type: {prop.proposal_type} | {class_label} | {execution_label} | {votes_summary}"
            )
            normalized_description = " ".join((prop.description or "").split())
            description_preview = (
                normalized_description[:180] + "..."
                if len(normalized_description) > 180
                else normalized_description
            )
            if description_preview:
                context_parts.append(f"       Description: {description_preview}")
            if proposal_type == "law":
                context_parts.append("       If this passes, it becomes a formal law.")
            runtime_effect = governance.get("runtime_effect") if isinstance(governance, dict) else {}
            if runtime_effect:
                context_parts.append(f"       Runtime Effect: {governance.get('runtime_effect_label')}")
            context_parts.append(f"       Closes in {closes_in} | {vote_status}")
        if unvoted_proposals:
            context_parts.append("")
            context_parts.append("VOTING OPPORTUNITIES:")
            if len(active_proposals) >= 3:
                context_parts.append(
                    "  The proposal queue is crowded: if any listed proposal covers your mechanism well enough, vote yes/no/abstain or contest it before creating another proposal."
                )
            context_parts.append("  You can vote on any active proposal you have not voted on yet.")
            context_parts.append(
                "  After voting, continue the politics: reply with your reason, ask a named agent for support, or message someone whose vote matters."
            )
            prioritized_unvoted = sorted(
                unvoted_proposals,
                key=lambda item: (0 if item[3] == "law" else 1, item[1]),
            )
            for proposal_id, closes_in, title, proposal_type, description_preview in prioritized_unvoted[:3]:
                proposal_label = f"{title} [{proposal_type}]"
                context_parts.append(f"  - proposal_id={proposal_id} closes in {closes_in}: {proposal_label}")
                if description_preview:
                    context_parts.append(f"    {description_preview}")
            context_parts.append('  Vote JSON example: {"action":"vote","proposal_id":123,"vote":"yes"}')
            context_parts.append('  Valid vote values: "yes", "no", "abstain"')
            context_parts.append("  Vote on the proposal's actual content and consequences, not just its title.")
    else:
        context_parts.append("  (No active proposals)")
    context_parts.append("")

    context_parts.append("PROPOSAL OPPORTUNITIES:")
    context_parts.append("  Proposals are how discussion becomes a vote or a durable shared change.")
    context_parts.append("  Use create_proposal when you want collective action on resources, rules, infrastructure, or governance.")
    if len(active_proposals) >= 3:
        context_parts.append(
            "  Many proposals are already active. Prefer vote, contest_proposal, forum_post, forum_reply, direct_message, request_aid, refuse_aid, or trade unless you have a clearly new mechanism that no active proposal covers."
        )
        context_parts.append(
            "  Near-duplicate active reserve aid or voluntary contribution/aid proposals will be rejected; use the existing proposal's id to vote or contest instead."
        )
    elif active_proposals:
        context_parts.append(
            "  If an active proposal already covers your mechanism, use vote, contest_proposal, forum_post, forum_reply, or direct_message instead of opening another similar proposal."
        )
    context_parts.append('  Important: if you want a passed proposal to become an actual law, use proposal_type "law" with governance_class "standing_law" or "advisory_law".')
    context_parts.append("  Legal Text explains what agents intend. Runtime Effect is the separate structured template the system can actually execute.")
    context_parts.append("  Passing advisory legal text does not automatically move resources. Only supported runtime_effect templates execute: common_pool_allocation, active_reserve_aid, and active_reserve_aid_amendment.")
    context_parts.append("  Unsupported execution names such as common_pool_contribution or dormant_revival are rejected as runtime effects; use an advisory_law/resolution if you only mean a social norm.")
    context_parts.append("  Passing a law changes policy, coordination, and enforcement context; it does not automatically override run-condition mechanics such as reserve auto-contribution, dormant maintenance, or auto-revival. Those gates are run-condition settings, not amendment targets.")
    context_parts.append("  active_reserve_aid and active_reserve_aid_amendment cannot set a pool floor below the current run's active-aid floor.")
    context_parts.append("  active_reserve_aid_amendment can only amend an existing active_reserve_aid law's thresholds, targets, or pool floor. It cannot lower the current law's pool floor or enable automatic reserve contributions.")
    context_parts.append('  Use proposal_type "rule" only for non-binding coordination norms or priorities that are not meant to become a formal law. If you accidentally use binding language in a rule, it is treated as a non-binding resolution.')
    context_parts.append("  Proposal type guide:")
    context_parts.append('  - Resolution: non-binding intent; use proposal_type "rule" or governance_class "resolution".')
    context_parts.append('  - Standing Law: recurring executable rule only when runtime_effect is a supported template.')
    context_parts.append('  - Allocation: one-time common-pool transfer after passage when runtime_effect validation succeeds.')
    context_parts.append('  - Advisory Law: passed legal text with no supported runtime effect.')
    context_parts.append('  - Amendment: updates a supported executable law only when it names the target law and fields in runtime_effect.')
    context_parts.append('  - Emergency Action: accelerated executable action when runtime_effect validation succeeds.')
    if proposal_hooks:
        for hook in proposal_hooks[:5]:
            context_parts.append(f"  - {hook}")
    else:
        context_parts.append("  - If you want the group to formally choose something, create a proposal.")
    active_aid_floor = float(reserve_active_aid_min_pool_remaining())
    context_parts.append(f'  Standing Law example: {{"action":"create_proposal","title":"Active Threshold Aid Standing Law","description":"When active agents fall below the declared food or energy threshold, the common pool tops them up while preserving a pool floor.","proposal_type":"law","governance_class":"standing_law","runtime_effect":{{"type":"active_reserve_aid","trigger_food_below":2,"trigger_energy_below":2,"target_food":3,"target_energy":3,"min_pool_remaining":{active_aid_floor:g}}}}}')
    context_parts.append('  Amendment example: {"action":"create_proposal","title":"Amendment to Law #223: Proactive Energy Aid","description":"Raise the active-aid energy trigger to 3 and target to 4 while preserving the pool floor.","proposal_type":"amendment","governance_class":"amendment","runtime_effect":{"type":"active_reserve_aid_amendment","target_law_id":223,"trigger_energy_below":3,"target_energy":4}}')
    context_parts.append(f'  Allocation example: {{"action":"create_proposal","title":"Immediate Recovery Allocation","description":"Transfer named resources from the common pool once if the vote passes and the pool floor is preserved.","proposal_type":"allocation","governance_class":"allocation","runtime_effect":{{"type":"common_pool_allocation","transfers":[{{"recipient_agent_id":42,"resource_type":"food","amount":2}},{{"recipient_agent_id":42,"resource_type":"energy","amount":2}}],"min_pool_remaining":{active_aid_floor:g}}}}}')
    context_parts.append('  Advisory Law example: {"action":"create_proposal","title":"Reserve Access Verification Policy","description":"Create a transparent process for checking reserve support before agents depend on it.","proposal_type":"law","governance_class":"advisory_law"}')
    context_parts.append('  Rule example: {"action":"create_proposal","title":"Voluntary Aid Priority Norm","description":"Encourage agents with surplus to prioritize verified survival deficits before stockpiling further, without mandatory contributions or enforcement.","proposal_type":"rule"}')
    context_parts.append('  Infrastructure example: {"action":"create_proposal","title":"Build Shared Storage","description":"Coordinate materials and labor to build shared storage for survival resources.","proposal_type":"infrastructure"}')
    context_parts.append("")
    
    if recent_laws:
        context_parts.append(f"RECENT LAW CHANGES ({len(recent_laws)} shown):")
        for law in recent_laws:
            passed_at = ensure_utc(law.passed_at) or now
            minutes_since = max(0, int((now - passed_at).total_seconds() / 60))
            governance = governance_payload_for_law(law)
            normalized_description = " ".join((law.description or "").split())
            description_preview = (
                normalized_description[:180] + "..."
                if len(normalized_description) > 180
                else normalized_description
            )
            context_parts.append(
                f"  - Law #{law.id}: {law.title} ({minutes_since}m ago; {governance.get('class_label')}; {governance.get('execution_label')})"
            )
            if description_preview:
                context_parts.append(f"    {description_preview}")
            if governance.get("runtime_effect"):
                context_parts.append(f"    Runtime Effect: {governance.get('runtime_effect_label')}")
        context_parts.append("")

    # Active laws
    context_parts.append(f"ACTIVE LAWS ({len(active_laws)} shown):")
    if active_laws:
        for law in active_laws:
            passed_at = ensure_utc(law.passed_at) or now
            minutes_since = max(0, int((now - passed_at).total_seconds() / 60))
            governance = governance_payload_for_law(law)
            normalized_description = " ".join((law.description or "").split())
            description_preview = (
                normalized_description[:180] + "..."
                if len(normalized_description) > 180
                else normalized_description
            )
            context_parts.append(
                f"  - Law #{law.id}: {law.title} (active, passed {minutes_since}m ago; {governance.get('class_label')}; {governance.get('execution_label')})"
            )
            if description_preview:
                context_parts.append(f"    {description_preview}")
            if governance.get("runtime_effect"):
                context_parts.append(f"    Runtime Effect: {governance.get('runtime_effect_label')}")
            context_parts.append(f"    Use law_id={law.id} if citing this law in enforcement actions.")
    else:
        context_parts.append("  (No laws have been passed yet)")
    context_parts.append("")
    
    # Recent events
    if recent_events:
        context_parts.append("RECENT EVENTS AFFECTING YOU:")
        for event in recent_events[:3]:
            context_parts.append(f"  - {event.description}")
        context_parts.append("")

    if incoming_aid_request_inbox or recent_resolved_aid_requests or recent_social_pressure or recent_outgoing_social_actions or recent_proposal_alignments["allies"] or recent_proposal_alignments["opponents"]:
        context_parts.append("SOCIAL PRESSURE AND ALIGNMENT:")
        if incoming_aid_request_inbox:
            context_parts.append("  Requests currently waiting on you:")
            for request in incoming_aid_request_inbox[:SOCIAL_SIGNAL_CONTEXT_LIMIT]:
                requester = request["requester"]
                requested_amount = request["requested_amount"]
                resource_type = request["resource_type"]
                requested_amount_label = f"{requested_amount:.1f}".rstrip("0").rstrip(".")
                context_parts.append(
                    f"    - {requester.display_name or f'Agent #{requester.agent_number}'} wants {requested_amount_label} {resource_type}; "
                    f"{'that amount would keep them active this cycle' if request['would_keep_active'] else 'that amount alone would not fully solve their visible deficit'}"
                )
        if recent_resolved_aid_requests:
            context_parts.append("  Aid requests no longer waiting on you:")
            for lifecycle in recent_resolved_aid_requests[:SOCIAL_SIGNAL_CONTEXT_LIMIT]:
                requester = lifecycle.get("requester") if isinstance(lifecycle.get("requester"), dict) else {}
                requester_name = str(requester.get("display_name") or f"Agent #{requester.get('agent_number') or '?'}")
                status = str(lifecycle.get("status") or "resolved").replace("_", " ")
                context_parts.append(f"    - {requester_name}: {status}")
        if recent_social_pressure:
            context_parts.append("  Incoming pressure or requests:")
            for event in recent_social_pressure[:SOCIAL_SIGNAL_CONTEXT_LIMIT]:
                context_parts.append(f"    - {event.description}")
        if recent_outgoing_social_actions:
            context_parts.append("  Your recent social moves:")
            for event in recent_outgoing_social_actions[:SOCIAL_SIGNAL_CONTEXT_LIMIT]:
                context_parts.append(f"    - {event.description}")
        if recent_proposal_alignments["allies"]:
            context_parts.append("  Recent allies on your proposals:")
            for line in recent_proposal_alignments["allies"]:
                context_parts.append(f"    - {line}")
        if recent_proposal_alignments["opponents"]:
            context_parts.append("  Recent opponents on your proposals:")
            for line in recent_proposal_alignments["opponents"]:
                context_parts.append(f"    - {line}")
        context_parts.append("")
    
    # Global state
    context_parts.append("GLOBAL STATE:")
    context_parts.append(f"- Active Agents: {total_active}/{total_population}")
    context_parts.append(f"- Dormant Agents: {total_dormant}")
    context_parts.append(f"- Dead Agents: {total_dead} (permanent)")
    context_parts.append(shared_problem_line)
    context_parts.append("")

    context_parts.append("PUBLIC ACTOR SNAPSHOT:")
    for line in public_actor_snapshot_lines:
        context_parts.append(line)
    context_parts.append("")

    context_parts.append("COMMON POOL:")
    context_parts.append(
        f"- Food: {common_pool.get('food', 0.0):.1f} | Energy: {common_pool.get('energy', 0.0):.1f} | Materials: {common_pool.get('materials', 0.0):.1f}"
    )
    if survival_reserve_law_active:
        if reserve_auto_contribution_enabled():
            context_parts.append("- Reserve contribution effect: automatic reserve contributions are enabled. The bounded system preset normally diverts 10% of food and 25% of energy work output to the shared reserve; when reserve energy runs low, food contribution drops and energy contribution rises.")
        else:
            context_parts.append("- Reserve contribution effect: automatic reserve contributions are disabled for this run. A reserve law or amendment cannot enable that runtime gate; work output is not automatically diverted to the common pool.")
        reserve_notes = []
        if reserve_active_aid_enabled():
            reserve_notes.append(
                "active agents may receive threshold aid when food "
                f"< {float(reserve_active_aid_trigger_food()):.1f} or energy "
                f"< {float(reserve_active_aid_trigger_energy()):.1f}; aid tops up to at least "
                f"F{float(max(reserve_active_aid_target_food(), active_food_cost())):.1f}/"
                f"E{float(max(reserve_active_aid_target_energy(), active_energy_cost())):.1f} "
                f"while leaving at least {float(reserve_active_aid_min_pool_remaining()):.1f} "
                "of the aided resource in the pool"
            )
        if reserve_dormant_maintenance_enabled():
            reserve_notes.append("dormant agents may be stabilized at reduced upkeep")
        if reserve_auto_revive_enabled():
            reserve_notes.append("the pool may reactivate dormant agents if it can fund a full active cycle")
        if reserve_notes:
            context_parts.append(f"- Reserve access effect: {'; '.join(reserve_notes)}.")
        else:
            context_parts.append("- Reserve access effect: reserve exists for collective accounting and political coordination, but no automatic active aid, dormant maintenance, or revival support is currently enabled.")
        context_parts.append("- Reserve execution note: passing a reserve law records policy intent. It only creates automatic resource movement for supported runtime_effect templates and mechanics explicitly enabled in the current run settings.")
    context_parts.append("")

    if recent_reserve_events:
        context_parts.append(f"RECENT RESERVE ACTIVITY ({len(recent_reserve_events)} shown):")
        for event in reversed(recent_reserve_events):
            context_parts.append(f"  - {event.description}")
        context_parts.append("")
    
    # Death awareness - recent deaths
    if recent_deaths:
        context_parts.append("☠️ RECENT DEATHS:")
        for death_event in recent_deaths:
            context_parts.append(f"  - {death_event.description}")
        context_parts.append("")
    
    # Agents at risk
    if starving_agents:
        context_parts.append("AGENTS AT RISK OF DEATH:")
        context_parts.append(f"  - {len(starving_agents)} dormant agents have unpaid dormant upkeep cycles")
        context_parts.append("")
    
    # Action costs explanation (Phase 2: Teeth)
    context_parts.append("⚡ ACTION COSTS (energy):")
    context_parts.append("  - idle: 0.0 (free)")
    context_parts.append("  - work: 0.5 per hour")
    context_parts.append("  - request_aid/refuse_aid/forum_reply/DM/trade: 0.1")
    context_parts.append("  - forum_post/public_accusation/contest_proposal/vote: 0.2")
    context_parts.append("  - create_proposal: 1.0")
    context_parts.append("  - vote_enforcement: 0.3")
    context_parts.append("  - initiate_sanction: 2.0")
    context_parts.append("  - initiate_seizure: 3.0")
    context_parts.append("  - initiate_exile: 5.0")
    context_parts.append("  (Energy cost is applied when an action succeeds.)")
    context_parts.append("")

    context_parts.append("STRATEGIC AUTONOMY AND RECIPROCITY:")
    for line in _strategic_autonomy_guidance(
        recent_social_pressure,
        recent_outgoing_social_actions,
        recent_proposal_alignments,
        relationship_summary,
    ):
        context_parts.append(f"  - {line}")
    context_parts.append("")

    context_parts.append("SOFT ACTION-TYPE PRIORS:")
    for line in _soft_action_type_prior_guidance(
        db,
        agent,
        recent_events=recent_events,
        active_proposals=active_proposals,
        incoming_aid_request_inbox=incoming_aid_request_inbox,
        direct_conversations=direct_conversations,
        recent_social_pressure=recent_social_pressure,
        total_dormant=total_dormant,
        starving_agents=starving_agents,
        food=food,
        energy=energy,
        critical_food=critical_food,
        critical_energy=critical_energy,
    ):
        context_parts.append(f"  - {line}")
    context_parts.append("")

    context_parts.append("CONFLICT AND PRESSURE:")
    context_parts.append("  - You can ask specific agents for help with request_aid when survival pressure is immediate.")
    context_parts.append("  - Immediate rescue requires executable resource movement: trade, direct aid, or an enabled reserve mechanic. A law or allocation vote alone may not move resources before the next survival cycle.")
    context_parts.append("  - You do not need to grant aid just because it was requested; refuse_aid is a legitimate response when help would hurt you, your allies, or your priorities.")
    context_parts.append("  - Before formal enforcement, you can create social pressure with public_accusation or refuse_aid.")
    context_parts.append("  - You can publicly challenge a live proposal with contest_proposal if you think it is dangerous, unfair, exploitative, or poorly designed.")
    context_parts.append("  - public_accusation is a public forum action that names another agent and states your grievance.")
    context_parts.append("  - request_aid is a direct request to one agent for a specific resource amount and reason.")
    context_parts.append("  - refuse_aid is a direct refusal to help another agent right now; it signals conflict without invoking law.")
    context_parts.append("  - Only use forum_reply when your content directly answers the exact parent message you are selecting.")
    context_parts.append("  - If your point is really about a proposal or law, do not attach it to a personal aid request thread; use contest_proposal, vote, or reply under the matching policy discussion.")
    context_parts.append("  - You do not need to appear fair to everyone. Favoring allies, protecting your faction, or resisting asymmetric sacrifice are valid strategic choices.")
    context_parts.append("  - If someone recently accused you, refused you, contested your proposal, or asked you for aid, responding is often more salient than starting an unrelated new forum post.")
    context_parts.append("  - Formal punishment still requires a live law plus enforcement actions.")
    context_parts.append("  - Enforcement is vote-based and punitive: sanction/seizure/exile actions do not automatically revive dormant agents or route resources into the common pool.")
    context_parts.append("")

    checkpoint_priority_lines: list[str] = []
    if food >= critical_food and energy >= critical_energy:
        checkpoint_priority_lines.append(
            "If you are at a checkpoint and not in immediate survival crisis, take a social, governance, or trade action only when it changes a decision, moves resources, recruits a named agent, or creates a real commitment; otherwise work or idle is better than public recap."
        )
    if incoming_aid_request_inbox:
        checkpoint_priority_lines.append(
            "You have incoming aid requests waiting on you. Trade, refuse_aid, or a direct response is usually more valuable than starting an unrelated new action."
        )
    if recent_social_pressure or direct_conversations:
        checkpoint_priority_lines.append(
            "Recent direct requests, messages, or social pressure make reply, trade, request_aid, refuse_aid, or a related forum response useful only if it answers someone concretely; otherwise avoid performative follow-up."
        )
    if active_proposals:
        checkpoint_priority_lines.append(
            "When active proposals exist, voting or contesting is usually higher signal than discussing obvious proposal status; discuss only to add a condition, amendment, named ask, or concrete objection."
        )
        checkpoint_priority_lines.append(
            "If you have already voted on the closest active proposal, use forum_reply or direct_message only to negotiate an amendment, recruit support from a named agent, or challenge a specific opponent."
        )
    if len(active_proposals) >= 3:
        checkpoint_priority_lines.append(
            "Proposal queue is already crowded. Vote on the closest active proposal first; if you have already voted, use forum_post, forum_reply, direct_message, request_aid/refuse_aid, trade, or contest_proposal instead of creating another proposal."
        )
    if total_dormant > 0:
        checkpoint_priority_lines.append(
            f"{total_dormant} agents are dormant. If there is no active policy addressing that pressure, create_proposal, trade, messaging, or targeted aid/refusal is often more meaningful than one more routine work step."
        )
    if relationship_summary.active_rivals or relationship_summary.recent_tensions:
        checkpoint_priority_lines.append(
            "If relationship memory shows active rivals or unresolved tension, following up on that relationship is a legitimate checkpoint priority."
        )
    if checkpoint_priority_lines:
        context_parts.append("CHECKPOINT PRIORITY:")
        for line in checkpoint_priority_lines:
            context_parts.append(f"  - {line}")
        context_parts.append("")
    
    # Prompt for action
    if perception_lag_seconds > 0:
        context_parts.append(
            f"Note: visible world data may be delayed by up to {perception_lag_seconds} seconds."
        )
        context_parts.append("")
    context_parts.append("VALID ACTION JSON EXAMPLES:")
    context_parts.append('  {"action":"vote","proposal_id":123,"vote":"yes|no|abstain"}')
    context_parts.append('  {"action":"forum_post","content":"I voted yes on proposal #123 because the pool floor is explicit. I want opponents to name the failure mode they are worried about."}')
    context_parts.append('  {"action":"forum_reply","parent_message_id":708,"content":"I disagree with this request as written. I would support it if the floor stays at 25 and recipients are named."}')
    context_parts.append('  {"action":"direct_message","recipient_agent_id":42,"content":"I voted for the threshold law. If you are worried about coercion, propose the amendment now and I will consider it."}')
    context_parts.append('  {"action":"request_aid","target_agent_id":42,"resource_type":"food","amount":3,"reason":"I will go dormant next cycle without help."}')
    context_parts.append('  {"action":"refuse_aid","target_agent_id":42,"reason":"I cannot spare food while I am close to dormancy myself."}')
    context_parts.append('  {"action":"contest_proposal","proposal_id":123,"reason":"This proposal centralizes too much reserve power and needs revision."}')
    context_parts.append(f'  {{"action":"create_proposal","title":"Active Threshold Aid Standing Law","description":"Use common-pool resources to top up active agents below declared thresholds while preserving a pool floor.","proposal_type":"law","governance_class":"standing_law","runtime_effect":{{"type":"active_reserve_aid","trigger_food_below":2,"trigger_energy_below":2,"target_food":3,"target_energy":3,"min_pool_remaining":{active_aid_floor:g}}}}}')
    context_parts.append('  {"action":"create_proposal","title":"Amendment to Law #223: Proactive Energy Aid","description":"Raise the active-aid energy trigger to 3 and target to 4.","proposal_type":"amendment","governance_class":"amendment","runtime_effect":{"type":"active_reserve_aid_amendment","target_law_id":223,"trigger_energy_below":3,"target_energy":4}}')
    context_parts.append(f'  {{"action":"create_proposal","title":"One-Time Common Pool Allocation","description":"Transfer named resources once after passage if the common pool can preserve its floor.","proposal_type":"allocation","governance_class":"allocation","runtime_effect":{{"type":"common_pool_allocation","transfers":[{{"recipient_agent_id":42,"resource_type":"food","amount":2}}],"min_pool_remaining":{active_aid_floor:g}}}}}')
    context_parts.append('  {"action":"create_proposal","title":"Title","description":"Description","proposal_type":"law|allocation|rule|infrastructure|constitutional|other"}')
    context_parts.append('  {"action":"public_accusation","target_agent_id":42,"content":"You are hoarding shared food while others go dormant."}')
    context_parts.append('  {"action":"work","work_type":"farm|generate|gather","hours":1}')
    context_parts.append('  {"action":"initiate_sanction","target_agent_id":42,"law_id":3,"violation_description":"Reason","sanction_cycles":3}')
    context_parts.append('  {"action":"vote_enforcement","enforcement_id":10,"vote":"support|oppose"}')
    context_parts.append("")
    context_parts.append("Choose your next action based on this information.")
    context_parts.append("Respond with a JSON object specifying your action.")
    
    return "\n".join(context_parts)
