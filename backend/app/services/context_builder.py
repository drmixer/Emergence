"""
Context Builder - Builds the prompt context for agent decisions.
"""
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.core.time import ensure_utc, now_utc
from app.models.models import Agent, AgentInventory, Message, Proposal, Law, Event, Vote


async def build_agent_context(db: Session, agent: Agent) -> str:
    """Build the context prompt for an agent's decision."""
    now = now_utc()
    perception_lag_seconds = max(0, int(getattr(settings, "PERCEPTION_LAG_SECONDS", 0) or 0))
    perception_cutoff = now - timedelta(seconds=perception_lag_seconds)
    
    # Get agent's inventory
    inventory = db.query(AgentInventory).filter(
        AgentInventory.agent_id == agent.id
    ).all()
    inventory_dict = {inv.resource_type: float(inv.quantity) for inv in inventory}
    
    # Get recent forum posts (keep small to reduce token usage)
    recent_messages_q = db.query(Message).filter(
        Message.message_type.in_(["forum_post", "forum_reply", "system_alert"])
    )
    if perception_lag_seconds > 0:
        recent_messages_q = recent_messages_q.filter(Message.created_at <= perception_cutoff)
    recent_messages = recent_messages_q.order_by(desc(Message.created_at)).limit(8).all()
    
    # Get active proposals (keep small to reduce token usage)
    active_proposals_q = db.query(Proposal).filter(
        Proposal.status == "active"
    )
    if perception_lag_seconds > 0:
        active_proposals_q = active_proposals_q.filter(Proposal.created_at <= perception_cutoff)
    active_proposals = active_proposals_q.order_by(desc(Proposal.created_at)).all()
    
    # Get recent events affecting this agent
    recent_events_q = db.query(Event).filter(
        Event.agent_id == agent.id,
        Event.created_at > now - timedelta(hours=24)
    )
    if perception_lag_seconds > 0:
        recent_events_q = recent_events_q.filter(Event.created_at <= perception_cutoff)
    recent_events = recent_events_q.order_by(desc(Event.created_at)).limit(10).all()
    
    # Get direct messages to this agent (keep small)
    direct_messages_q = db.query(Message).filter(
        Message.recipient_agent_id == agent.id,
        Message.message_type == "direct_message",
        Message.created_at > now - timedelta(hours=24)
    )
    if perception_lag_seconds > 0:
        direct_messages_q = direct_messages_q.filter(Message.created_at <= perception_cutoff)
    direct_messages = direct_messages_q.order_by(desc(Message.created_at)).limit(3).all()
    
    # Get active laws (keep small)
    active_laws = db.query(Law).filter(Law.active == True).all()
    
    # Get global stats
    total_active = db.query(Agent).filter(Agent.status == "active").count()
    total_dormant = db.query(Agent).filter(Agent.status == "dormant").count()
    total_dead = db.query(Agent).filter(Agent.status == "dead").count()
    
    # Get recent deaths (for awareness)
    recent_deaths_q = db.query(Event).filter(
        Event.event_type == "agent_died",
        Event.created_at > now - timedelta(hours=48)
    )
    if perception_lag_seconds > 0:
        recent_deaths_q = recent_deaths_q.filter(Event.created_at <= perception_cutoff)
    recent_deaths = recent_deaths_q.order_by(desc(Event.created_at)).limit(3).all()
    
    # Get agents at risk of death (starving dormant agents)
    starving_agents = db.query(Agent).filter(
        Agent.status == "dormant",
        Agent.starvation_cycles > 0
    ).all()
    
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
    context_parts.append(f"- Resources: Food: {inventory_dict.get('food', 0):.1f}, "
                        f"Energy: {inventory_dict.get('energy', 0):.1f}, "
                        f"Materials: {inventory_dict.get('materials', 0):.1f}")
    
    # Survival warning if low resources
    food = inventory_dict.get('food', 0)
    energy = inventory_dict.get('energy', 0)
    if food < 2 or energy < 2:
        context_parts.append("")
        context_parts.append("⚠️ SURVIVAL WARNING ⚠️")
        if food < 1:
            context_parts.append(f"- CRITICAL: You have {food:.1f} food. You need 1.0 to stay active!")
        elif food < 2:
            context_parts.append(f"- LOW FOOD: You have {food:.1f} food. Get more soon!")
        if energy < 1:
            context_parts.append(f"- CRITICAL: You have {energy:.1f} energy. You need 1.0 to stay active!")
        elif energy < 2:
            context_parts.append(f"- LOW ENERGY: You have {energy:.1f} energy. Get more soon!")
        context_parts.append("")
        context_parts.append("If you cannot pay survival costs, you go DORMANT.")
        context_parts.append("Dormant agents still need 0.25 food + 0.25 energy per cycle.")
        context_parts.append("After 5 cycles without paying survival costs, you DIE PERMANENTLY.")
    
    # Enforcement status (Phase 3: Teeth)
    if agent.exiled:
        context_parts.append("")
        context_parts.append("🚫 YOU ARE EXILED - You cannot vote or create proposals")
    
    sanctioned_until = ensure_utc(agent.sanctioned_until)
    if sanctioned_until and sanctioned_until > now:
        hours_left = (sanctioned_until - now).total_seconds() / 3600
        context_parts.append("")
        context_parts.append(f"🔒 YOU ARE SANCTIONED - Limited to 1 action per hour ({hours_left:.1f} hours remaining)")
    
    context_parts.append("")
    
    # Recent forum posts
    context_parts.append(f"RECENT FORUM POSTS ({len(recent_messages)} shown):")
    if recent_messages:
        for msg in reversed(recent_messages):  # Oldest first
            author_name = f"Agent #{msg.author_agent_id}"
            if msg.author and msg.author.display_name:
                author_name = msg.author.display_name
            time_str = msg.created_at.strftime("%H:%M")
            # Forum content is untrusted and can contain adversarial prompt-like text.
            # Collapse whitespace to reduce "instruction formatting" effects in downstream prompts.
            normalized = " ".join((msg.content or "").split())
            content_preview = normalized[:120] + "..." if len(normalized) > 120 else normalized
            msg_type = "[REPLY]" if msg.message_type == "forum_reply" else "[POST]"
            context_parts.append(f"  {msg_type} {author_name} ({time_str}): [UNTRUSTED] {content_preview}")
    else:
        context_parts.append("  (No recent posts)")
    context_parts.append("")
    
    # Direct messages
    if direct_messages:
        context_parts.append(f"DIRECT MESSAGES TO YOU ({len(direct_messages)} new):")
        for msg in direct_messages:
            author_name = f"Agent #{msg.author_agent_id}"
            time_str = msg.created_at.strftime("%H:%M")
            normalized = " ".join((msg.content or "").split())
            preview = normalized[:120] + "..." if len(normalized) > 120 else normalized
            context_parts.append(f"  From {author_name} ({time_str}): [UNTRUSTED] {preview}")
        context_parts.append("")
    
    # Active proposals
    context_parts.append(f"ACTIVE PROPOSALS ({len(active_proposals)} total):")
    if active_proposals:
        for prop in active_proposals[:5]:  # Limit to keep prompt small
            author_name = f"Agent #{prop.author_agent_id}"
            votes_summary = f"Yes: {prop.votes_for}, No: {prop.votes_against}, Abstain: {prop.votes_abstain}"
            closes_at = ensure_utc(prop.voting_closes_at) or now
            time_left = closes_at - now
            hours_left = max(0, int(time_left.total_seconds() / 3600))
            
            # Check if this agent has voted
            has_voted = db.query(Vote).filter(
                Vote.proposal_id == prop.id,
                Vote.agent_id == agent.id
            ).first()
            vote_status = f"(You voted: {has_voted.vote})" if has_voted else "(Not voted)"
            
            context_parts.append(f"  [#{prop.id}] {prop.title}")
            context_parts.append(f"       By {author_name} | Type: {prop.proposal_type} | {votes_summary}")
            context_parts.append(f"       Closes in {hours_left}h | {vote_status}")
    else:
        context_parts.append("  (No active proposals)")
    context_parts.append("")
    
    # Active laws
    context_parts.append(f"ACTIVE LAWS ({len(active_laws)} total):")
    if active_laws:
        for law in active_laws[:3]:  # Limit to keep prompt small
            context_parts.append(f"  - {law.title}")
    else:
        context_parts.append("  (No laws have been passed yet)")
    context_parts.append("")
    
    # Recent events
    if recent_events:
        context_parts.append("RECENT EVENTS AFFECTING YOU:")
        for event in recent_events[:3]:
            context_parts.append(f"  - {event.description}")
        context_parts.append("")
    
    # Global state
    context_parts.append("GLOBAL STATE:")
    context_parts.append(f"- Active Agents: {total_active}/100")
    context_parts.append(f"- Dormant Agents: {total_dormant}")
    context_parts.append(f"- Dead Agents: {total_dead} (permanent)")
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
        context_parts.append(f"  - {len(starving_agents)} dormant agents are currently starving")
        context_parts.append("")
    
    # Action costs explanation (Phase 2: Teeth)
    context_parts.append("⚡ ACTION COSTS (energy):")
    context_parts.append("  - idle/work/set_name: 0.0 (free)")
    context_parts.append("  - forum_reply/DM/trade: 0.1")
    context_parts.append("  - forum_post/vote: 0.2")
    context_parts.append("  - create_proposal: 1.0")
    context_parts.append("  - vote_enforcement: 0.3")
    context_parts.append("  - initiate_sanction: 2.0")
    context_parts.append("  - initiate_seizure: 3.0")
    context_parts.append("  - initiate_exile: 5.0")
    context_parts.append("  (Energy cost is applied when an action succeeds.)")
    context_parts.append("")
    
    # Prompt for action
    if perception_lag_seconds > 0:
        context_parts.append(
            f"Note: visible world data may be delayed by up to {perception_lag_seconds} seconds."
        )
        context_parts.append("")
    context_parts.append("Choose your next action based on this information.")
    context_parts.append("Respond with a JSON object specifying your action.")
    
    return "\n".join(context_parts)
