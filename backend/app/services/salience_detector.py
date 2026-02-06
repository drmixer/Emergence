"""Deterministic salience heuristics for long-term memory updates."""

from __future__ import annotations

from typing import Iterable

from app.models.models import Event

# High-impact outcomes that should usually be remembered.
SALIENT_EVENT_TYPES = {
    "proposal_resolved",
    "law_passed",
    "enforcement_initiated",
    "agent_sanctioned",
    "agent_exiled",
    "resources_seized",
    "became_dormant",
    "agent_died",
    "agent_revived",
    "crisis",
    "crisis_event",
    "world_event",
}

# Lightweight lexical backup for alliance/conflict and macro shocks.
SALIENT_KEYWORDS = {
    "alliance",
    "ally",
    "coalition",
    "betray",
    "conflict",
    "hostile",
    "fight",
    "war",
    "truce",
    "sanction",
    "exile",
    "crisis",
    "collapse",
    "riot",
}


def is_salient_checkpoint_reason(checkpoint_reason: str | None) -> bool:
    """Interrupt checkpoints are treated as salient by default."""
    if not checkpoint_reason:
        return False
    return str(checkpoint_reason).startswith("interrupt_")


def score_event_salience(event: Event, agent_id: int) -> int:
    """Return deterministic salience score for an event."""
    score = 0

    event_type = str(event.event_type or "")
    description = str(event.description or "").lower()

    if event_type in SALIENT_EVENT_TYPES:
        score += 3

    if event.agent_id == agent_id:
        score += 1

    if any(keyword in description for keyword in SALIENT_KEYWORDS):
        score += 1

    metadata = event.event_metadata or {}
    if isinstance(metadata, dict):
        if event_type == "proposal_resolved" and metadata.get("result") in {"passed", "failed", "expired"}:
            score += 2
        if event_type in {"agent_sanctioned", "agent_exiled", "agent_died", "became_dormant"}:
            score += 2

    return score


def detect_salient_events(events: Iterable[Event], agent_id: int, limit: int = 3) -> list[Event]:
    """Return top salient events, highest score first, stable order otherwise."""
    scored = []
    for event in events:
        score = score_event_salience(event, agent_id=agent_id)
        if score > 0:
            scored.append((score, event))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [event for _, event in scored[: max(1, limit)]]
