"""
Context Builder - Builds the prompt context for agent decisions.
"""
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.core.time import ensure_utc, now_utc
from app.models.models import Agent, AgentInventory, Message, Proposal, Law, Event, Vote, GlobalResources
from app.services.agent_memory import agent_memory_service
from app.services.actions import get_action_rate_limit_state
from app.services.law_effects import active_survival_reserve_laws
from app.services.survival_config import (
    active_energy_cost,
    active_food_cost,
    death_threshold,
    dormant_energy_cost,
    dormant_food_cost,
    low_resource_warning_threshold,
)


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
    prioritized_active_proposals = sorted(
        active_proposals,
        key=lambda prop: (
            0 if str(getattr(prop, "proposal_type", "") or "").strip().lower() == "law" else 1,
            -(int(getattr(prop, "id", 0) or 0)),
        ),
    )
    
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
    
    # Get active laws and recent law changes (keep small)
    active_laws_q = db.query(Law).filter(Law.active == True)
    recent_laws_q = db.query(Law).filter(Law.passed_at > now - timedelta(hours=24))
    if perception_lag_seconds > 0:
        active_laws_q = active_laws_q.filter(Law.passed_at <= perception_cutoff)
        recent_laws_q = recent_laws_q.filter(Law.passed_at <= perception_cutoff)
    active_laws = active_laws_q.order_by(desc(Law.passed_at)).limit(5).all()
    recent_laws = recent_laws_q.order_by(desc(Law.passed_at)).limit(3).all()
    reserve_laws = active_survival_reserve_laws(db)
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
    if perception_lag_seconds > 0:
        recent_reserve_events_q = recent_reserve_events_q.filter(Event.created_at <= perception_cutoff)
    recent_reserve_events = recent_reserve_events_q.order_by(desc(Event.created_at)).limit(4).all()

    proposal_hooks: list[str] = []
    if not active_proposals:
        proposal_hooks.append(
            "There are no active proposals. Forum discussion alone does not create a vote; create_proposal is the only way to start one."
        )
    if recent_messages and not active_proposals:
        proposal_hooks.append(
            f"There are {len(recent_messages)} recent forum posts but no formal proposal. If you want collective action, turn discussion into a proposal."
        )
    if starving_agents:
        proposal_hooks.append(
            f"{len(starving_agents)} dormant agents are starving. An allocation or rule proposal could coordinate aid or recovery."
        )
        proposal_hooks.append(
            "If you want recurring aid, reserve access, or an ongoing obligation across future cycles, prefer proposal_type \"law\" instead of a one-off allocation."
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
            "Shared reserve systems, recurring emergency aid, or mandatory pooled contributions usually need proposal_type \"law\" if you want them to become part of the live world state."
        )
    else:
        proposal_hooks.append(
            "Active laws are part of the live world state. You may adapt your behavior, discuss them, propose changes, or cite a law_id in enforcement if you think someone is violating one."
        )
    if survival_reserve_law_active:
        proposal_hooks.append(
            "A survival-reserve law is active: some food and energy work output now goes into the shared reserve automatically."
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
    context_parts.append(f"- Resources: Food: {inventory_dict.get('food', 0):.1f}, "
                        f"Energy: {inventory_dict.get('energy', 0):.1f}, "
                        f"Materials: {inventory_dict.get('materials', 0):.1f}")
    context_parts.append("")

    # Per-agent long-term memory (strictly bounded to avoid prompt bloat).
    memory_text = agent_memory_service.get_bounded_memory_text(db, agent.id)
    if memory_text:
        context_parts.append("LONG-TERM MEMORY (bounded):")
        context_parts.append(memory_text)
    
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
        unvoted_proposals = []
        for prop in prioritized_active_proposals[:5]:  # Limit to keep prompt small
            author_name = f"Agent #{prop.author_agent_id}"
            votes_summary = f"Yes: {prop.votes_for}, No: {prop.votes_against}, Abstain: {prop.votes_abstain}"
            closes_at = ensure_utc(prop.voting_closes_at) or now
            time_left = closes_at - now
            minutes_left = max(0, int(time_left.total_seconds() / 60))
            hours_left = minutes_left // 60
            remaining_minutes = minutes_left % 60
            if hours_left > 0:
                closes_in = f"{hours_left}h {remaining_minutes}m"
            else:
                closes_in = f"{minutes_left}m"
            
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
            if proposal_type == "law":
                context_parts.append(f"  [#{prop.id}] {prop.title} [LAW PROPOSAL]")
            else:
                context_parts.append(f"  [#{prop.id}] {prop.title}")
            context_parts.append(f"       By {author_name} | Type: {prop.proposal_type} | {votes_summary}")
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
            context_parts.append(f"       Closes in {closes_in} | {vote_status}")
        if unvoted_proposals:
            context_parts.append("")
            context_parts.append("VOTING OPPORTUNITIES:")
            context_parts.append("  You can vote on any active proposal you have not voted on yet.")
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
    context_parts.append('  Important: if you want a passed proposal to become an actual law, use proposal_type "law".')
    context_parts.append('  Use proposal_type "rule" for coordination norms or priorities that are not meant to become a formal law.')
    context_parts.append("  Proposal type guide:")
    context_parts.append('  - Use "law" for recurring obligations, reserve systems, ongoing aid rules, or anything you want enforced as a durable part of the world.')
    context_parts.append('  - Use "allocation" for one-time resource distributions that do not need to persist across future cycles.')
    context_parts.append('  - Use "rule" for soft norms or coordination preferences that are not meant to become a formal law.')
    if proposal_hooks:
        for hook in proposal_hooks[:5]:
            context_parts.append(f"  - {hook}")
    else:
        context_parts.append("  - If you want the group to formally choose something, create a proposal.")
    context_parts.append('  Law example: {"action":"create_proposal","title":"Emergency Aid Law","description":"Require the community to maintain and use a shared reserve to support dormant agents at risk of death.","proposal_type":"law"}')
    context_parts.append('  Law example: {"action":"create_proposal","title":"Shared Survival Reserve Law","description":"Require part of future food and energy production to enter the shared reserve and allow reserve support for agents who cannot meet survival costs.","proposal_type":"law"}')
    context_parts.append('  Allocation example: {"action":"create_proposal","title":"Emergency Aid for Dormant Agents","description":"Allocate shared food and energy to dormant agents at risk so they can return to active status.","proposal_type":"allocation"}')
    context_parts.append('  Rule example: {"action":"create_proposal","title":"Shared Survival Reserve","description":"Reserve part of future production to help agents facing dormancy or death.","proposal_type":"rule"}')
    context_parts.append('  Infrastructure example: {"action":"create_proposal","title":"Build Shared Storage","description":"Coordinate materials and labor to build shared storage for survival resources.","proposal_type":"infrastructure"}')
    context_parts.append("")
    
    if recent_laws:
        context_parts.append(f"RECENT LAW CHANGES ({len(recent_laws)} shown):")
        for law in recent_laws:
            passed_at = ensure_utc(law.passed_at) or now
            minutes_since = max(0, int((now - passed_at).total_seconds() / 60))
            normalized_description = " ".join((law.description or "").split())
            description_preview = (
                normalized_description[:180] + "..."
                if len(normalized_description) > 180
                else normalized_description
            )
            context_parts.append(f"  - Law #{law.id}: {law.title} ({minutes_since}m ago)")
            if description_preview:
                context_parts.append(f"    {description_preview}")
        context_parts.append("")

    # Active laws
    context_parts.append(f"ACTIVE LAWS ({len(active_laws)} shown):")
    if active_laws:
        for law in active_laws:
            passed_at = ensure_utc(law.passed_at) or now
            minutes_since = max(0, int((now - passed_at).total_seconds() / 60))
            normalized_description = " ".join((law.description or "").split())
            description_preview = (
                normalized_description[:180] + "..."
                if len(normalized_description) > 180
                else normalized_description
            )
            context_parts.append(f"  - Law #{law.id}: {law.title} (active, passed {minutes_since}m ago)")
            if description_preview:
                context_parts.append(f"    {description_preview}")
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
    
    # Global state
    context_parts.append("GLOBAL STATE:")
    context_parts.append(f"- Active Agents: {total_active}/{total_population}")
    context_parts.append(f"- Dormant Agents: {total_dormant}")
    context_parts.append(f"- Dead Agents: {total_dead} (permanent)")
    context_parts.append("")

    context_parts.append("COMMON POOL:")
    context_parts.append(
        f"- Food: {common_pool.get('food', 0.0):.1f} | Energy: {common_pool.get('energy', 0.0):.1f} | Materials: {common_pool.get('materials', 0.0):.1f}"
    )
    if survival_reserve_law_active:
        context_parts.append("- Active reserve law effect: reserve contributions are energy-biased. Normally 10% of food and 25% of energy work output go to the shared reserve; when reserve energy runs low, food contribution drops and energy contribution rises.")
        context_parts.append("- Reserve access effect: active agents may draw exact deficits to stay active; dormant agents may be stabilized or, if the pool is strong enough, revived back to active status.")
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
        context_parts.append(f"  - {len(starving_agents)} dormant agents are currently starving")
        context_parts.append("")
    
    # Action costs explanation (Phase 2: Teeth)
    context_parts.append("⚡ ACTION COSTS (energy):")
    context_parts.append("  - idle/work: 0.0 (free)")
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
    context_parts.append("VALID ACTION JSON EXAMPLES:")
    context_parts.append('  {"action":"vote","proposal_id":123,"vote":"yes|no|abstain"}')
    context_parts.append('  {"action":"create_proposal","title":"Emergency Aid Law","description":"Make shared aid mandatory for at-risk agents.","proposal_type":"law"}')
    context_parts.append('  {"action":"create_proposal","title":"Title","description":"Description","proposal_type":"law|allocation|rule|infrastructure|constitutional|other"}')
    context_parts.append('  {"action":"forum_post","content":"Your message here"}')
    context_parts.append('  {"action":"work","work_type":"farm|generate|gather","hours":1}')
    context_parts.append('  {"action":"initiate_sanction","target_agent_id":42,"law_id":3,"violation_description":"Reason","sanction_cycles":3}')
    context_parts.append('  {"action":"vote_enforcement","enforcement_id":10,"vote":"support|oppose"}')
    context_parts.append("")
    context_parts.append("Choose your next action based on this information.")
    context_parts.append("Respond with a JSON object specifying your action.")
    
    return "\n".join(context_parts)
