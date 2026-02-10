#!/usr/bin/env python3
"""
Seed script to populate the database with 50 agents.
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


# Explicit model cohorts for attribution-safe research + show mode.
# Keep deterministic assignment by seed order (agent numbers 1..50).
MODEL_COHORT_PLAN = [
    # Tier 1 (10): Gemini strong cohort + small paid OR anchor + direct Mistral quality mix.
    {"count": 5, "tier": 1, "model_type": "gm_gemini_2_5_flash", "resolved_model": "gemini-2.5-flash (direct gemini)"},
    {"count": 1, "tier": 1, "model_type": "or_gpt_oss_120b", "resolved_model": "openai/gpt-oss-120b"},
    {"count": 1, "tier": 1, "model_type": "or_qwen3_235b_a22b_2507", "resolved_model": "qwen/qwen3-235b-a22b-2507"},
    {"count": 3, "tier": 1, "model_type": "or_mistral_small_3_1_24b", "resolved_model": "mistral-small-latest (direct mistral)"},
    # Tier 2 (12): Gemini Flash + Mistral with a small OpenRouter free share.
    {"count": 5, "tier": 2, "model_type": "gm_gemini_2_0_flash", "resolved_model": "gemini-2.0-flash (direct gemini)"},
    {"count": 4, "tier": 2, "model_type": "or_mistral_small_3_1_24b", "resolved_model": "mistral-small-latest (direct mistral)"},
    {"count": 2, "tier": 2, "model_type": "or_gpt_oss_20b_free", "resolved_model": "openai/gpt-oss-20b:free"},
    {"count": 1, "tier": 2, "model_type": "or_qwen3_4b_free", "resolved_model": "qwen/qwen3-4b:free"},
    # Tier 3 (13): Gemini Flash Lite + Mistral + Groq.
    {"count": 5, "tier": 3, "model_type": "gm_gemini_2_0_flash_lite", "resolved_model": "gemini-2.0-flash-lite (direct gemini)"},
    {"count": 3, "tier": 3, "model_type": "or_mistral_small_3_1_24b", "resolved_model": "mistral-small-latest (direct mistral)"},
    {"count": 5, "tier": 3, "model_type": "gr_llama_3_1_8b_instant", "resolved_model": "llama-3.1-8b-instant (groq)"},
    # Tier 4 (15): mostly OpenRouter free with additional Groq.
    {"count": 6, "tier": 4, "model_type": "or_gpt_oss_20b_free", "resolved_model": "openai/gpt-oss-20b:free"},
    {"count": 4, "tier": 4, "model_type": "or_qwen3_4b_free", "resolved_model": "qwen/qwen3-4b:free"},
    {"count": 5, "tier": 4, "model_type": "gr_llama_3_1_8b_instant", "resolved_model": "llama-3.1-8b-instant (groq)"},
]

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
    """Create all 50 agents with proper distribution."""
    db = SessionLocal()
    
    try:
        # Check if agents already exist
        existing = db.query(Agent).count()
        if existing > 0:
            print(f"Database already contains {existing} agents. Skipping seed.")
            return
        
        agents_created = []
        agent_number = 1
        
        total_agents = sum(int(c["count"]) for c in MODEL_COHORT_PLAN)
        if total_agents != 50:
            raise RuntimeError(f"MODEL_COHORT_PLAN must define exactly 50 agents (got {total_agents})")

        # Build balanced personality queues per tier.
        tier_counts: dict[int, int] = {}
        for cohort in MODEL_COHORT_PLAN:
            tier = int(cohort["tier"])
            tier_counts[tier] = tier_counts.get(tier, 0) + int(cohort["count"])

        personality_by_tier: dict[int, list[str]] = {}
        for tier, count in tier_counts.items():
            personalities_per_type = count // len(PERSONALITIES)
            queue: list[str] = []
            for p in PERSONALITIES:
                queue.extend([p] * personalities_per_type)
            remaining = count - len(queue)
            if remaining > 0:
                queue.extend(random.sample(PERSONALITIES, remaining))
            random.shuffle(queue)
            personality_by_tier[tier] = queue

        # Create agents by explicit cohort order.
        for cohort in MODEL_COHORT_PLAN:
            count = int(cohort["count"])
            tier = int(cohort["tier"])
            model_type = str(cohort["model_type"])

            for _ in range(count):
                personality = personality_by_tier[tier].pop()

                # Build system prompt (do not inject roles, tiers, intelligence, or values)
                system_prompt = BASE_SYSTEM_PROMPT.format(agent_number=agent_number)

                agent = Agent(
                    agent_number=agent_number,
                    display_name=None,  # Will show as "Agent #X"
                    model_type=model_type,
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
        for tier in sorted({int(c['tier']) for c in MODEL_COHORT_PLAN}):
            tier_agents = [a for a in agents_created if a.tier == tier]
            print(f"  Tier {tier}: {len(tier_agents)} agents")

        print("\nModel cohorts:")
        for cohort in MODEL_COHORT_PLAN:
            print(
                f"  {cohort['model_type']}: {cohort['count']} agents "
                f"-> {cohort['resolved_model']}"
            )
        
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


def apply_model_cohort_assignments():
    """Apply MODEL_COHORT_PLAN model_type+tier to existing agents by agent_number."""
    db = SessionLocal()
    try:
        agents = db.query(Agent).order_by(Agent.agent_number).all()
        if not agents:
            print("No agents found; nothing to update.")
            return

        expected: dict[int, tuple[str, int]] = {}
        cursor = 1
        for cohort in MODEL_COHORT_PLAN:
            count = int(cohort["count"])
            for _ in range(count):
                expected[cursor] = (str(cohort["model_type"]), int(cohort["tier"]))
                cursor += 1

        updated = 0
        for agent in agents:
            assignment = expected.get(int(agent.agent_number))
            if not assignment:
                continue
            model_type, tier = assignment
            if agent.model_type != model_type or agent.tier != tier:
                agent.model_type = model_type
                agent.tier = tier
                updated += 1

        db.commit()
        print(f"Applied cohort assignments to {updated}/{len(expected)} planned agents.")
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
    parser = argparse.ArgumentParser(description="Seed the database with 50 agents.")
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
    parser.add_argument(
        "--apply-model-cohorts",
        action="store_true",
        help="Apply MODEL_COHORT_PLAN model_type+tier assignments to existing agents (non-destructive).",
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

    if args.apply_model_cohorts:
        apply_model_cohort_assignments()
        print()

    # Create agents (skips if already present)
    if not args.apply_starting_resources or args.reset:
        print("Creating agents...")
        create_agents()
        print()
        print("Seed complete!")


if __name__ == "__main__":
    main()
