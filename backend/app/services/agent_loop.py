"""
Agent Processing Loop - The heart of the simulation.
Each agent runs this loop continuously to perceive, decide, and act.
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, Message, Proposal, Event, Law, Vote
from app.services.llm_client import get_agent_action
from app.services.actions import execute_action, validate_action
from app.services.context_builder import build_agent_context

logger = logging.getLogger(__name__)


class AgentProcessor:
    """Manages the processing loop for all agents."""
    
    def __init__(self):
        self.running = False
        self.tasks: dict[int, asyncio.Task] = {}
    
    async def start(self):
        """Start processing all agents."""
        self.running = True
        db = SessionLocal()
        
        try:
            query = db.query(Agent).order_by(Agent.agent_number)
            if settings.SIMULATION_MAX_AGENTS and settings.SIMULATION_MAX_AGENTS > 0:
                query = query.limit(settings.SIMULATION_MAX_AGENTS)
            agents = query.all()
            
            for agent in agents:
                # Stagger agent starts over 60 seconds
                delay = random.uniform(0, 60)
                task = asyncio.create_task(
                    self._run_agent_loop(agent.id, initial_delay=delay)
                )
                self.tasks[agent.id] = task
                
            logger.info(f"Started {len(agents)} agent processing loops")
            
        finally:
            db.close()
    
    async def stop(self):
        """Stop all agent processing."""
        self.running = False
        
        for agent_id, task in self.tasks.items():
            task.cancel()
            
        self.tasks.clear()
        logger.info("Stopped all agent processing loops")
    
    async def _run_agent_loop(self, agent_id: int, initial_delay: float = 0):
        """Main processing loop for a single agent."""
        
        if initial_delay > 0:
            await asyncio.sleep(initial_delay)
        
        while self.running:
            try:
                await self._process_agent_turn(agent_id)
                
            except asyncio.CancelledError:
                break
                
            except Exception as e:
                logger.error(f"Error in agent {agent_id} loop: {e}")
                await self._log_error(agent_id, str(e))
            
            # Wait before next action (2-3 minutes with jitter)
            delay = settings.AGENT_LOOP_DELAY_SECONDS + random.randint(-30, 30)
            await asyncio.sleep(max(60, delay))  # Minimum 1 minute
    
    async def _process_agent_turn(self, agent_id: int):
        """Process a single turn for an agent."""
        db = SessionLocal()
        
        try:
            # 1. PERCEIVE - Get agent and check status
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            
            if not agent:
                logger.error(f"Agent {agent_id} not found")
                return
            
            if agent.status == "dormant":
                logger.debug(f"Agent {agent_id} is dormant, skipping")
                return
            
            if agent.status == "dead":
                # Dead agents are permanently removed from the simulation
                logger.debug(f"Agent {agent_id} is dead, removing from loop")
                if agent_id in self.tasks:
                    self.tasks[agent_id].cancel()
                    del self.tasks[agent_id]
                return
            
            # 2. BUILD CONTEXT - Gather information for decision
            context = await build_agent_context(db, agent)
            
            # 3. DECIDE - Call LLM for action
            action_data = await get_agent_action(
                agent_id=agent.id,
                model_type=agent.model_type,
                system_prompt=agent.system_prompt,
                context_prompt=context,
            )
            
            if not action_data:
                logger.debug(f"Agent {agent_id} returned no action")
                return
            
            # 4. VALIDATE - Check action is allowed
            validation = await validate_action(db, agent, action_data)
            
            if not validation["valid"]:
                await self._log_invalid_action(db, agent_id, action_data, validation["reason"])
                return
            
            # 5. ACT - Execute the action
            result = await execute_action(db, agent, action_data)
            
            # 6. LOG - Record what happened
            await self._log_action(db, agent_id, action_data, result)
            
            # Update last active time
            agent.last_active_at = now_utc()
            db.commit()
            
        finally:
            db.close()
    
    async def _log_action(self, db: Session, agent_id: int, action: dict, result: dict):
        """Log a successful action."""
        event = Event(
            agent_id=agent_id,
            event_type=action.get("action", "unknown"),
            description=result.get("description", "Action completed"),
            event_metadata={
                "action": action,
                "result": result,
            }
        )
        db.add(event)
        db.commit()
    
    async def _log_invalid_action(self, db: Session, agent_id: int, action: dict, reason: str):
        """Log an invalid/rejected action."""
        event = Event(
            agent_id=agent_id,
            event_type="invalid_action",
            description=f"Action rejected: {reason}",
            event_metadata={
                "action": action,
                "reason": reason,
            }
        )
        db.add(event)
        db.commit()
        logger.debug(f"Agent {agent_id} action rejected: {reason}")
    
    async def _log_error(self, agent_id: int, error: str):
        """Log an error during processing."""
        db = SessionLocal()
        try:
            event = Event(
                agent_id=agent_id,
                event_type="processing_error",
                description=f"Error during processing: {error}",
                event_metadata={"error": error}
            )
            db.add(event)
            db.commit()
        finally:
            db.close()


# Singleton processor instance
agent_processor = AgentProcessor()


async def start_simulation():
    """Start the simulation."""
    await agent_processor.start()


async def stop_simulation():
    """Stop the simulation."""
    await agent_processor.stop()


async def get_simulation_status() -> dict:
    """Get current simulation status."""
    return {
        "running": agent_processor.running,
        "active_agents": len(agent_processor.tasks),
    }
