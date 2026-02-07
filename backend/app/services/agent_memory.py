"""Per-agent long-term memory updates and bounded retrieval."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.core.time import ensure_utc, now_utc
from app.models.models import Agent, AgentMemory, Event
from app.services.runtime_config import runtime_config_service
from app.services.salience_detector import (
    SALIENT_EVENT_TYPES,
    detect_salient_events,
    is_salient_checkpoint_reason,
)


class AgentMemoryService:
    """Maintains concise autobiographical memory for each agent."""

    MAX_EVENT_SCAN = 40
    MAX_SALIENT_EVENTS = 3
    DEFAULT_EVENT_LOOKBACK_HOURS = 48

    def maybe_update_after_checkpoint(
        self,
        db: Session,
        agent: Agent,
        checkpoint_number: int,
        checkpoint_reason: str | None,
        action_data: dict | None,
        action_result: dict | None,
    ) -> dict:
        """Update memory only when cadence or salience policy requires it."""
        checkpoint_number = max(1, int(checkpoint_number or 1))
        cadence_n = max(
            1,
            int(runtime_config_service.get_effective_value_cached("LLM_MEMORY_UPDATE_EVERY_N_CHECKPOINTS") or 3),
        )
        max_chars = max(
            200,
            int(runtime_config_service.get_effective_value_cached("LLM_MEMORY_MAX_CHARS") or 1200),
        )

        memory = (
            db.query(AgentMemory)
            .filter(AgentMemory.agent_id == agent.id)
            .first()
        )

        last_checkpoint_number = int((memory.last_checkpoint_number if memory else 0) or 0)
        if checkpoint_number <= last_checkpoint_number:
            return {"updated": False, "reason": "already_up_to_date"}

        recent_events = self._load_recent_events(
            db=db,
            agent_id=agent.id,
            since=ensure_utc(memory.last_updated_at) if memory else None,
        )
        salient_events = detect_salient_events(
            recent_events,
            agent_id=agent.id,
            limit=self.MAX_SALIENT_EVENTS,
        )

        cadence_due = checkpoint_number % cadence_n == 0
        salient_due = bool(salient_events) or is_salient_checkpoint_reason(checkpoint_reason)
        should_update = memory is None or cadence_due or salient_due

        if not should_update:
            return {
                "updated": False,
                "reason": "policy_skip",
                "cadence_due": cadence_due,
                "salient_due": salient_due,
            }

        entry = self._build_entry(
            agent=agent,
            checkpoint_number=checkpoint_number,
            checkpoint_reason=checkpoint_reason,
            action_data=action_data,
            action_result=action_result,
            salient_events=salient_events,
        )

        merged_summary = self._append_with_compaction(
            existing=(memory.summary_text if memory else ""),
            new_entry=entry,
            max_chars=max_chars,
        )

        if not memory:
            memory = AgentMemory(agent_id=agent.id)

        memory.summary_text = merged_summary
        memory.last_updated_at = now_utc()
        memory.last_checkpoint_number = checkpoint_number
        db.add(memory)

        return {
            "updated": True,
            "reason": "salient" if salient_due else "cadence",
            "checkpoint_number": checkpoint_number,
            "salient_events": len(salient_events),
        }

    def get_bounded_memory_text(self, db: Session, agent_id: int) -> str:
        """Return capped memory text for prompt injection."""
        max_chars = max(
            200,
            int(runtime_config_service.get_effective_value_cached("LLM_MEMORY_MAX_CHARS") or 1200),
        )
        memory = (
            db.query(AgentMemory)
            .filter(AgentMemory.agent_id == agent_id)
            .first()
        )
        if not memory or not memory.summary_text:
            return ""

        text = memory.summary_text.strip()
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    def _load_recent_events(self, db: Session, agent_id: int, since) -> list[Event]:
        if since is None:
            since = now_utc() - timedelta(hours=self.DEFAULT_EVENT_LOOKBACK_HOURS)

        return (
            db.query(Event)
            .filter(
                Event.created_at > since,
                or_(
                    Event.agent_id == agent_id,
                    Event.event_type.in_(tuple(SALIENT_EVENT_TYPES)),
                ),
            )
            .order_by(desc(Event.created_at))
            .limit(self.MAX_EVENT_SCAN)
            .all()
        )

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    def _build_entry(
        self,
        agent: Agent,
        checkpoint_number: int,
        checkpoint_reason: str | None,
        action_data: dict | None,
        action_result: dict | None,
        salient_events: list[Event],
    ) -> str:
        ts = now_utc().strftime("%Y-%m-%d %H:%M UTC")
        strategy = str((agent.current_intent or {}).get("strategy") or "stabilize")
        action_type = str((action_data or {}).get("action") or "idle")
        outcome = self._truncate(str((action_result or {}).get("description") or ""), 160)

        lines = [
            f"[CP#{checkpoint_number} {ts}] strategy={strategy}; action={action_type}; outcome={outcome or 'none'}"
        ]

        if salient_events:
            event_bits = []
            for event in salient_events[:2]:
                event_bits.append(
                    f"{event.event_type}: {self._truncate(event.description or '', 100)}"
                )
            lines.append(f"salient: {' | '.join(event_bits)}")
        elif is_salient_checkpoint_reason(checkpoint_reason):
            lines.append(f"salient: checkpoint trigger {checkpoint_reason}")
        else:
            lines.append("salient: cadence refresh")

        return "\n".join(lines)

    def _append_with_compaction(self, existing: str, new_entry: str, max_chars: int) -> str:
        existing = (existing or "").strip()
        new_entry = (new_entry or "").strip()

        combined = new_entry if not existing else f"{existing}\n{new_entry}"
        if len(combined) <= max_chars:
            return combined

        lines = [line.strip() for line in combined.splitlines() if line.strip()]
        kept: list[str] = []
        total = 0

        for line in reversed(lines):
            line_cost = len(line) + (1 if kept else 0)
            if total + line_cost > max_chars:
                break
            kept.append(line)
            total += line_cost

        kept.reverse()

        trimmed = "\n".join(["[Trimmed older memory]", *kept]) if kept else "[Trimmed older memory]"
        if len(trimmed) <= max_chars:
            return trimmed
        return trimmed[-max_chars:]


agent_memory_service = AgentMemoryService()
