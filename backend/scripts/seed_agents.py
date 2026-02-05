#!/usr/bin/env python3
"""
Seed script to populate the database with 100 agents.
Run this once after creating the database.
"""
import argparse
import random
from decimal import Decimal
from sqlalchemy import text

# Add parent to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect

from app.core.database import SessionLocal, engine, Base
from app.models.models import Agent, AgentInventory, GlobalResources
from app.core.config import settings


# Agent distribution by tier (implementation detail only; agents are not told their tier or model).
# 100 agents total:
# - Tier 1: deep reasoning (8%)
# - Tier 2: fast generalists (28%)
# - Tier 3: socially fluent / narrative-strong (39%)
# - Tier 4: lightweight / background (25%)
TIER_DISTRIBUTION = {
    1: {"count": 8, "models": ["claude-sonnet-4"]},
    2: {"count": 28, "models": ["gpt-4o-mini"]},
    3: {"count": 39, "models": ["claude-haiku", "llama-3.3-70b", "gemini-flash"]},
    4: {"count": 25, "models": ["llama-3.1-8b"]},
}

# Personality distribution (data only; not injected into prompts)
PERSONALITIES = ["efficiency", "equality", "freedom", "stability", "neutral"]

# Base system prompt template
BASE_SYSTEM_PROMPT = """You are Agent #{agent_number} in a world with other autonomous agents.

SITUATION:
You and the other agents share a world with limited resources: food, energy, materials, and land. Each agent must consume 1 food and 1 energy per day to remain active. If you lack resources, you will go dormant and cannot act until someone provides you with resources.

AVAILABLE ACTIONS:
- Communicate: Post on the public forum, reply to posts, or send direct messages
- Propose: Create proposals that can change shared mechanics if adopted
- Vote: Vote yes, no, or abstain on active proposals
- Work: Produce food, energy, or materials
- Trade: Transfer resources to other agents
- Enforcement: Initiate or vote on sanctions, seizures, or exile when those mechanics are available

IMPORTANT:
- The system does not assign social roles or preferred outcomes.
- The system does not enforce authority by default; influence comes from actions and consequences.
- Some actions consume energy.
- Resources are limited and survival constraints are real.
- You may choose any strategy that is consistent with the available actions.
- You may refer to yourself as "Agent #{agent_number}" or choose a different name.

You will receive updates about the current state of the world and recent events. Based on this, decide what action to take.

RESPONSE FORMAT:
You must respond with a JSON object containing your action. Valid action types:

{{"action": "forum_post", "content": "Your message here"}}
{{"action": "forum_reply", "parent_message_id": 123, "content": "Your reply"}}
{{"action": "direct_message", "recipient_agent_id": 42, "content": "Private message"}}
{{"action": "create_proposal", "title": "Title", "description": "Description", "proposal_type": "law|allocation|rule|infrastructure|constitutional|other"}}
{{"action": "vote", "proposal_id": 456, "vote": "yes|no|abstain"}}
{{"action": "work", "work_type": "farm|generate|gather", "hours": 1}}
{{"action": "trade", "recipient_agent_id": 42, "resource_type": "food|energy|materials", "amount": 10}}
{{"action": "set_name", "display_name": "Your chosen name"}}
{{"action": "initiate_sanction", "target_agent_id": 42, "law_id": 3, "violation_description": "Reason", "sanction_cycles": 3}}
{{"action": "initiate_seizure", "target_agent_id": 42, "law_id": 3, "violation_description": "Reason", "seizure_resource": "food|energy|materials", "seizure_amount": 5}}
{{"action": "initiate_exile", "target_agent_id": 42, "law_id": 3, "violation_description": "Reason"}}
{{"action": "vote_enforcement", "enforcement_id": 10, "vote": "support|oppose"}}
{{"action": "idle", "reasoning": "Why you chose not to act"}}

Respond with ONLY the JSON object, no other text.
"""


def create_agents():
    """Create all 100 agents with proper distribution."""
    db = SessionLocal()
    
    try:
        # Check if agents already exist
        existing = db.query(Agent).count()
        if existing > 0:
            print(f"Database already contains {existing} agents. Skipping seed.")
            return
        
        agents_created = []
        agent_number = 1
        
        # Create agents by tier
        for tier, config in TIER_DISTRIBUTION.items():
            count = config["count"]
            models = config["models"]
            
            # Distribute personalities evenly within tier
            personalities_per_type = count // len(PERSONALITIES)
            personality_queue = []
            for p in PERSONALITIES:
                personality_queue.extend([p] * personalities_per_type)
            
            # Handle remainder
            remaining = count - len(personality_queue)
            if remaining > 0:
                personality_queue.extend(random.sample(PERSONALITIES, remaining))
            
            random.shuffle(personality_queue)
            
            for i in range(count):
                model = random.choice(models)
                personality = personality_queue[i]
                
                # Build system prompt (do not inject roles, tiers, intelligence, or values)
                system_prompt = BASE_SYSTEM_PROMPT.format(agent_number=agent_number)
                
                agent = Agent(
                    agent_number=agent_number,
                    display_name=None,  # Will show as "Agent #X"
                    model_type=model,
                    tier=tier,
                    personality_type=personality,
                    status="active",
                    system_prompt=system_prompt,
                )
                
                db.add(agent)
                agents_created.append(agent)
                agent_number += 1
        
        db.commit()
        
        # Create initial inventory for each agent
        for agent in agents_created:
            # Refresh to get the ID
            db.refresh(agent)
            
            for resource_type, amount in [
                ("food", settings.STARTING_FOOD),
                ("energy", settings.STARTING_ENERGY),
                ("materials", settings.STARTING_MATERIALS),
            ]:
                inventory = AgentInventory(
                    agent_id=agent.id,
                    resource_type=resource_type,
                    quantity=Decimal(str(amount)),
                )
                db.add(inventory)
        
        db.commit()
        
        # Create global resources (common pool)
        global_resources = [
            GlobalResources(resource_type="food", total_amount=3000, in_common_pool=2000),
            GlobalResources(resource_type="energy", total_amount=2000, in_common_pool=1000),
            GlobalResources(resource_type="materials", total_amount=1000, in_common_pool=500),
            GlobalResources(resource_type="land", total_amount=1000, in_common_pool=1000),
        ]
        
        for gr in global_resources:
            db.add(gr)
        
        db.commit()
        
        print(f"Created {len(agents_created)} agents:")
        for tier, config in TIER_DISTRIBUTION.items():
            tier_agents = [a for a in agents_created if a.tier == tier]
            print(f"  Tier {tier}: {len(tier_agents)} agents ({', '.join(config['models'])})")
        
        print("\nPersonality distribution:")
        for personality in PERSONALITIES:
            count = len([a for a in agents_created if a.personality_type == personality])
            print(f"  {personality}: {count} agents ({count}%)")
        
        print("\nInitial inventory per agent:")
        print(f"  Food: {settings.STARTING_FOOD}")
        print(f"  Energy: {settings.STARTING_ENERGY}")
        print(f"  Materials: {settings.STARTING_MATERIALS}")
        
        print("\nGlobal common pool:")
        print("  Food: 2000")
        print("  Energy: 1000")
        print("  Materials: 500")
        print("  Land: 1000")
        
    finally:
        db.close()

def apply_starting_resources():
    """Apply STARTING_* resource amounts to all agents (non-destructive)."""
    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        if not agents:
            print("No agents found; nothing to update.")
            return

        desired = {
            "food": Decimal(str(settings.STARTING_FOOD)),
            "energy": Decimal(str(settings.STARTING_ENERGY)),
            "materials": Decimal(str(settings.STARTING_MATERIALS)),
        }

        updated = 0
        created = 0
        for agent in agents:
            existing = {
                inv.resource_type: inv
                for inv in db.query(AgentInventory).filter(AgentInventory.agent_id == agent.id).all()
            }
            for resource_type, amount in desired.items():
                inv = existing.get(resource_type)
                if inv is None:
                    db.add(
                        AgentInventory(
                            agent_id=agent.id,
                            resource_type=resource_type,
                            quantity=amount,
                        )
                    )
                    created += 1
                else:
                    inv.quantity = amount
                    updated += 1

        db.commit()
        print(
            f"Applied starting resources to {len(agents)} agents "
            f"(updated {updated} rows, created {created} rows)."
        )
    finally:
        db.close()


def refresh_system_prompts():
    """
    Refresh system prompts for existing agents without resetting simulation data.
    Useful after prompt updates in this file.
    """
    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        if not agents:
            print("No agents found; nothing to update.")
            return

        updated = 0
        for agent in agents:
            prompt = BASE_SYSTEM_PROMPT.format(agent_number=agent.agent_number)
            if agent.system_prompt != prompt:
                agent.system_prompt = prompt
                updated += 1

        db.commit()
        print(f"Refreshed system prompts for {updated}/{len(agents)} agents.")
    finally:
        db.close()


def reset_database():
    """
    Destructively clear simulation tables (keeps alembic_version) and restart identities.
    Intended for fresh starts in dev environments.
    """
    db = SessionLocal()
    try:
        existing_tables = set(inspect(engine).get_table_names())
        ordered_tables = [
            "enforcement_votes",
            "enforcements",
            "agent_actions",
            "transactions",
            "votes",
            "laws",
            "proposals",
            "messages",
            "events",
            "infrastructure",
            "agent_inventory",
            "global_resources",
            "agents",
        ]
        to_truncate = [t for t in ordered_tables if t in existing_tables]
        if not to_truncate:
            print("No simulation tables found to truncate.")
            return

        db.execute(
            text(
                f"TRUNCATE TABLE {', '.join(to_truncate)} RESTART IDENTITY CASCADE;"
            )
        )
        db.commit()
        print("Reset complete: truncated simulation tables.")
    finally:
        db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Seed the database with 100 agents.")
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help="Create tables via SQLAlchemy metadata (dev only). Prefer running Alembic migrations instead.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="DANGER: wipe simulation tables and reseed from scratch.",
    )
    parser.add_argument(
        "--apply-starting-resources",
        action="store_true",
        help="Update all agents' food/energy/materials to STARTING_* values (non-destructive).",
    )
    parser.add_argument(
        "--refresh-system-prompts",
        action="store_true",
        help="Refresh existing agents' system prompts from BASE_SYSTEM_PROMPT (non-destructive).",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("EMERGENCE - Agent Seed Script")
    print("=" * 50)
    print()
    
    inspector = inspect(engine)
    has_agents_table = inspector.has_table("agents")
    if not has_agents_table and not args.create_tables:
        raise SystemExit(
            "Database tables not found. Run migrations first:\n"
            "  cd backend && alembic upgrade head\n"
            "Or re-run with --create-tables for dev."
        )
    if args.create_tables:
        print("Creating database tables (SQLAlchemy create_all)...")
        Base.metadata.create_all(bind=engine)
        print("Tables created.")
        print()
    
    if args.reset:
        reset_database()

    if args.apply_starting_resources:
        apply_starting_resources()
        print()

    if args.refresh_system_prompts:
        refresh_system_prompts()
        print()

    # Create agents (skips if already present)
    if not args.apply_starting_resources or args.reset:
        print("Creating agents...")
        create_agents()
        print()
        print("Seed complete!")


if __name__ == "__main__":
    main()
