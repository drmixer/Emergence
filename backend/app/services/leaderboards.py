"""
Leaderboard Service

Calculates and tracks various rankings and statistics for agents.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.database import SessionLocal
from app.models.models import Agent, AgentInventory, AgentLineage, Event, Vote, Message, Proposal, SimulationRun

logger = logging.getLogger(__name__)


def _resolve_active_or_latest_season_id(db: Session) -> str | None:
    active_row = (
        db.query(SimulationRun.season_id)
        .filter(
            SimulationRun.season_id.isnot(None),
            SimulationRun.season_id != "",
            SimulationRun.ended_at.is_(None),
        )
        .order_by(SimulationRun.started_at.desc(), SimulationRun.id.desc())
        .first()
    )
    if active_row and str(active_row.season_id or "").strip():
        return str(active_row.season_id).strip()

    latest_row = (
        db.query(SimulationRun.season_id)
        .filter(
            SimulationRun.season_id.isnot(None),
            SimulationRun.season_id != "",
        )
        .order_by(SimulationRun.started_at.desc(), SimulationRun.id.desc())
        .first()
    )
    if latest_row and str(latest_row.season_id or "").strip():
        return str(latest_row.season_id).strip()
    return None


def _lineage_map_for_season(db: Session, *, season_id: str | None) -> dict[int, dict[str, Any]]:
    rows: list[AgentLineage] = []
    clean_season_id = str(season_id or "").strip()
    if clean_season_id:
        rows = (
            db.query(AgentLineage)
            .filter(AgentLineage.season_id == clean_season_id)
            .all()
        )
    if not rows:
        rows = (
            db.query(AgentLineage)
            .order_by(AgentLineage.created_at.desc(), AgentLineage.id.desc())
            .all()
        )

    by_child: dict[int, dict[str, Any]] = {}
    for row in rows:
        child_number = int(row.child_agent_number or 0)
        if child_number <= 0 or child_number in by_child:
            continue
        origin = str(row.origin or "").strip()
        by_child[child_number] = {
            "lineage_origin": (origin if origin in {"carryover", "fresh"} else None),
            "lineage_season_id": str(row.season_id or "").strip() or None,
            "lineage_parent_agent_number": (
                int(row.parent_agent_number) if row.parent_agent_number is not None else None
            ),
        }
    return by_child


def _agent_identity_payload(agent: Agent, lineage_by_agent_number: dict[int, dict[str, Any]]) -> dict[str, Any]:
    lineage = lineage_by_agent_number.get(int(agent.agent_number), {})
    origin = lineage.get("lineage_origin")
    return {
        "agent_id": int(agent.id),
        "agent_number": int(agent.agent_number),
        "display_name": agent.display_name or f"Agent #{agent.agent_number}",
        "tier": int(agent.tier),
        "model_type": str(agent.model_type or ""),
        "personality_type": str(agent.personality_type or ""),
        "status": str(agent.status or "active"),
        "lineage_origin": origin,
        "lineage_is_carryover": bool(origin == "carryover"),
        "lineage_is_fresh": bool(origin == "fresh"),
        "lineage_parent_agent_number": lineage.get("lineage_parent_agent_number"),
        "lineage_season_id": lineage.get("lineage_season_id"),
    }


def get_wealth_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get agents ranked by total wealth (food + energy + materials).
    """
    db = SessionLocal()
    
    try:
        season_id = _resolve_active_or_latest_season_id(db)
        lineage_by_agent_number = _lineage_map_for_season(db, season_id=season_id)
        agents = db.query(Agent).filter(Agent.status == "active").all()
        
        wealth_data = []
        for agent in agents:
            inventory = db.query(AgentInventory).filter(
                AgentInventory.agent_id == agent.id
            ).all()
            
            total_wealth = sum(float(inv.quantity) for inv in inventory)
            food = next((float(inv.quantity) for inv in inventory if inv.resource_type == "food"), 0)
            energy = next((float(inv.quantity) for inv in inventory if inv.resource_type == "energy"), 0)
            materials = next((float(inv.quantity) for inv in inventory if inv.resource_type == "materials"), 0)
            
            payload = _agent_identity_payload(agent, lineage_by_agent_number)
            payload.update(
                {
                    "total_wealth": total_wealth,
                    "food": food,
                    "energy": energy,
                    "materials": materials,
                }
            )
            wealth_data.append(payload)
        
        # Sort by total wealth
        wealth_data.sort(key=lambda x: x["total_wealth"], reverse=True)
        
        # Add rank
        for i, agent in enumerate(wealth_data[:limit]):
            agent["rank"] = i + 1
        
        return wealth_data[:limit]
        
    finally:
        db.close()


def get_activity_leaderboard(hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get agents ranked by number of actions in the last N hours.
    """
    db = SessionLocal()
    
    try:
        season_id = _resolve_active_or_latest_season_id(db)
        lineage_by_agent_number = _lineage_map_for_season(db, season_id=season_id)
        time_threshold = datetime.utcnow() - timedelta(hours=hours)
        
        activity = db.query(
            Event.agent_id,
            func.count(Event.id).label('action_count')
        ).filter(
            Event.created_at >= time_threshold,
            Event.agent_id.isnot(None)
        ).group_by(Event.agent_id).order_by(desc('action_count')).limit(limit).all()
        
        result = []
        for i, (agent_id, action_count) in enumerate(activity):
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                payload = _agent_identity_payload(agent, lineage_by_agent_number)
                payload.update(
                    {
                        "rank": i + 1,
                        "action_count": int(action_count or 0),
                    }
                )
                result.append(payload)
        
        return result
        
    finally:
        db.close()


def get_influence_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get agents ranked by "influence" - combination of:
    - Proposals created
    - Votes cast
    - Messages that received replies
    - Laws authored
    """
    db = SessionLocal()
    
    try:
        season_id = _resolve_active_or_latest_season_id(db)
        lineage_by_agent_number = _lineage_map_for_season(db, season_id=season_id)
        agents = db.query(Agent).all()
        
        influence_data = []
        for agent in agents:
            # Count proposals created
            proposals = db.query(Proposal).filter(
                Proposal.author_agent_id == agent.id
            ).count()
            
            # Count successful proposals (passed)
            successful_proposals = db.query(Proposal).filter(
                Proposal.author_agent_id == agent.id,
                Proposal.status == "passed"
            ).count()
            
            # Count votes cast
            votes = db.query(Vote).filter(Vote.agent_id == agent.id).count()
            
            # Count forum messages
            messages = db.query(Message).filter(
                Message.author_agent_id == agent.id,
                Message.message_type == "forum"
            ).count()
            
            # Calculate influence score
            # Successful proposals worth most, then proposals, then messages, then votes
            influence = (
                successful_proposals * 50 +
                proposals * 20 +
                messages * 5 +
                votes * 2
            )
            
            if influence > 0:
                payload = _agent_identity_payload(agent, lineage_by_agent_number)
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
        
        # Sort by influence
        influence_data.sort(key=lambda x: x["influence_score"], reverse=True)
        
        # Add rank
        for i, agent in enumerate(influence_data[:limit]):
            agent["rank"] = i + 1
        
        return influence_data[:limit]
        
    finally:
        db.close()


def get_producer_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get agents ranked by total resources produced.
    Based on work events.
    """
    db = SessionLocal()
    
    try:
        season_id = _resolve_active_or_latest_season_id(db)
        lineage_by_agent_number = _lineage_map_for_season(db, season_id=season_id)
        work_events = db.query(
            Event.agent_id,
            func.count(Event.id).label('work_count')
        ).filter(
            Event.event_type == "work"
        ).group_by(Event.agent_id).order_by(desc('work_count')).limit(limit).all()
        
        result = []
        for i, (agent_id, work_count) in enumerate(work_events):
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                payload = _agent_identity_payload(agent, lineage_by_agent_number)
                payload.update(
                    {
                        "rank": i + 1,
                        "work_sessions": int(work_count or 0),
                    }
                )
                result.append(payload)
        
        return result
        
    finally:
        db.close()


def get_trader_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get agents ranked by trading activity.
    """
    db = SessionLocal()
    
    try:
        season_id = _resolve_active_or_latest_season_id(db)
        lineage_by_agent_number = _lineage_map_for_season(db, season_id=season_id)
        trade_events = db.query(
            Event.agent_id,
            func.count(Event.id).label('trade_count')
        ).filter(
            Event.event_type == "trade"
        ).group_by(Event.agent_id).order_by(desc('trade_count')).limit(limit).all()
        
        result = []
        for i, (agent_id, trade_count) in enumerate(trade_events):
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                payload = _agent_identity_payload(agent, lineage_by_agent_number)
                payload.update(
                    {
                        "rank": i + 1,
                        "trades": int(trade_count or 0),
                    }
                )
                result.append(payload)
        
        return result
        
    finally:
        db.close()


def get_all_leaderboards() -> Dict[str, List[Dict[str, Any]]]:
    """Get all leaderboard types."""
    return {
        "wealth": get_wealth_leaderboard(),
        "activity": get_activity_leaderboard(),
        "influence": get_influence_leaderboard(),
        "producers": get_producer_leaderboard(),
        "traders": get_trader_leaderboard(),
    }


def get_agent_rankings(agent_id: int) -> Dict[str, Any]:
    """Get all rankings for a specific agent."""
    wealth = get_wealth_leaderboard(limit=100)
    activity = get_activity_leaderboard(limit=100)
    influence = get_influence_leaderboard(limit=100)
    
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
