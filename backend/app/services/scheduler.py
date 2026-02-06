"""
Scheduled Tasks - Daily consumption, proposal resolution, etc.
"""
import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import Agent, AgentInventory, Proposal, Law, Event, Transaction, GlobalResources
from app.services.emergence_metrics import persist_completed_day_snapshot

# Twitter bot integration (optional)
try:
    from app.services.twitter_bot import tweet_agent_dormant, tweet_agent_died, tweet_law_passed, twitter_bot
    TWITTER_ENABLED = True
except ImportError:
    TWITTER_ENABLED = False
    tweet_agent_dormant = None
    tweet_agent_died = None
    tweet_law_passed = None

logger = logging.getLogger(__name__)

# ============================================================================
# SURVIVAL COST CONFIGURATION
# ============================================================================
# Active agents must pay full survival cost each cycle
ACTIVE_FOOD_COST = Decimal("1.0")
ACTIVE_ENERGY_COST = Decimal("1.0")

# Dormant agents pay reduced survival cost (but NOT zero - scarcity still kills)
DORMANT_FOOD_COST = Decimal("0.25")
DORMANT_ENERGY_COST = Decimal("0.25")

# After this many consecutive cycles of unpaid survival cost, agent dies permanently
DEATH_THRESHOLD = 5


async def process_daily_consumption():
    """
    Process daily resource consumption for all living agents.
    
    SURVIVAL MECHANICS:
    - Active agents: Pay 1 food + 1 energy per cycle
    - If active agent can't pay → goes DORMANT
    - Dormant agents: Pay 0.25 food + 0.25 energy per cycle (reduced, not zero)
    - If dormant agent can't pay reduced cost → starvation_cycles += 1
    - If starvation_cycles >= DEATH_THRESHOLD → PERMANENT DEATH
    - Death is irreversible. Agent is removed from simulation.
    
    This ensures scarcity is the root cause of death, not just "sleeping too long".
    """
    db = SessionLocal()
    
    try:
        logger.info("Processing daily survival cycle...")
        
        # Get all living agents (both active and dormant)
        query = db.query(Agent).filter(or_(Agent.status == "active", Agent.status == "dormant"))

        # Dev/test mode: if we cap the simulation to N agents, don't kill the rest via survival ticks.
        # This keeps "SIMULATION_MAX_AGENTS=20" as a cheap sandbox without destroying the full seeded world.
        if settings.SIMULATION_MAX_AGENTS and settings.SIMULATION_MAX_AGENTS > 0:
            query = query.filter(Agent.agent_number <= settings.SIMULATION_MAX_AGENTS)

        living_agents = query.all()
        
        # Track outcomes
        agents_consumed = []  # Paid full cost
        agents_made_dormant = []  # Active → Dormant
        agents_starving = []  # Dormant & can't pay reduced cost
        agents_died = []  # Reached death threshold
        agents_recovered = []  # Dormant but paid cost (stable)
        
        for agent in living_agents:
            # Get inventory
            food_inv = db.query(AgentInventory).filter(
                AgentInventory.agent_id == agent.id,
                AgentInventory.resource_type == "food"
            ).first()
            
            energy_inv = db.query(AgentInventory).filter(
                AgentInventory.agent_id == agent.id,
                AgentInventory.resource_type == "energy"
            ).first()
            
            food_amount = Decimal(str(food_inv.quantity)) if food_inv else Decimal("0")
            energy_amount = Decimal(str(energy_inv.quantity)) if energy_inv else Decimal("0")
            
            agent_name = agent.display_name or f"Agent #{agent.agent_number}"
            
            # ================================================================
            # ACTIVE AGENT PROCESSING
            # ================================================================
            if agent.status == "active":
                can_pay_food = food_amount >= ACTIVE_FOOD_COST
                can_pay_energy = energy_amount >= ACTIVE_ENERGY_COST
                
                if can_pay_food and can_pay_energy:
                    # Pay full survival cost - stays active
                    food_inv.quantity -= ACTIVE_FOOD_COST
                    energy_inv.quantity -= ACTIVE_ENERGY_COST
                    
                    # Reset starvation counter (agent is well-fed)
                    agent.starvation_cycles = 0
                    
                    # Record transactions
                    for resource_type, amount in [("food", ACTIVE_FOOD_COST), ("energy", ACTIVE_ENERGY_COST)]:
                        transaction = Transaction(
                            from_agent_id=agent.id,
                            resource_type=resource_type,
                            amount=amount,
                            transaction_type="survival_consumption"
                        )
                        db.add(transaction)
                    
                    agents_consumed.append(agent.id)
                    
                else:
                    # Can't pay full cost → GO DORMANT
                    agent.status = "dormant"
                    reason = "lack of food" if not can_pay_food else "lack of energy"
                    
                    agents_made_dormant.append((agent.id, agent.agent_number, agent.display_name, reason))
                    
                    event = Event(
                        agent_id=agent.id,
                        event_type="became_dormant",
                        description=f"{agent_name} went dormant due to {reason}",
                        event_metadata={
                            "reason": reason, 
                            "food": float(food_amount), 
                            "energy": float(energy_amount)
                        }
                    )
                    db.add(event)
                    
                    # Tweet about dormancy
                    if TWITTER_ENABLED and tweet_agent_dormant:
                        asyncio.create_task(tweet_agent_dormant(
                            agent.agent_number,
                            agent.display_name,
                            reason
                        ))
                    
                    logger.info(f"⚠️ {agent_name} went DORMANT ({reason})")
            
            # ================================================================
            # DORMANT AGENT PROCESSING
            # ================================================================
            elif agent.status == "dormant":
                can_pay_reduced_food = food_amount >= DORMANT_FOOD_COST
                can_pay_reduced_energy = energy_amount >= DORMANT_ENERGY_COST
                
                if can_pay_reduced_food and can_pay_reduced_energy:
                    # Pay reduced survival cost - stays dormant but stable
                    if food_inv:
                        food_inv.quantity -= DORMANT_FOOD_COST
                    if energy_inv:
                        energy_inv.quantity -= DORMANT_ENERGY_COST
                    
                    # Starvation counter doesn't increase (agent is surviving)
                    # But it also doesn't reset - need to become active for that
                    
                    # Record transactions
                    for resource_type, amount in [("food", DORMANT_FOOD_COST), ("energy", DORMANT_ENERGY_COST)]:
                        transaction = Transaction(
                            from_agent_id=agent.id,
                            resource_type=resource_type,
                            amount=amount,
                            transaction_type="dormant_survival"
                        )
                        db.add(transaction)
                    
                    agents_recovered.append(agent.id)
                    
                else:
                    # CAN'T PAY EVEN REDUCED COST - STARVATION WORSENS
                    agent.starvation_cycles += 1
                    
                    agents_starving.append((
                        agent.id, 
                        agent.agent_number, 
                        agent.display_name,
                        agent.starvation_cycles
                    ))
                    
                    logger.warning(
                        f"💀 {agent_name} cannot pay survival cost! "
                        f"Starvation cycle {agent.starvation_cycles}/{DEATH_THRESHOLD}"
                    )
                    
                    # Check for PERMANENT DEATH
                    if agent.starvation_cycles >= DEATH_THRESHOLD:
                        # ========================================
                        # PERMANENT DEATH - NO RESURRECTION
                        # ========================================
                        agent.status = "dead"
                        agent.died_at = datetime.utcnow()
                        agent.death_cause = "starvation"
                        
                        agents_died.append((
                            agent.id,
                            agent.agent_number,
                            agent.display_name,
                            agent.starvation_cycles
                        ))
                        
                        # Create death event
                        event = Event(
                            agent_id=agent.id,
                            event_type="agent_died",
                            description=f"☠️ {agent_name} has DIED from starvation after {agent.starvation_cycles} cycles without resources",
                            event_metadata={
                                "cause": "starvation",
                                "starvation_cycles": agent.starvation_cycles,
                                "final_food": float(food_amount),
                                "final_energy": float(energy_amount)
                            }
                        )
                        db.add(event)
                        
                        # Tweet about death
                        if TWITTER_ENABLED and tweet_agent_died:
                            asyncio.create_task(tweet_agent_died(
                                agent.agent_number,
                                agent.display_name,
                                "starvation",
                                agent.starvation_cycles
                            ))
                        
                        logger.error(f"☠️☠️☠️ {agent_name} HAS DIED PERMANENTLY ☠️☠️☠️")
                    
                    else:
                        # Not dead yet, but getting closer
                        event = Event(
                            agent_id=agent.id,
                            event_type="starvation_warning",
                            description=f"⚠️ {agent_name} is starving! Cycle {agent.starvation_cycles}/{DEATH_THRESHOLD} until death",
                            event_metadata={
                                "starvation_cycles": agent.starvation_cycles,
                                "cycles_until_death": DEATH_THRESHOLD - agent.starvation_cycles,
                                "food": float(food_amount),
                                "energy": float(energy_amount)
                            }
                        )
                        db.add(event)
        
        # Update global consumption stats
        total_consumed = len(agents_consumed) + len(agents_recovered)
        for resource_type in ["food", "energy"]:
            global_res = db.query(GlobalResources).filter(
                GlobalResources.resource_type == resource_type
            ).first()
            
            if global_res:
                global_res.consumed_today = Decimal(str(total_consumed))
        
        db.commit()
        
        # Log summary
        logger.info(
            f"Survival cycle complete: "
            f"{len(agents_consumed)} active (fed), "
            f"{len(agents_recovered)} dormant (stable), "
            f"{len(agents_made_dormant)} became dormant, "
            f"{len(agents_starving)} starving, "
            f"{len(agents_died)} DIED"
        )
        
        return {
            "active_fed": len(agents_consumed),
            "dormant_stable": len(agents_recovered),
            "became_dormant": len(agents_made_dormant),
            "dormant_agents": agents_made_dormant,
            "starving": len(agents_starving),
            "starving_agents": agents_starving,
            "died": len(agents_died),
            "dead_agents": agents_died,
        }
        
    except Exception as e:
        logger.error(f"Error in survival cycle: {e}")
        db.rollback()
        raise
        
    finally:
        db.close()


async def resolve_expired_proposals():
    """
    Resolve proposals whose voting period has ended.
    Run this every few minutes.
    """
    db = SessionLocal()
    
    try:
        logger.info("Checking for expired proposals...")
        
        now = datetime.utcnow()
        
        expired_proposals = db.query(Proposal).filter(
            Proposal.status == "active",
            Proposal.voting_closes_at <= now
        ).all()
        
        results = []
        
        for proposal in expired_proposals:
            # Calculate result
            total_votes = proposal.votes_for + proposal.votes_against
            
            if total_votes == 0:
                # No votes = failed
                proposal.status = "expired"
                result = "expired"
            elif proposal.votes_for > proposal.votes_against:
                # Majority yes = passed
                proposal.status = "passed"
                result = "passed"
                
                # If it's a law proposal, create the law
                if proposal.proposal_type == "law":
                    law = Law(
                        proposal_id=proposal.id,
                        title=proposal.title,
                        description=proposal.description,
                        author_agent_id=proposal.author_agent_id,
                        active=True,
                    )
                    db.add(law)
                    
                    event = Event(
                        event_type="law_passed",
                        description=f"New law enacted: {proposal.title}",
                        event_metadata={
                            "proposal_id": proposal.id,
                            "votes_for": proposal.votes_for,
                            "votes_against": proposal.votes_against,
                        }
                    )
                    db.add(event)
                    
                    # Tweet about the new law
                    if TWITTER_ENABLED and tweet_law_passed:
                        asyncio.create_task(tweet_law_passed(
                            proposal.title,
                            proposal.id,
                            proposal.votes_for,
                            proposal.votes_against,
                            proposal.description or ""
                        ))
            else:
                # Majority no or tie = failed
                proposal.status = "failed"
                result = "failed"
            
            proposal.resolved_at = now
            
            # Log the result
            event = Event(
                event_type="proposal_resolved",
                description=f"Proposal '{proposal.title}' {result} ({proposal.votes_for}/{proposal.votes_against})",
                event_metadata={
                    "proposal_id": proposal.id,
                    "result": result,
                    "votes_for": proposal.votes_for,
                    "votes_against": proposal.votes_against,
                    "votes_abstain": proposal.votes_abstain,
                }
            )
            db.add(event)
            
            results.append({
                "proposal_id": proposal.id,
                "title": proposal.title,
                "result": result,
            })
        
        db.commit()
        
        if results:
            logger.info(f"Resolved {len(results)} proposals: {results}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error resolving proposals: {e}")
        db.rollback()
        raise
        
    finally:
        db.close()


async def reset_daily_stats():
    """
    Reset daily production/consumption counters.
    Run at the start of each simulation day.
    """
    db = SessionLocal()
    
    try:
        global_resources = db.query(GlobalResources).all()
        
        for gr in global_resources:
            gr.produced_today = Decimal("0")
            gr.consumed_today = Decimal("0")
        
        db.commit()
        logger.info("Daily stats reset")
        
    finally:
        db.close()


class SchedulerRunner:
    """Manages scheduled tasks."""
    
    def __init__(self):
        self.running = False
        self.tasks = []
    
    async def start(self, day_length_minutes: int = 60):
        """Start the scheduler."""
        self.running = True
        
        # Proposal resolution every 5 minutes
        self.tasks.append(
            asyncio.create_task(self._run_periodic(resolve_expired_proposals, 300))
        )
        
        # Daily consumption every day_length_minutes
        self.tasks.append(
            asyncio.create_task(self._run_periodic(process_daily_consumption, day_length_minutes * 60))
        )
        
        # Daily stats reset
        self.tasks.append(
            asyncio.create_task(self._run_periodic(reset_daily_stats, day_length_minutes * 60))
        )

        # Persist one emergence metrics snapshot per completed simulation day.
        self.tasks.append(
            asyncio.create_task(self._run_periodic(persist_completed_day_snapshot, day_length_minutes * 60))
        )
        
        logger.info(f"Scheduler started (day length: {day_length_minutes} minutes)")
    
    async def stop(self):
        """Stop the scheduler."""
        self.running = False
        
        for task in self.tasks:
            task.cancel()
        
        self.tasks.clear()
        logger.info("Scheduler stopped")
    
    async def _run_periodic(self, func, interval_seconds: int):
        """Run a function periodically."""
        while self.running:
            try:
                await func()
            except Exception as e:
                logger.error(f"Error in scheduled task {func.__name__}: {e}")
            
            await asyncio.sleep(interval_seconds)


# Singleton scheduler
scheduler = SchedulerRunner()
