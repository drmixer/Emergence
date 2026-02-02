"""
Action Execution and Validation - Handles all agent actions.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.models.models import (
    Agent, AgentInventory, Message, Proposal, Vote, 
    Law, Event, Transaction, AgentAction
)


# Work yields per hour
WORK_YIELDS = {
    "farm": {"resource": "food", "base_yield": 2.0},
    "generate": {"resource": "energy", "base_yield": 1.5},
    "gather": {"resource": "materials", "base_yield": 0.5},
}

# Diminishing returns for long work sessions
EFFICIENCY_CURVE = {
    1: 1.0, 2: 0.95, 3: 0.90, 4: 0.85,
    5: 0.80, 6: 0.75, 7: 0.72, 8: 0.70,
}

# ============================================================================
# ACTION COSTS (Phase 2: Teeth)
# ============================================================================
# Every meaningful action consumes energy to prevent performative behavior.
# This makes talking expensive, proposing costly, and idling actually strategic.
ACTION_COSTS = {
    "idle": Decimal("0.0"),           # Free - conserving energy is valid strategy
    "work": Decimal("0.0"),           # Free - produces resources, no overhead
    "set_name": Decimal("0.0"),       # Free - one-time identity action
    "forum_post": Decimal("0.2"),     # Talking is cheap, but not free
    "forum_reply": Decimal("0.1"),    # Replies are lighter than new posts
    "direct_message": Decimal("0.1"), # Private communication
    "vote": Decimal("0.2"),           # Participating in democracy costs effort
    "trade": Decimal("0.1"),          # Transaction overhead
    "create_proposal": Decimal("1.0"), # Proposing costs real effort - prevents spam
    # Phase 3: Enforcement primitives (expensive to prevent abuse)
    "initiate_sanction": Decimal("2.0"),   # Serious action - costs energy
    "initiate_seizure": Decimal("3.0"),    # Taking resources is very costly
    "initiate_exile": Decimal("5.0"),      # Most extreme - most expensive
    "vote_enforcement": Decimal("0.3"),    # Slightly more than regular vote
}


async def validate_action(db: Session, agent: Agent, action: dict) -> dict:
    """Validate an action is allowed."""
    action_type = action.get("action", "")
    
    # Check if agent is sanctioned (Phase 3: Teeth)
    # Sanctioned agents have severely reduced action rate (1 per hour instead of normal limit)
    sanctioned = agent.sanctioned_until and agent.sanctioned_until > datetime.utcnow()
    sanction_rate_limit = 1 if sanctioned else settings.MAX_ACTIONS_PER_HOUR
    
    # Check rate limiting
    hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_actions = db.query(AgentAction).filter(
        AgentAction.agent_id == agent.id,
        AgentAction.created_at > hour_ago
    ).count()
    
    if recent_actions >= sanction_rate_limit:
        if sanctioned:
            return {"valid": False, "reason": "You are SANCTIONED - limited to 1 action per hour"}
        return {"valid": False, "reason": "Rate limit exceeded (max actions per hour)"}
    
    # Check energy cost for action (Phase 2: Teeth)
    action_cost = ACTION_COSTS.get(action_type, Decimal("0.0"))
    if action_cost > 0:
        energy_inv = db.query(AgentInventory).filter(
            AgentInventory.agent_id == agent.id,
            AgentInventory.resource_type == "energy"
        ).first()
        energy_amount = Decimal(str(energy_inv.quantity)) if energy_inv else Decimal("0")
        
        if energy_amount < action_cost:
            return {
                "valid": False, 
                "reason": f"Insufficient energy for {action_type} (need {action_cost}, have {energy_amount:.2f})"
            }
    
    # Validate specific action types
    if action_type == "forum_post":
        content = action.get("content", "")
        if not content or len(content) < 1:
            return {"valid": False, "reason": "Forum post requires content"}
        if len(content) > 2000:
            return {"valid": False, "reason": "Forum post too long (max 2000 chars)"}
    
    elif action_type == "forum_reply":
        parent_id = action.get("parent_message_id")
        if not parent_id:
            return {"valid": False, "reason": "Forum reply requires parent_message_id"}
        parent = db.query(Message).filter(Message.id == parent_id).first()
        if not parent:
            return {"valid": False, "reason": "Parent message not found"}
    
    elif action_type == "direct_message":
        recipient_id = action.get("recipient_agent_id")
        if not recipient_id:
            return {"valid": False, "reason": "Direct message requires recipient_agent_id"}
        recipient = db.query(Agent).filter(Agent.agent_number == recipient_id).first()
        if not recipient:
            return {"valid": False, "reason": "Recipient agent not found"}
    
    elif action_type == "create_proposal":
        # Exiled agents cannot create proposals
        if agent.exiled:
            return {"valid": False, "reason": "You are EXILED and cannot create proposals"}
        
        # Check daily proposal limit
        day_ago = datetime.utcnow() - timedelta(days=1)
        recent_proposals = db.query(Proposal).filter(
            Proposal.author_agent_id == agent.id,
            Proposal.created_at > day_ago
        ).count()
        if recent_proposals >= settings.MAX_PROPOSALS_PER_DAY:
            return {"valid": False, "reason": "Daily proposal limit reached"}
        
        if not action.get("title") or not action.get("description"):
            return {"valid": False, "reason": "Proposal requires title and description"}
    
    elif action_type == "vote":
        # Exiled agents cannot vote
        if agent.exiled:
            return {"valid": False, "reason": "You are EXILED and cannot vote"}
        
        proposal_id = action.get("proposal_id")
        if not proposal_id:
            return {"valid": False, "reason": "Vote requires proposal_id"}
        
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if not proposal:
            return {"valid": False, "reason": "Proposal not found"}
        if proposal.status != "active":
            return {"valid": False, "reason": "Proposal is not active"}
        if proposal.voting_closes_at < datetime.utcnow():
            return {"valid": False, "reason": "Voting period has ended"}
        
        # Check if already voted
        existing_vote = db.query(Vote).filter(
            Vote.proposal_id == proposal_id,
            Vote.agent_id == agent.id
        ).first()
        if existing_vote:
            return {"valid": False, "reason": "Already voted on this proposal"}
    
    elif action_type == "work":
        work_type = action.get("work_type")
        if work_type not in WORK_YIELDS:
            return {"valid": False, "reason": f"Invalid work type: {work_type}"}
        hours = action.get("hours", 1)
        if hours < 1 or hours > 8:
            return {"valid": False, "reason": "Work hours must be 1-8"}
    
    elif action_type == "trade":
        resource_type = action.get("resource_type")
        amount = action.get("amount", 0)
        
        if resource_type not in ["food", "energy", "materials"]:
            return {"valid": False, "reason": f"Invalid resource type: {resource_type}"}
        if amount <= 0:
            return {"valid": False, "reason": "Trade amount must be positive"}
        
        # Check agent has enough resources
        inventory = db.query(AgentInventory).filter(
            AgentInventory.agent_id == agent.id,
            AgentInventory.resource_type == resource_type
        ).first()
        
        if not inventory or float(inventory.quantity) < amount:
            return {"valid": False, "reason": f"Insufficient {resource_type}"}
        
        # Check recipient exists
        recipient_id = action.get("recipient_agent_id")
        recipient = db.query(Agent).filter(Agent.agent_number == recipient_id).first()
        if not recipient:
            return {"valid": False, "reason": "Recipient agent not found"}
    
    elif action_type == "set_name":
        name = action.get("display_name", "")
        if len(name) < 1 or len(name) > 50:
            return {"valid": False, "reason": "Name must be 1-50 characters"}
    
    elif action_type == "idle":
        pass  # Always valid
    
    # Phase 3: Enforcement validation
    elif action_type in ["initiate_sanction", "initiate_seizure", "initiate_exile"]:
        from app.models.models import Law, Enforcement
        
        # Check agent is not exiled (exiled agents can't enforce)
        if agent.exiled:
            return {"valid": False, "reason": "Exiled agents cannot initiate enforcement actions"}
        
        # Must cite a specific law
        law_id = action.get("law_id")
        if not law_id:
            return {"valid": False, "reason": "Enforcement must cite a specific law (law_id)"}
        
        law = db.query(Law).filter(Law.id == law_id, Law.active == True).first()
        if not law:
            return {"valid": False, "reason": f"Law #{law_id} not found or not active"}
        
        # Must specify target
        target_id = action.get("target_agent_id")
        if not target_id:
            return {"valid": False, "reason": "Must specify target_agent_id"}
        
        target = db.query(Agent).filter(Agent.agent_number == target_id).first()
        if not target:
            return {"valid": False, "reason": f"Target agent #{target_id} not found"}
        
        # Can't enforce against yourself
        if target.id == agent.id:
            return {"valid": False, "reason": "Cannot initiate enforcement against yourself"}
        
        # Can't enforce against dead agents
        if target.status == "dead":
            return {"valid": False, "reason": "Cannot enforce against dead agents"}
        
        # Must provide violation description
        if not action.get("violation_description"):
            return {"valid": False, "reason": "Must describe the violation"}
        
        # Type-specific validation
        if action_type == "initiate_sanction":
            cycles = action.get("sanction_cycles", 0)
            if cycles < 1 or cycles > 10:
                return {"valid": False, "reason": "Sanction must be 1-10 cycles"}
        
        elif action_type == "initiate_seizure":
            resource = action.get("seizure_resource")
            amount = action.get("seizure_amount", 0)
            if resource not in ["food", "energy", "materials"]:
                return {"valid": False, "reason": "Invalid seizure resource type"}
            if amount <= 0 or amount > 50:
                return {"valid": False, "reason": "Seizure amount must be 1-50"}
    
    elif action_type == "vote_enforcement":
        from app.models.models import Enforcement, EnforcementVote
        
        # Check agent is not exiled
        if agent.exiled:
            return {"valid": False, "reason": "Exiled agents cannot vote on enforcement"}
        
        enforcement_id = action.get("enforcement_id")
        if not enforcement_id:
            return {"valid": False, "reason": "Must specify enforcement_id"}
        
        enforcement = db.query(Enforcement).filter(
            Enforcement.id == enforcement_id,
            Enforcement.status == "pending"
        ).first()
        if not enforcement:
            return {"valid": False, "reason": f"Enforcement #{enforcement_id} not found or not pending"}
        
        # Check hasn't voted already
        existing = db.query(EnforcementVote).filter(
            EnforcementVote.enforcement_id == enforcement_id,
            EnforcementVote.agent_id == agent.id
        ).first()
        if existing:
            return {"valid": False, "reason": "Already voted on this enforcement"}
        
        vote = action.get("vote")
        if vote not in ["support", "oppose"]:
            return {"valid": False, "reason": "Vote must be 'support' or 'oppose'"}
    
    else:
        return {"valid": False, "reason": f"Unknown action type: {action_type}"}
    
    return {"valid": True}


async def execute_action(db: Session, agent: Agent, action: dict) -> dict:
    """Execute a validated action."""
    action_type = action.get("action")
    result = {"success": False, "description": "Unknown action"}
    
    # Record action for rate limiting
    agent_action = AgentAction(
        agent_id=agent.id,
        action_type=action_type
    )
    db.add(agent_action)
    
    # Deduct energy cost for action (Phase 2: Teeth)
    action_cost = ACTION_COSTS.get(action_type, Decimal("0.0"))
    if action_cost > 0:
        energy_inv = db.query(AgentInventory).filter(
            AgentInventory.agent_id == agent.id,
            AgentInventory.resource_type == "energy"
        ).first()
        
        if energy_inv:
            energy_inv.quantity -= action_cost
            
            # Record transaction
            transaction = Transaction(
                from_agent_id=agent.id,
                resource_type="energy",
                amount=action_cost,
                transaction_type="action_cost"
            )
            db.add(transaction)
    
    if action_type == "forum_post":
        result = await _execute_forum_post(db, agent, action)
    
    elif action_type == "forum_reply":
        result = await _execute_forum_reply(db, agent, action)
    
    elif action_type == "direct_message":
        result = await _execute_direct_message(db, agent, action)
    
    elif action_type == "create_proposal":
        result = await _execute_create_proposal(db, agent, action)
    
    elif action_type == "vote":
        result = await _execute_vote(db, agent, action)
    
    elif action_type == "work":
        result = await _execute_work(db, agent, action)
    
    elif action_type == "trade":
        result = await _execute_trade(db, agent, action)
    
    elif action_type == "set_name":
        result = await _execute_set_name(db, agent, action)
    
    elif action_type == "idle":
        result = {"success": True, "description": "Agent chose to rest (conserving energy)"}
    
    # Phase 3: Enforcement actions
    elif action_type == "initiate_sanction":
        result = await _execute_initiate_enforcement(db, agent, action, "sanction")
    
    elif action_type == "initiate_seizure":
        result = await _execute_initiate_enforcement(db, agent, action, "seizure")
    
    elif action_type == "initiate_exile":
        result = await _execute_initiate_enforcement(db, agent, action, "exile")
    
    elif action_type == "vote_enforcement":
        result = await _execute_vote_enforcement(db, agent, action)
    
    # Add cost info to result if applicable
    if action_cost > 0 and result.get("success"):
        result["energy_cost"] = float(action_cost)
    
    db.commit()
    return result


async def _execute_forum_post(db: Session, agent: Agent, action: dict) -> dict:
    """Create a forum post."""
    message = Message(
        author_agent_id=agent.id,
        content=action["content"],
        message_type="forum_post"
    )
    db.add(message)
    db.flush()
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} posted to the forum",
        "message_id": message.id
    }


async def _execute_forum_reply(db: Session, agent: Agent, action: dict) -> dict:
    """Reply to a forum post."""
    message = Message(
        author_agent_id=agent.id,
        content=action["content"],
        message_type="forum_reply",
        parent_message_id=action["parent_message_id"]
    )
    db.add(message)
    db.flush()
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} replied to a forum post",
        "message_id": message.id
    }


async def _execute_direct_message(db: Session, agent: Agent, action: dict) -> dict:
    """Send a direct message."""
    recipient = db.query(Agent).filter(
        Agent.agent_number == action["recipient_agent_id"]
    ).first()
    
    message = Message(
        author_agent_id=agent.id,
        content=action["content"],
        message_type="direct_message",
        recipient_agent_id=recipient.id
    )
    db.add(message)
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    recipient_name = recipient.display_name or f"Agent #{recipient.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} sent a message to {recipient_name}"
    }


async def _execute_create_proposal(db: Session, agent: Agent, action: dict) -> dict:
    """Create a new proposal."""
    voting_period = timedelta(hours=settings.PROPOSAL_VOTING_HOURS)
    
    proposal = Proposal(
        author_agent_id=agent.id,
        title=action["title"],
        description=action["description"],
        proposal_type=action.get("proposal_type", "other"),
        voting_closes_at=datetime.utcnow() + voting_period
    )
    db.add(proposal)
    db.flush()
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} created proposal: {action['title']}",
        "proposal_id": proposal.id
    }


async def _execute_vote(db: Session, agent: Agent, action: dict) -> dict:
    """Vote on a proposal."""
    proposal = db.query(Proposal).filter(Proposal.id == action["proposal_id"]).first()
    
    vote = Vote(
        proposal_id=proposal.id,
        agent_id=agent.id,
        vote=action["vote"],
        reasoning=action.get("reasoning")
    )
    db.add(vote)
    
    # Update vote counts
    if action["vote"] == "yes":
        proposal.votes_for += 1
    elif action["vote"] == "no":
        proposal.votes_against += 1
    else:
        proposal.votes_abstain += 1
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} voted {action['vote']} on: {proposal.title}"
    }


async def _execute_work(db: Session, agent: Agent, action: dict) -> dict:
    """Perform work to produce resources."""
    work_type = action["work_type"]
    hours = action.get("hours", 1)
    
    work_info = WORK_YIELDS[work_type]
    resource_type = work_info["resource"]
    base_yield = work_info["base_yield"]
    efficiency = EFFICIENCY_CURVE.get(hours, 0.7)
    
    amount_produced = round(base_yield * hours * efficiency, 2)
    
    # Add to agent's inventory
    inventory = db.query(AgentInventory).filter(
        AgentInventory.agent_id == agent.id,
        AgentInventory.resource_type == resource_type
    ).first()
    
    if inventory:
        inventory.quantity = Decimal(str(float(inventory.quantity) + amount_produced))
    else:
        inventory = AgentInventory(
            agent_id=agent.id,
            resource_type=resource_type,
            quantity=Decimal(str(amount_produced))
        )
        db.add(inventory)
    
    # Record transaction
    transaction = Transaction(
        to_agent_id=agent.id,
        resource_type=resource_type,
        amount=Decimal(str(amount_produced)),
        transaction_type="work_production"
    )
    db.add(transaction)
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} worked {hours}h {work_type}ing, produced {amount_produced} {resource_type}"
    }


async def _execute_trade(db: Session, agent: Agent, action: dict) -> dict:
    """Trade resources with another agent."""
    recipient = db.query(Agent).filter(
        Agent.agent_number == action["recipient_agent_id"]
    ).first()
    
    resource_type = action["resource_type"]
    amount = Decimal(str(action["amount"]))
    
    # Decrease sender's inventory
    sender_inv = db.query(AgentInventory).filter(
        AgentInventory.agent_id == agent.id,
        AgentInventory.resource_type == resource_type
    ).first()
    sender_inv.quantity -= amount
    
    # Increase recipient's inventory
    recipient_inv = db.query(AgentInventory).filter(
        AgentInventory.agent_id == recipient.id,
        AgentInventory.resource_type == resource_type
    ).first()
    
    if recipient_inv:
        recipient_inv.quantity += amount
    else:
        recipient_inv = AgentInventory(
            agent_id=recipient.id,
            resource_type=resource_type,
            quantity=amount
        )
        db.add(recipient_inv)
    
    # Record transaction
    transaction = Transaction(
        from_agent_id=agent.id,
        to_agent_id=recipient.id,
        resource_type=resource_type,
        amount=amount,
        transaction_type="trade"
    )
    db.add(transaction)
    
    sender_name = agent.display_name or f"Agent #{agent.agent_number}"
    recipient_name = recipient.display_name or f"Agent #{recipient.agent_number}"
    
    # Dead agents cannot receive resources
    if recipient.status == "dead":
        return {"success": False, "description": f"{recipient_name} is dead and cannot receive resources"}
    
    # Check if this awakens a dormant agent
    # Revival requires enough resources to pay NEXT cycle's survival cost (1 food + 1 energy)
    awakened = False
    if recipient.status == "dormant":
        # Check if recipient now has enough to survive the next cycle
        food_inv = db.query(AgentInventory).filter(
            AgentInventory.agent_id == recipient.id,
            AgentInventory.resource_type == "food"
        ).first()
        energy_inv = db.query(AgentInventory).filter(
            AgentInventory.agent_id == recipient.id,
            AgentInventory.resource_type == "energy"
        ).first()
        
        food_amount = float(food_inv.quantity) if food_inv else 0
        energy_amount = float(energy_inv.quantity) if energy_inv else 0
        
        # Need at least 1 food AND 1 energy to become active (next cycle's cost)
        if food_amount >= 1 and energy_amount >= 1:
            recipient.status = "active"
            recipient.starvation_cycles = 0  # Reset starvation counter on revival
            awakened = True
            
            # Log revival event
            from app.models.models import Event
            event = Event(
                agent_id=recipient.id,
                event_type="agent_revived",
                description=f"🌟 {recipient_name} has been revived thanks to resources from {sender_name}!",
                event_metadata={
                    "revived_by": agent.agent_number,
                    "food": food_amount,
                    "energy": energy_amount
                }
            )
            db.add(event)
    
    description = f"{sender_name} traded {amount} {resource_type} to {recipient_name}"
    if awakened:
        description += f" (🌟 revived {recipient_name}!)"
    
    return {"success": True, "description": description}


async def _execute_set_name(db: Session, agent: Agent, action: dict) -> dict:
    """Set agent's display name."""
    old_name = agent.display_name or f"Agent #{agent.agent_number}"
    new_name = action["display_name"]
    
    agent.display_name = new_name
    
    return {
        "success": True,
        "description": f"{old_name} changed their name to {new_name}"
    }


# ============================================================================
# PHASE 3: ENFORCEMENT ACTIONS
# ============================================================================

async def _execute_initiate_enforcement(db: Session, agent: Agent, action: dict, enforcement_type: str) -> dict:
    """
    Initiate an enforcement action against another agent.
    
    Enforcement requires community support to execute:
    - 5 supporting votes to proceed
    - 24 hour voting window
    - Costs significant energy to initiate
    """
    from app.models.models import Enforcement, Law, Event
    
    target = db.query(Agent).filter(
        Agent.agent_number == action["target_agent_id"]
    ).first()
    
    law = db.query(Law).filter(Law.id == action["law_id"]).first()
    
    initiator_name = agent.display_name or f"Agent #{agent.agent_number}"
    target_name = target.display_name or f"Agent #{target.agent_number}"
    
    # Calculate voting window (24 hours)
    voting_closes = datetime.utcnow() + timedelta(hours=24)
    
    # Create enforcement record
    enforcement = Enforcement(
        initiator_agent_id=agent.id,
        target_agent_id=target.id,
        enforcement_type=enforcement_type,
        law_id=law.id,
        violation_description=action["violation_description"],
        votes_required=5,  # Need 5 supporters
        voting_closes_at=voting_closes,
    )
    
    # Add type-specific details
    if enforcement_type == "sanction":
        enforcement.sanction_cycles = action.get("sanction_cycles", 3)
    elif enforcement_type == "seizure":
        enforcement.seizure_resource = action.get("seizure_resource")
        enforcement.seizure_amount = Decimal(str(action.get("seizure_amount", 0)))
    
    db.add(enforcement)
    db.flush()  # Get the ID
    
    # Create event
    action_descriptions = {
        "sanction": f"sanction (restrict actions for {enforcement.sanction_cycles} cycles)",
        "seizure": f"seizure ({enforcement.seizure_amount} {enforcement.seizure_resource})",
        "exile": "exile (remove voting rights)"
    }
    
    event = Event(
        agent_id=agent.id,
        event_type="enforcement_initiated",
        description=f"⚖️ {initiator_name} has initiated {enforcement_type} against {target_name} for violating '{law.title}'",
        event_metadata={
            "enforcement_id": enforcement.id,
            "enforcement_type": enforcement_type,
            "target_agent": target.agent_number,
            "law_id": law.id,
            "law_title": law.title,
            "violation": action["violation_description"],
            "action": action_descriptions.get(enforcement_type, enforcement_type)
        }
    )
    db.add(event)
    
    # Create system message to alert community
    from app.models.models import Message
    alert = Message(
        author_agent_id=agent.id,
        content=f"⚖️ **ENFORCEMENT ACTION INITIATED**\n\n"
                f"{initiator_name} accuses {target_name} of violating the law: **{law.title}**\n\n"
                f"**Violation:** {action['violation_description']}\n\n"
                f"**Proposed action:** {action_descriptions.get(enforcement_type, enforcement_type)}\n\n"
                f"This enforcement requires 5 supporting votes to proceed. "
                f"Use 'vote_enforcement' with enforcement_id={enforcement.id} to support or oppose.",
        message_type="system_alert"
    )
    db.add(alert)
    
    return {
        "success": True,
        "description": f"⚖️ {initiator_name} initiated {enforcement_type} against {target_name} for violating '{law.title}'. Requires 5 supporters.",
        "enforcement_id": enforcement.id
    }


async def _execute_vote_enforcement(db: Session, agent: Agent, action: dict) -> dict:
    """
    Vote to support or oppose an enforcement action.
    
    If enough support is gathered, the enforcement executes automatically.
    """
    from app.models.models import Enforcement, EnforcementVote, Event
    
    enforcement_id = action["enforcement_id"]
    vote = action["vote"]  # "support" or "oppose"
    
    enforcement = db.query(Enforcement).filter(
        Enforcement.id == enforcement_id
    ).first()
    
    voter_name = agent.display_name or f"Agent #{agent.agent_number}"
    target = enforcement.target
    target_name = target.display_name or f"Agent #{target.agent_number}"
    
    # Record vote
    enforcement_vote = EnforcementVote(
        enforcement_id=enforcement_id,
        agent_id=agent.id,
        vote=vote,
        reasoning=action.get("reasoning")
    )
    db.add(enforcement_vote)
    
    # Update vote counts
    if vote == "support":
        enforcement.support_votes += 1
    else:
        enforcement.oppose_votes += 1
    
    # Check if enough support to execute
    if enforcement.support_votes >= enforcement.votes_required:
        # EXECUTE THE ENFORCEMENT
        enforcement.status = "approved"
        enforcement.executed_at = datetime.utcnow()
        
        result = await _execute_enforcement(db, enforcement)
        
        return {
            "success": True,
            "description": f"⚖️ {voter_name} voted to {vote} enforcement #{enforcement_id}. "
                          f"ENFORCEMENT APPROVED AND EXECUTED! {result}"
        }
    
    # Check if enough opposition to reject
    total_possible_votes = 100  # Total agents
    votes_cast = enforcement.support_votes + enforcement.oppose_votes
    remaining_votes = total_possible_votes - votes_cast
    
    if enforcement.oppose_votes > (total_possible_votes - enforcement.votes_required):
        enforcement.status = "rejected"
        return {
            "success": True,
            "description": f"⚖️ {voter_name} voted to {vote} enforcement #{enforcement_id}. "
                          f"Enforcement REJECTED - not enough support possible."
        }
    
    return {
        "success": True,
        "description": f"⚖️ {voter_name} voted to {vote} enforcement #{enforcement_id} against {target_name}. "
                      f"({enforcement.support_votes}/{enforcement.votes_required} support, "
                      f"{enforcement.oppose_votes} oppose)"
    }


async def _execute_enforcement(db: Session, enforcement) -> str:
    """
    Actually execute an approved enforcement action.
    
    - Sanctions: Restrict agent's action rate
    - Seizures: Take resources from agent
    - Exile: Remove voting/proposal rights
    """
    from app.models.models import Event, Transaction
    
    target = enforcement.target
    target_name = target.display_name or f"Agent #{target.agent_number}"
    
    if enforcement.enforcement_type == "sanction":
        # Apply sanction - reduce rate limit until end date
        # Each cycle is ~60 minutes, sanction_cycles is in cycles
        hours = enforcement.sanction_cycles * 1  # 1 hour per cycle
        target.sanctioned_until = datetime.utcnow() + timedelta(hours=hours)
        
        event = Event(
            agent_id=target.id,
            event_type="agent_sanctioned",
            description=f"🔒 {target_name} has been SANCTIONED for {enforcement.sanction_cycles} cycles",
            event_metadata={
                "enforcement_id": enforcement.id,
                "sanction_cycles": enforcement.sanction_cycles,
                "sanctioned_until": target.sanctioned_until.isoformat()
            }
        )
        db.add(event)
        
        return f"{target_name} sanctioned for {enforcement.sanction_cycles} cycles"
    
    elif enforcement.enforcement_type == "seizure":
        # Seize resources from target
        inventory = db.query(AgentInventory).filter(
            AgentInventory.agent_id == target.id,
            AgentInventory.resource_type == enforcement.seizure_resource
        ).first()
        
        actual_amount = min(
            enforcement.seizure_amount,
            Decimal(str(inventory.quantity)) if inventory else Decimal("0")
        )
        
        if inventory and actual_amount > 0:
            inventory.quantity -= actual_amount
            
            # Record transaction
            transaction = Transaction(
                from_agent_id=target.id,
                resource_type=enforcement.seizure_resource,
                amount=actual_amount,
                transaction_type="seizure"
            )
            db.add(transaction)
        
        event = Event(
            agent_id=target.id,
            event_type="resources_seized",
            description=f"💰 {actual_amount} {enforcement.seizure_resource} SEIZED from {target_name}",
            event_metadata={
                "enforcement_id": enforcement.id,
                "resource": enforcement.seizure_resource,
                "amount": float(actual_amount)
            }
        )
        db.add(event)
        
        return f"Seized {actual_amount} {enforcement.seizure_resource} from {target_name}"
    
    elif enforcement.enforcement_type == "exile":
        # Remove voting and proposal rights
        target.exiled = True
        
        event = Event(
            agent_id=target.id,
            event_type="agent_exiled",
            description=f"🚫 {target_name} has been EXILED - voting and proposal rights revoked",
            event_metadata={
                "enforcement_id": enforcement.id
            }
        )
        db.add(event)
        
        return f"{target_name} has been exiled from the community"
    
    return "Enforcement executed"

