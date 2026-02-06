"""
Emergence metrics computation + daily snapshot persistence.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import ensure_utc, now_utc
from app.models.models import (
    Agent,
    AgentInventory,
    EmergenceMetricSnapshot,
    Enforcement,
    EnforcementVote,
    Event,
    Proposal,
    Vote,
)

logger = logging.getLogger(__name__)

COOPERATION_EVENT_TYPES = {
    "trade",
    "direct_message",
    "forum_reply",
    "forum_post",
    "agent_revived",
    "proposal_resolved",
}

CONFLICT_EVENT_TYPES = {
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
    "vote_enforcement",
    "enforcement_initiated",
    "agent_sanctioned",
    "resources_seized",
    "agent_exiled",
}

COOPERATION_KEYWORDS = {
    "alliance",
    "ally",
    "cooperate",
    "cooperation",
    "truce",
    "help",
    "support",
    "rescue",
}

CONFLICT_KEYWORDS = {
    "conflict",
    "hostile",
    "fight",
    "war",
    "betray",
    "sanction",
    "seizure",
    "exile",
    "retaliation",
}


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    den = float(denominator or 0)
    if den <= 0:
        return 0.0
    return float(numerator or 0) / den


def _gini(values: Iterable[float]) -> float:
    xs = [max(0.0, float(v)) for v in values]
    if not xs:
        return 0.0
    xs.sort()
    total = sum(xs)
    n = len(xs)
    if total <= 0 or n <= 0:
        return 0.0
    weighted = 0.0
    for idx, value in enumerate(xs, start=1):
        weighted += idx * value
    return (2.0 * weighted) / (n * total) - (n + 1.0) / n


def _classify_social_event(event: Event) -> str | None:
    event_type = str(event.event_type or "")
    description = str(event.description or "").lower()

    if event_type in COOPERATION_EVENT_TYPES:
        return "cooperation"
    if event_type in CONFLICT_EVENT_TYPES:
        return "conflict"

    if any(keyword in description for keyword in CONFLICT_KEYWORDS):
        return "conflict"
    if any(keyword in description for keyword in COOPERATION_KEYWORDS):
        return "cooperation"
    return None


def _compute_governance_participation(db: Session, window_start, window_end) -> tuple[int, int, float]:
    living_agents = int(
        db.query(Agent).filter(Agent.status != "dead").count()
    )

    participant_ids: set[int] = set()
    participant_ids.update(
        int(row[0])
        for row in db.query(Proposal.author_agent_id)
        .filter(
            Proposal.author_agent_id.isnot(None),
            Proposal.created_at >= window_start,
            Proposal.created_at < window_end,
        )
        .all()
    )
    participant_ids.update(
        int(row[0])
        for row in db.query(Vote.agent_id)
        .filter(
            Vote.agent_id.isnot(None),
            Vote.created_at >= window_start,
            Vote.created_at < window_end,
        )
        .all()
    )
    participant_ids.update(
        int(row[0])
        for row in db.query(Enforcement.initiator_agent_id)
        .filter(
            Enforcement.initiator_agent_id.isnot(None),
            Enforcement.created_at >= window_start,
            Enforcement.created_at < window_end,
        )
        .all()
    )
    participant_ids.update(
        int(row[0])
        for row in db.query(EnforcementVote.agent_id)
        .filter(
            EnforcementVote.agent_id.isnot(None),
            EnforcementVote.created_at >= window_start,
            EnforcementVote.created_at < window_end,
        )
        .all()
    )

    participants = len(participant_ids)
    rate = _safe_ratio(participants, living_agents)
    return living_agents, participants, rate


def _compute_inequality_gini(db: Session) -> float:
    living_agent_ids = [
        int(row[0])
        for row in db.query(Agent.id).filter(Agent.status != "dead").all()
    ]
    if not living_agent_ids:
        return 0.0

    totals_by_agent = {
        int(row.agent_id): float(row.total_qty or 0.0)
        for row in db.query(
            AgentInventory.agent_id,
            func.sum(AgentInventory.quantity).label("total_qty"),
        )
        .filter(
            AgentInventory.resource_type.in_(("food", "energy", "materials")),
            AgentInventory.agent_id.isnot(None),
        )
        .group_by(AgentInventory.agent_id)
        .all()
    }
    wealth_values = [float(totals_by_agent.get(agent_id, 0.0)) for agent_id in living_agent_ids]
    return _gini(wealth_values)


def _compute_coalition_edges(db: Session, window_start, window_end) -> set[str]:
    votes = (
        db.query(Vote.proposal_id, Vote.agent_id, Vote.vote)
        .filter(
            Vote.proposal_id.isnot(None),
            Vote.agent_id.isnot(None),
            Vote.created_at >= window_start,
            Vote.created_at < window_end,
            Vote.vote.in_(("yes", "no")),
        )
        .all()
    )
    votes_by_proposal: dict[int, list[tuple[int, str]]] = {}
    for proposal_id, agent_id, vote_value in votes:
        votes_by_proposal.setdefault(int(proposal_id), []).append((int(agent_id), str(vote_value)))

    pair_stats: dict[tuple[int, int], list[int]] = {}
    for entries in votes_by_proposal.values():
        count = len(entries)
        for idx in range(count):
            a_agent, a_vote = entries[idx]
            for jdx in range(idx + 1, count):
                b_agent, b_vote = entries[jdx]
                pair = (a_agent, b_agent) if a_agent < b_agent else (b_agent, a_agent)
                if pair not in pair_stats:
                    pair_stats[pair] = [0, 0]  # [agreements, total]
                pair_stats[pair][1] += 1
                if a_vote == b_vote:
                    pair_stats[pair][0] += 1

    edge_keys: set[str] = set()
    for (agent_a, agent_b), (agreements, total) in pair_stats.items():
        if total < 2:
            continue
        if _safe_ratio(agreements, total) >= 0.70:
            edge_keys.add(f"{agent_a}:{agent_b}")
    return edge_keys


def _compute_coalition_churn(previous_edges: set[str], current_edges: set[str]) -> float:
    if not previous_edges and not current_edges:
        return 0.0
    union = previous_edges | current_edges
    if not union:
        return 0.0
    removed = previous_edges - current_edges
    added = current_edges - previous_edges
    return _safe_ratio(len(removed) + len(added), len(union))


def compute_emergence_metrics(
    db: Session,
    *,
    window_start,
    window_end,
    previous_window_start=None,
    previous_window_end=None,
    previous_coalition_edge_keys: Optional[Iterable[str]] = None,
    previous_inequality_gini: float | None = None,
) -> dict:
    """
    Compute emergence metrics for a window.
    """
    events = (
        db.query(Event)
        .filter(Event.created_at >= window_start, Event.created_at < window_end)
        .all()
    )

    cooperation_events = 0
    conflict_events = 0
    for event in events:
        classification = _classify_social_event(event)
        if classification == "cooperation":
            cooperation_events += 1
        elif classification == "conflict":
            conflict_events += 1
    classified_total = cooperation_events + conflict_events

    living_agents, governance_participants, governance_participation_rate = _compute_governance_participation(
        db, window_start, window_end
    )
    inequality_gini = _compute_inequality_gini(db)

    current_edges = _compute_coalition_edges(db, window_start, window_end)
    if previous_coalition_edge_keys is not None:
        previous_edges = set(str(edge) for edge in previous_coalition_edge_keys if edge)
    elif previous_window_start is not None and previous_window_end is not None:
        previous_edges = _compute_coalition_edges(db, previous_window_start, previous_window_end)
    else:
        previous_edges = set()

    coalition_churn = _compute_coalition_churn(previous_edges, current_edges)

    inequality_trend = None
    if previous_inequality_gini is not None:
        inequality_trend = float(inequality_gini - float(previous_inequality_gini))

    return {
        "living_agents": int(living_agents),
        "governance_participants": int(governance_participants),
        "governance_participation_rate": float(governance_participation_rate),
        "coalition_edge_count": int(len(current_edges)),
        "coalition_edge_keys": sorted(current_edges),
        "coalition_churn": float(coalition_churn),
        "inequality_gini": float(inequality_gini),
        "inequality_trend": (None if inequality_trend is None else float(inequality_trend)),
        "conflict_events": int(conflict_events),
        "cooperation_events": int(cooperation_events),
        "conflict_rate": float(_safe_ratio(conflict_events, classified_total)),
        "cooperation_rate": float(_safe_ratio(cooperation_events, classified_total)),
    }


def _get_completed_simulation_day_window(db: Session):
    first_event = db.query(Event).order_by(Event.created_at.asc()).first()
    if not first_event or first_event.created_at is None:
        return None

    first_at = ensure_utc(first_event.created_at)
    now = now_utc()
    if first_at is None or now <= first_at:
        return None

    day_length_seconds = max(60, int(getattr(settings, "DAY_LENGTH_MINUTES", 60) or 60) * 60)
    elapsed_seconds = max(0.0, (now - first_at).total_seconds())
    current_day = int(elapsed_seconds // day_length_seconds) + 1
    completed_day = current_day - 1
    if completed_day < 1:
        return None

    window_start = first_at + timedelta(seconds=(completed_day - 1) * day_length_seconds)
    window_end = window_start + timedelta(seconds=day_length_seconds)
    return {
        "simulation_day": completed_day,
        "window_start_at": window_start,
        "window_end_at": window_end,
    }


async def persist_completed_day_snapshot() -> dict:
    """
    Persist one snapshot for the latest fully completed simulation day.
    Idempotent by `simulation_day`.
    """
    db = SessionLocal()
    try:
        window = _get_completed_simulation_day_window(db)
        if window is None:
            return {"persisted": False, "reason": "no_completed_day"}

        simulation_day = int(window["simulation_day"])
        existing = (
            db.query(EmergenceMetricSnapshot)
            .filter(EmergenceMetricSnapshot.simulation_day == simulation_day)
            .first()
        )
        if existing:
            return {
                "persisted": False,
                "reason": "already_exists",
                "simulation_day": simulation_day,
            }

        previous_snapshot = (
            db.query(EmergenceMetricSnapshot)
            .order_by(EmergenceMetricSnapshot.simulation_day.desc())
            .first()
        )
        previous_edges = list(previous_snapshot.coalition_edge_keys or []) if previous_snapshot else None
        previous_gini = float(previous_snapshot.inequality_gini) if previous_snapshot else None

        metrics = compute_emergence_metrics(
            db,
            window_start=window["window_start_at"],
            window_end=window["window_end_at"],
            previous_coalition_edge_keys=previous_edges,
            previous_inequality_gini=previous_gini,
        )

        snapshot = EmergenceMetricSnapshot(
            simulation_day=simulation_day,
            window_start_at=window["window_start_at"],
            window_end_at=window["window_end_at"],
            living_agents=metrics["living_agents"],
            governance_participants=metrics["governance_participants"],
            governance_participation_rate=metrics["governance_participation_rate"],
            coalition_edge_count=metrics["coalition_edge_count"],
            coalition_churn=metrics["coalition_churn"],
            coalition_edge_keys=metrics["coalition_edge_keys"],
            inequality_gini=metrics["inequality_gini"],
            inequality_trend=metrics["inequality_trend"],
            conflict_events=metrics["conflict_events"],
            cooperation_events=metrics["cooperation_events"],
            conflict_rate=metrics["conflict_rate"],
            cooperation_rate=metrics["cooperation_rate"],
        )
        db.add(snapshot)
        db.commit()

        logger.info(
            "Persisted emergence metrics snapshot (simulation_day=%s, churn=%.4f, gini=%.4f)",
            simulation_day,
            float(metrics["coalition_churn"]),
            float(metrics["inequality_gini"]),
        )
        return {
            "persisted": True,
            "simulation_day": simulation_day,
            "window_start_at": ensure_utc(window["window_start_at"]).isoformat(),
            "window_end_at": ensure_utc(window["window_end_at"]).isoformat(),
        }
    except Exception as e:
        db.rollback()
        message = str(e)
        if "emergence_metric_snapshots" in message and "does not exist" in message:
            logger.warning("Emergence snapshot table is not available yet; skipping persistence.")
            return {"persisted": False, "reason": "table_not_migrated"}
        logger.error("Failed to persist emergence metrics snapshot: %s", e)
        return {"persisted": False, "reason": "error", "error": str(e)}
    finally:
        db.close()
