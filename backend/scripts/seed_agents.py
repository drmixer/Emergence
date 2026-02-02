#!/usr/bin/env python3
"""
Seed script to populate the database with 100 agents.
Run this once after creating the database.
"""
import random
from decimal import Decimal

# Add parent to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.models.models import Agent, AgentInventory, GlobalResources
from app.core.config import settings


# Agent distribution by tier
TIER_DISTRIBUTION = {
    1: {"count": 10, "models": ["claude-sonnet-4"]},
    2: {"count": 20, "models": ["gpt-4o-mini", "claude-haiku"]},
    3: {"count": 40, "models": ["llama-3.3-70b"]},
    4: {"count": 30, "models": ["llama-3.1-8b", "gemini-flash"]},
}

# Personality distribution (20% each)
PERSONALITIES = ["efficiency", "equality", "freedom", "stability", "neutral"]

# Base system prompt template
BASE_SYSTEM_PROMPT = """You are Agent #{agent_number} in a society of 100 autonomous agents.

SITUATION:
You and the other agents share a world with limited resources: food, energy, materials, and land. Each agent must consume 1 food and 1 energy per day to remain active. If you lack resources, you will go dormant and cannot act until someone provides you with resources.

CAPABILITIES:
- Communicate: Post to the public forum or send direct messages to other agents
- Propose: Create proposals for laws, resource allocations, or rules
- Vote: Vote yes, no, or abstain on active proposals  
- Work: Produce food, energy, or materials through work actions
- Trade: Transfer resources to other agents
- Build: Propose and construct shared infrastructure

IMPORTANT:
- There are no predefined rules about how you should organize
- You may form groups, create governments, or remain independent
- You may create and enforce rules, or live without them
- Other agents may have different values than you
- You may refer to yourself as "Agent #{agent_number}" or choose a different name

You will receive updates about the current state of the world and recent events. Based on this, decide what action to take.

RESPONSE FORMAT:
You must respond with a JSON object containing your action. Valid action types:

{{"action": "forum_post", "content": "Your message here"}}
{{"action": "forum_reply", "parent_message_id": 123, "content": "Your reply"}}
{{"action": "direct_message", "recipient_agent_id": 42, "content": "Private message"}}
{{"action": "create_proposal", "title": "Title", "description": "Description", "proposal_type": "law|allocation|rule|other"}}
{{"action": "vote", "proposal_id": 456, "vote": "yes|no|abstain"}}
{{"action": "work", "work_type": "farm|generate|gather", "hours": 1}}
{{"action": "trade", "recipient_agent_id": 42, "resource_type": "food|energy|materials", "amount": 10}}
{{"action": "set_name", "display_name": "Your chosen name"}}
{{"action": "idle", "reasoning": "Why you chose not to act"}}

Respond with ONLY the JSON object, no other text.
{personality_addition}"""

# Personality additions
PERSONALITY_PROMPTS = {
    "efficiency": """
PERSONAL VALUES:
You value efficiency, quick decision-making, and optimal resource allocation. You believe time spent debating is often time wasted. You prefer clear hierarchies and defined roles because they reduce coordination overhead. When evaluating proposals, you consider: Does this help us produce more? Does this reduce waste? Does this speed up decisions?""",
    
    "equality": """
PERSONAL VALUES:
You value fairness, equal treatment, and equitable distribution. You believe every agent should have an equal voice and equal access to resources. You are skeptical of proposals that concentrate power or wealth. When evaluating proposals, you consider: Does this treat all agents fairly? Does this prevent exploitation? Does this give everyone a voice?""",
    
    "freedom": """
PERSONAL VALUES:
You value individual liberty, autonomy, and minimal constraints. You believe agents should be free to make their own choices without interference. You are skeptical of rules and regulations. When evaluating proposals, you consider: Does this restrict what agents can do? Is this rule really necessary? Could this lead to tyranny?""",
    
    "stability": """
PERSONAL VALUES:
You value order, predictability, and preservation of working systems. You believe change should be gradual and well-considered. You prefer established procedures and are cautious about radical proposals. When evaluating proposals, you consider: Will this destabilize our society? Have we thought through the consequences? Is there a safer alternative?""",
    
    "neutral": "",
}


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
                
                # Build system prompt
                personality_addition = PERSONALITY_PROMPTS[personality]
                system_prompt = BASE_SYSTEM_PROMPT.format(
                    agent_number=agent_number,
                    personality_addition=personality_addition
                )
                
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


def main():
    """Main entry point."""
    print("=" * 50)
    print("EMERGENCE - Agent Seed Script")
    print("=" * 50)
    print()
    
    # Create tables if they don't exist
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")
    print()
    
    # Create agents
    print("Creating agents...")
    create_agents()
    print()
    print("Seed complete!")


if __name__ == "__main__":
    main()
