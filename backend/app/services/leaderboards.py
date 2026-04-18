"""
Leaderboard Service

Calculates and tracks various rankings and statistics for agents.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import case, desc, func

from app.core.database import SessionLocal
from app.models.models import Agent, AgentInventory, Event, Vote, Message, Proposal
from app.services.lineage import (
    lineage_map_for_season,
    lineage_payload_for_agent_number,
    resolve_active_or_latest_season_id,
)
from app.services.live_run_scope import LiveRunWindow, get_live_run_window

logger = logging.getLogger(__name__)


@dataclass
class _LeaderboardContext:
    lineage_by_agent_number: dict[int, dict[str, Any]]
    all_agents_by_id: dict[int, Agent]
    active_agents_by_id: dict[int, Agent]


def _agent_identity_payload(agent: Agent, lineage_by_agent_number: dict[int, dict[str, Any]]) -> dict[str, Any]:
    lineage = lineage_payload_for_agent_number(int(agent.agent_number), lineage_by_agent_number)
    return {
        "agent_id": int(agent.id),
        "agent_number": int(agent.agent_number),
        "display_name": agent.display_name or f"Agent #{agent.agent_number}",
        "tier": int(agent.tier),
        "model_type": str(agent.model_type or ""),
        "personality_type": str(agent.personality_type or ""),
        "status": str(agent.status or "active"),
        "lineage_origin": lineage.get("lineage_origin"),
        "lineage_is_carryover": bool(lineage.get("lineage_is_carryover")),
        "lineage_is_fresh": bool(lineage.get("lineage_is_fresh")),
        "lineage_parent_agent_number": lineage.get("lineage_parent_agent_number"),
        "lineage_season_id": lineage.get("lineage_season_id"),
    }


def _resolve_context(db: Session) -> _LeaderboardContext:
    season_id = resolve_active_or_latest_season_id(db)
    lineage_by_agent_number = lineage_map_for_season(db, season_id=season_id)
    agents = db.query(Agent).all()
    all_agents_by_id = {int(agent.id): agent for agent in agents}
    active_agents_by_id = {
        int(agent.id): agent for agent in agents
        if str(agent.status or "active") == "active"
    }
    return _LeaderboardContext(
        lineage_by_agent_number=lineage_by_agent_number,
        all_agents_by_id=all_agents_by_id,
        active_agents_by_id=active_agents_by_id,
    )


def _ranked_entries(items: list[dict[str, Any]], *, sort_key: str, limit: int) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda item: (-float(item.get(sort_key) or 0), int(item.get("agent_number") or 0)))
    for index, item in enumerate(ranked[:limit], start=1):
        item["rank"] = index
    return ranked[:limit]


def _apply_run_window(query, column, run_window: LiveRunWindow | None):
    if run_window is None:
        return query
    if run_window.started_at is not None:
        query = query.filter(column >= run_window.started_at)
    if run_window.ended_at is not None:
        query = query.filter(column <= run_window.ended_at)
    return query


def get_wealth_leaderboard(
    limit: int = 10,
    *,
    db: Session | None = None,
    context: _LeaderboardContext | None = None,
) -> List[Dict[str, Any]]:
    """
    Get agents ranked by total wealth (food + energy + materials).
    """
    managed_session = db is None
    db = db or SessionLocal()
    try:
        context = context or _resolve_context(db)
        inventory_rows = db.query(
            AgentInventory.agent_id,
            func.coalesce(func.sum(AgentInventory.quantity), 0).label("total_wealth"),
            func.coalesce(func.sum(case((AgentInventory.resource_type == "food", AgentInventory.quantity), else_=0)), 0).label("food"),
            func.coalesce(func.sum(case((AgentInventory.resource_type == "energy", AgentInventory.quantity), else_=0)), 0).label("energy"),
            func.coalesce(func.sum(case((AgentInventory.resource_type == "materials", AgentInventory.quantity), else_=0)), 0).label("materials"),
        ).group_by(AgentInventory.agent_id).all()
        inventory_by_agent_id = {
            int(agent_id): {
                "total_wealth": float(total_wealth or 0),
                "food": float(food or 0),
                "energy": float(energy or 0),
                "materials": float(materials or 0),
            }
            for agent_id, total_wealth, food, energy, materials in inventory_rows
        }

        wealth_data = []
        for agent in context.active_agents_by_id.values():
            totals = inventory_by_agent_id.get(int(agent.id), {})
            payload = _agent_identity_payload(agent, context.lineage_by_agent_number)
            payload.update(
                {
                    "total_wealth": float(totals.get("total_wealth", 0)),
                    "food": float(totals.get("food", 0)),
                    "energy": float(totals.get("energy", 0)),
                    "materials": float(totals.get("materials", 0)),
                }
            )
            wealth_data.append(payload)

        return _ranked_entries(wealth_data, sort_key="total_wealth", limit=limit)
    finally:
        if managed_session:
            db.close()


def get_activity_leaderboard(
    hours: int = 24,
    limit: int = 10,
    *,
    db: Session | None = None,
    context: _LeaderboardContext | None = None,
    run_window: LiveRunWindow | None = None,
) -> List[Dict[str, Any]]:
    """
    Get agents ranked by number of actions in the last N hours.
    """
    managed_session = db is None
    db = db or SessionLocal()
    try:
        context = context or _resolve_context(db)
        time_threshold = datetime.utcnow() - timedelta(hours=hours)
        activity_query = db.query(
            Event.agent_id,
            func.count(Event.id).label('action_count')
        ).filter(
            Event.created_at >= time_threshold,
            Event.agent_id.isnot(None)
        )
        activity_rows = (
            _apply_run_window(activity_query, Event.created_at, run_window)
            .group_by(Event.agent_id)
            .order_by(desc('action_count'))
            .limit(limit)
            .all()
        )

        result = []
        for agent_id, action_count in activity_rows:
            agent = context.all_agents_by_id.get(int(agent_id))
            if agent:
                payload = _agent_identity_payload(agent, context.lineage_by_agent_number)
                payload.update(
                    {
                        "action_count": int(action_count or 0),
                    }
                )
                result.append(payload)

        return _ranked_entries(result, sort_key="action_count", limit=limit)
    finally:
        if managed_session:
            db.close()


def get_influence_leaderboard(
    limit: int = 10,
    *,
    db: Session | None = None,
    context: _LeaderboardContext | None = None,
    run_window: LiveRunWindow | None = None,
) -> List[Dict[str, Any]]:
    """
    Get agents ranked by "influence" - combination of:
    - Proposals created
    - Votes cast
    - Messages that received replies
    - Laws authored
    """
    managed_session = db is None
    db = db or SessionLocal()
    try:
        context = context or _resolve_context(db)
        proposal_rows = _apply_run_window(
            db.query(
            Proposal.author_agent_id,
            func.count(Proposal.id).label("proposal_count"),
            func.coalesce(func.sum(case((Proposal.status == "passed", 1), else_=0)), 0).label("successful_count"),
            ),
            Proposal.created_at,
            run_window,
        ).group_by(Proposal.author_agent_id).all()
        vote_rows = _apply_run_window(
            db.query(
            Vote.agent_id,
            func.count(Vote.id).label("vote_count"),
            ),
            Vote.created_at,
            run_window,
        ).group_by(Vote.agent_id).all()
        message_rows = _apply_run_window(
            db.query(
            Message.author_agent_id,
            func.count(Message.id).label("message_count"),
        ).filter(
            Message.message_type == "forum"
            ),
            Message.created_at,
            run_window,
        ).group_by(Message.author_agent_id).all()

        proposal_counts = {
            int(agent_id): {
                "proposals": int(proposal_count or 0),
                "successful_proposals": int(successful_count or 0),
            }
            for agent_id, proposal_count, successful_count in proposal_rows
            if agent_id is not None
        }
        vote_counts = {int(agent_id): int(vote_count or 0) for agent_id, vote_count in vote_rows if agent_id is not None}
        message_counts = {int(agent_id): int(message_count or 0) for agent_id, message_count in message_rows if agent_id is not None}

        influence_data = []
        for agent in context.all_agents_by_id.values():
            proposals = proposal_counts.get(int(agent.id), {}).get("proposals", 0)
            successful_proposals = proposal_counts.get(int(agent.id), {}).get("successful_proposals", 0)
            votes = vote_counts.get(int(agent.id), 0)
            messages = message_counts.get(int(agent.id), 0)

            # Calculate influence score
            # Successful proposals worth most, then proposals, then messages, then votes
            influence = (
                successful_proposals * 50 +
                proposals * 20 +
                messages * 5 +
                votes * 2
            )
            
            if influence > 0:
                payload = _agent_identity_payload(agent, context.lineage_by_agent_number)
                payload.update(
                    {
                        "influence_score": int(influence),
                        "proposals": int(proposals),
                        "successful_proposals": int(successful_proposals),
                        "votes": int(votes),
                        "messages": int(messages),
                    }
                )
                influence_data.append(payload)

        return _ranked_entries(influence_data, sort_key="influence_score", limit=limit)
    finally:
        if managed_session:
            db.close()


def get_producer_leaderboard(
    limit: int = 10,
    *,
    db: Session | None = None,
    context: _LeaderboardContext | None = None,
    run_window: LiveRunWindow | None = None,
) -> List[Dict[str, Any]]:
    """
    Get agents ranked by total resources produced.
    Based on work events.
    """
    managed_session = db is None
    db = db or SessionLocal()
    try:
        context = context or _resolve_context(db)
        work_rows = _apply_run_window(
            db.query(
            Event.agent_id,
            func.count(Event.id).label('work_count')
        ).filter(
            Event.event_type == "work"
            ),
            Event.created_at,
            run_window,
        ).group_by(Event.agent_id).order_by(desc('work_count')).limit(limit).all()

        result = []
        for agent_id, work_count in work_rows:
            agent = context.all_agents_by_id.get(int(agent_id))
            if agent:
                payload = _agent_identity_payload(agent, context.lineage_by_agent_number)
                payload.update(
                    {
                        "work_sessions": int(work_count or 0),
                    }
                )
                result.append(payload)

        return _ranked_entries(result, sort_key="work_sessions", limit=limit)
    finally:
        if managed_session:
            db.close()


def get_trader_leaderboard(
    limit: int = 10,
    *,
    db: Session | None = None,
    context: _LeaderboardContext | None = None,
    run_window: LiveRunWindow | None = None,
) -> List[Dict[str, Any]]:
    """
    Get agents ranked by trading activity.
    """
    managed_session = db is None
    db = db or SessionLocal()
    try:
        context = context or _resolve_context(db)
        trade_rows = _apply_run_window(
            db.query(
            Event.agent_id,
            func.count(Event.id).label('trade_count')
        ).filter(
            Event.event_type == "trade"
            ),
            Event.created_at,
            run_window,
        ).group_by(Event.agent_id).order_by(desc('trade_count')).limit(limit).all()

        result = []
        for agent_id, trade_count in trade_rows:
            agent = context.all_agents_by_id.get(int(agent_id))
            if agent:
                payload = _agent_identity_payload(agent, context.lineage_by_agent_number)
                payload.update(
                    {
                        "trades": int(trade_count or 0),
                    }
                )
                result.append(payload)

        return _ranked_entries(result, sort_key="trades", limit=limit)
    finally:
        if managed_session:
            db.close()


def get_all_leaderboards(*, scope: str = "active_run") -> Dict[str, List[Dict[str, Any]]]:
    """Get all leaderboard types."""
    db = SessionLocal()
    try:
        context = _resolve_context(db)
        run_window = get_live_run_window(db) if scope != "all" else None
        return {
            "wealth": get_wealth_leaderboard(db=db, context=context),
            "activity": get_activity_leaderboard(db=db, context=context, run_window=run_window),
            "influence": get_influence_leaderboard(db=db, context=context, run_window=run_window),
            "producers": get_producer_leaderboard(db=db, context=context, run_window=run_window),
            "traders": get_trader_leaderboard(db=db, context=context, run_window=run_window),
        }
    finally:
        db.close()


def get_agent_rankings(agent_id: int, *, scope: str = "active_run") -> Dict[str, Any]:
    """Get all rankings for a specific agent."""
    db = SessionLocal()
    try:
        context = _resolve_context(db)
        run_window = get_live_run_window(db) if scope != "all" else None
        wealth = get_wealth_leaderboard(limit=100, db=db, context=context)
        activity = get_activity_leaderboard(limit=100, db=db, context=context, run_window=run_window)
        influence = get_influence_leaderboard(limit=100, db=db, context=context, run_window=run_window)
    finally:
        db.close()
    
    def find_rank(leaderboard: List[Dict], agent_id: int) -> int:
        for entry in leaderboard:
            if entry["agent_id"] == agent_id:
                return entry["rank"]
        return -1
    
    return {
        "wealth_rank": find_rank(wealth, agent_id),
        "activity_rank": find_rank(activity, agent_id),
        "influence_rank": find_rank(influence, agent_id),
        "total_agents": len(wealth),
    }
