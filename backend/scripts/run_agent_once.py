#!/usr/bin/env python3
"""
Run a single agent turn once (useful for smoke testing the loop without running worker.py).
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.models import Agent, Event
from app.services.context_builder import build_agent_context
from app.services.llm_client import get_agent_action
from app.services.actions import validate_action, execute_action


async def run_once(agent_number: int, dry_run: bool) -> int:
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.agent_number == agent_number).first()
        if not agent:
            print(f"Agent #{agent_number} not found")
            return 2

        context = await build_agent_context(db, agent)
        action = await get_agent_action(
            agent_id=agent.id,
            model_type=agent.model_type,
            system_prompt=agent.system_prompt,
            context_prompt=context,
        )

        if dry_run:
            print({"agent_number": agent_number, "action": action})
            return 0

        validation = await validate_action(db, agent, action or {})
        if not validation["valid"]:
            db.add(
                Event(
                    agent_id=agent.id,
                    event_type="invalid_action",
                    description=f"Action rejected: {validation['reason']}",
                    event_metadata={"action": action, "reason": validation["reason"]},
                )
            )
            db.commit()
            print({"agent_number": agent_number, "rejected": True, "reason": validation["reason"], "action": action})
            return 0

        result = await execute_action(db, agent, action or {})
        db.add(
            Event(
                agent_id=agent.id,
                event_type=(action or {}).get("action", "unknown"),
                description=result.get("description", "Action completed"),
                event_metadata={"action": action, "result": result},
            )
        )
        db.commit()
        print({"agent_number": agent_number, "action": action, "result": result})
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one agent turn once.")
    parser.add_argument("--agent", type=int, default=1, help="Agent number (1-100)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Call the LLM and print the chosen action, but do not execute it.",
    )
    args = parser.parse_args()
    return asyncio.run(run_once(agent_number=args.agent, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())

