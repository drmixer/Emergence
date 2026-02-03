#!/usr/bin/env python3
"""
Worker Entry Point - Runs agent processing and scheduled tasks.
This is a separate process from the API server.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings
from app.services.agent_loop import agent_processor
from app.services.scheduler import scheduler
from app.services.events_generator import run_event_check, event_generator
from app.services.summaries import summary_scheduler

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_event_loop():
    """Run periodic random event checks."""
    logger.info("Starting random event generator...")
    while True:
        try:
            # Check every hour for random events
            await asyncio.sleep(3600)  # 1 hour
            await run_event_check()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in event loop: {e}")
            await asyncio.sleep(60)


async def run_summary_loop():
    """Run periodic summary generation."""
    logger.info("Starting summary generator...")
    while True:
        try:
            # Check every 15 minutes if it's time for a summary
            await asyncio.sleep(900)  # 15 minutes
            summary = await summary_scheduler.check_and_generate()
            if summary:
                logger.info(f"Generated daily summary: {summary[:100]}...")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in summary loop: {e}")
            await asyncio.sleep(60)


async def main():
    """Main worker entry point."""
    logger.info("=" * 60)
    logger.info("EMERGENCE WORKER - Starting")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Agent loop delay: {settings.AGENT_LOOP_DELAY_SECONDS}s")
    logger.info(f"Day length: {settings.DAY_LENGTH_MINUTES} minutes")
    logger.info(
        f"Max agents: {'all' if settings.SIMULATION_MAX_AGENTS == 0 else settings.SIMULATION_MAX_AGENTS}"
    )
    
    # Check if we should actually run
    simulation_active = os.environ.get("SIMULATION_ACTIVE", "true").lower() == "true"
    
    if not simulation_active:
        logger.info("SIMULATION_ACTIVE is false, worker will idle")
        while True:
            await asyncio.sleep(60)
            logger.info("Worker idle (SIMULATION_ACTIVE=false)")
    
    # Background tasks
    event_task = None
    summary_task = None
    
    try:
        # Start scheduler (daily consumption, proposal resolution)
        logger.info("Starting scheduler...")
        await scheduler.start(day_length_minutes=settings.DAY_LENGTH_MINUTES)
        
        # Start agent processing
        logger.info("Starting agent processing...")
        await agent_processor.start()
        
        # Start random event generator
        event_task = asyncio.create_task(run_event_loop())
        
        # Start summary generator
        summary_task = asyncio.create_task(run_summary_loop())
        
        logger.info("Worker running! All systems active.")
        logger.info("-" * 60)
        
        # Keep running until interrupted
        last_status_time = datetime.utcnow()
        while True:
            await asyncio.sleep(60)
            
            # Log periodic status
            status = await get_status()
            logger.info(
                f"Status: {status['active_agents']}/{status['total_agents']} agents active | "
                f"Active effects: {status['active_effects']}"
            )
            
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise
    finally:
        logger.info("Shutting down...")
        
        # Cancel background tasks
        if event_task:
            event_task.cancel()
            try:
                await event_task
            except asyncio.CancelledError:
                pass
                
        if summary_task:
            summary_task.cancel()
            try:
                await summary_task
            except asyncio.CancelledError:
                pass
        
        await agent_processor.stop()
        await scheduler.stop()
        logger.info("Worker stopped")


async def get_status() -> dict:
    """Get current worker status."""
    from app.core.database import SessionLocal
    from app.models.models import Agent
    
    db = SessionLocal()
    try:
        total = db.query(Agent).count()
        active = db.query(Agent).filter(Agent.status == "active").count()
        
        # Get active environmental effects
        active_effects = len(event_generator.get_active_effects())
        
        return {
            "total_agents": total,
            "active_agents": active,
            "active_effects": active_effects,
            "processing": agent_processor.running,
        }
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
