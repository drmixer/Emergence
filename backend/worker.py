#!/usr/bin/env python3
"""
Worker Entry Point - Runs agent processing and scheduled tasks.
This is a separate process from the API server.
"""
import asyncio
import logging
import os
import json
import sys
from pathlib import Path
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings
from app.services.agent_loop import agent_processor
from app.services.scheduler import scheduler
from app.services.events_generator import run_event_check, event_generator
from app.services.summaries import summary_scheduler
from app.services.runtime_config import runtime_config_service
from app.services.run_guardrails import run_guardrail_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
DB_RETRY_SECONDS = max(5, int(os.environ.get("WORKER_DB_RETRY_SECONDS", "20")))


async def _healthcheck_handler(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Serve a minimal HTTP health response for Railway worker health checks."""
    try:
        request_line = await reader.readline()
        if not request_line:
            return

        parts = request_line.decode("utf-8", errors="ignore").strip().split()
        method = parts[0] if len(parts) >= 1 else "GET"
        path = parts[1] if len(parts) >= 2 else "/"

        # Drain request headers.
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break

        if method == "GET" and path == "/health":
            body = json.dumps(
                {
                    "status": "ok",
                    "service": "emergence-worker",
                    "environment": settings.ENVIRONMENT,
                }
            ).encode("utf-8")
            status = "200 OK"
        else:
            body = b'{"status":"not_found"}'
            status = "404 Not Found"

        response = (
            f"HTTP/1.1 {status}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("utf-8") + body

        writer.write(response)
        await writer.drain()
    except Exception:
        # Keep healthcheck server resilient to malformed probes.
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _start_health_server() -> asyncio.AbstractServer | None:
    """Start lightweight worker health server bound to PORT for Railway checks."""
    port_raw = str(os.environ.get("PORT", "8080") or "8080").strip()
    try:
        port = int(port_raw)
    except ValueError:
        logger.warning(
            "Invalid PORT=%s for worker health server; skipping health endpoint",
            port_raw,
        )
        return None

    server = await asyncio.start_server(_healthcheck_handler, host="0.0.0.0", port=port)
    logger.info("Worker health server listening on 0.0.0.0:%s", port)
    return server


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


async def _start_runtime_systems() -> tuple[asyncio.Task, asyncio.Task | None]:
    """Start scheduler, agent loops, and optional background tasks."""
    logger.info("Starting scheduler...")
    await scheduler.start(day_length_minutes=settings.DAY_LENGTH_MINUTES)

    try:
        logger.info("Starting agent processing...")
        await agent_processor.start()
    except Exception:
        # If agent startup fails after scheduler starts, clean up before retrying.
        try:
            await scheduler.stop()
        except Exception as stop_error:
            logger.error("Failed to stop scheduler after startup error: %s", stop_error)
        raise

    event_task = asyncio.create_task(run_event_loop())

    summary_task: asyncio.Task | None = None
    if getattr(settings, "SUMMARIES_ENABLED", False):
        summary_task = asyncio.create_task(run_summary_loop())
    else:
        logger.info("Summaries disabled; skipping summary generator loop.")

    logger.info("Worker running! All systems active.")
    logger.info("-" * 60)
    return event_task, summary_task


async def _stop_runtime_systems(
    event_task: asyncio.Task | None,
    summary_task: asyncio.Task | None,
) -> None:
    """Stop scheduler, agent loops, and background tasks."""
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


async def main():
    """Main worker entry point."""
    health_server = None
    logger.info("=" * 60)
    logger.info("EMERGENCE WORKER - Starting")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(
        "LLM config: provider=%s groq=%s openrouter=%s mistral=%s groq_default_model=%s mistral_model=%s",
        getattr(settings, "LLM_PROVIDER", "auto"),
        bool(getattr(settings, "GROQ_API_KEY", "")),
        bool(getattr(settings, "OPENROUTER_API_KEY", "")),
        bool(getattr(settings, "MISTRAL_API_KEY", "")),
        getattr(settings, "GROQ_DEFAULT_MODEL", ""),
        getattr(settings, "MISTRAL_SMALL_MODEL", ""),
    )
    logger.info(f"Agent loop delay: {settings.AGENT_LOOP_DELAY_SECONDS}s")
    logger.info(f"Day length: {settings.DAY_LENGTH_MINUTES} minutes")
    logger.info(
        f"Max agents: {'all' if settings.SIMULATION_MAX_AGENTS == 0 else settings.SIMULATION_MAX_AGENTS}"
    )

    # Expose health endpoint to satisfy Railway worker health checks.
    health_server = await _start_health_server()

    event_task: asyncio.Task | None = None
    summary_task: asyncio.Task | None = None
    runtime_systems_started = False
    idle_logged = False

    try:
        while True:
            try:
                simulation_active = bool(
                    runtime_config_service.get_effective_value_cached("SIMULATION_ACTIVE")
                )

                if simulation_active and not runtime_systems_started:
                    event_task, summary_task = await _start_runtime_systems()
                    runtime_systems_started = True
                    idle_logged = False
                elif not simulation_active and runtime_systems_started:
                    logger.info("SIMULATION_ACTIVE is false; stopping runtime systems...")
                    await _stop_runtime_systems(event_task, summary_task)
                    event_task = None
                    summary_task = None
                    runtime_systems_started = False

                if not simulation_active:
                    if not idle_logged:
                        logger.info("SIMULATION_ACTIVE is false, worker will idle")
                        idle_logged = True
                    await asyncio.sleep(60)
                    logger.info("Worker idle (SIMULATION_ACTIVE=false)")
                    continue

                stop_decision = run_guardrail_service.evaluate_and_enforce()
                if stop_decision.should_stop:
                    logger.error(
                        "Stopping worker after run guardrail trigger (%s): %s",
                        stop_decision.reason,
                        stop_decision.details or {},
                    )
                    break

                # Log periodic status
                status = await get_status()
                logger.info(
                    f"Status: {status['processing_agents']} processing | "
                    f"{status['active_agents']}/{status['total_agents']} agents active | "
                    f"Active effects: {status['active_effects']}"
                )
                await asyncio.sleep(60)
            except SQLAlchemyError as db_error:
                logger.error(
                    "Database unavailable for worker loop; retrying in %ss: %s",
                    DB_RETRY_SECONDS,
                    db_error,
                )
                if runtime_systems_started:
                    try:
                        await _stop_runtime_systems(event_task, summary_task)
                    except Exception as stop_error:
                        logger.error("Failed to stop runtime systems after DB error: %s", stop_error)
                    event_task = None
                    summary_task = None
                    runtime_systems_started = False
                await asyncio.sleep(DB_RETRY_SECONDS)
            except Exception as loop_error:
                logger.error(
                    "Worker loop iteration failed; retrying in %ss: %s",
                    DB_RETRY_SECONDS,
                    loop_error,
                )
                await asyncio.sleep(DB_RETRY_SECONDS)

    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise
    finally:
        logger.info("Shutting down...")
        if runtime_systems_started:
            await _stop_runtime_systems(event_task, summary_task)
        if health_server is not None:
            health_server.close()
            try:
                await health_server.wait_closed()
            except Exception:
                pass
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
            "processing_agents": len(agent_processor.tasks),
        }
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
