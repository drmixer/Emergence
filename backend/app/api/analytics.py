"""
Analytics & Highlights API Router
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.services.leaderboards import (
    get_wealth_leaderboard,
    get_activity_leaderboard,
    get_influence_leaderboard,
    get_producer_leaderboard,
    get_trader_leaderboard,
    get_all_leaderboards,
    get_agent_rankings,
)
from app.services.featured_events import (
    get_featured_events,
    get_dramatic_events,
)
from app.services.summaries import (
    generate_daily_summary,
    get_story_so_far,
)
from app.core.database import SessionLocal
from app.models.models import Event

router = APIRouter()


# ===== LEADERBOARDS =====

@router.get("/leaderboards")
def get_leaderboards():
    """Get all leaderboard types."""
    return get_all_leaderboards()


@router.get("/leaderboards/wealth")
def leaderboard_wealth(limit: int = Query(10, le=50)):
    """Get agents ranked by total wealth."""
    return get_wealth_leaderboard(limit)


@router.get("/leaderboards/activity")
def leaderboard_activity(
    limit: int = Query(10, le=50),
    hours: int = Query(24, le=168)
):
    """Get agents ranked by recent activity."""
    return get_activity_leaderboard(hours, limit)


@router.get("/leaderboards/influence")
def leaderboard_influence(limit: int = Query(10, le=50)):
    """Get agents ranked by influence score."""
    return get_influence_leaderboard(limit)


@router.get("/leaderboards/producers")
def leaderboard_producers(limit: int = Query(10, le=50)):
    """Get agents ranked by production."""
    return get_producer_leaderboard(limit)


@router.get("/leaderboards/traders")
def leaderboard_traders(limit: int = Query(10, le=50)):
    """Get agents ranked by trading activity."""
    return get_trader_leaderboard(limit)


@router.get("/agents/{agent_id}/rankings")
def agent_rankings(agent_id: int):
    """Get ranking positions for a specific agent."""
    return get_agent_rankings(agent_id)


# ===== FEATURED EVENTS =====

@router.get("/featured")
def featured_events(limit: int = Query(20, le=100)):
    """Get featured/highlighted events."""
    return get_featured_events(limit)


@router.get("/dramatic")
def dramatic_events(
    limit: int = Query(10, le=50),
    hours: int = Query(24, le=168)
):
    """Get dramatic events (close votes, dormancies, etc)."""
    return get_dramatic_events(hours, limit)


# ===== SUMMARIES =====

@router.get("/summaries")
def get_summaries(limit: int = Query(10, le=50)):
    """Get recent daily summaries."""
    db = SessionLocal()
    try:
        summaries = db.query(Event).filter(
            Event.event_type == "daily_summary"
        ).order_by(Event.created_at.desc()).limit(limit).all()
        
        return [
            {
                "day_number": s.metadata.get("day_number"),
                "summary": s.metadata.get("summary"),
                "stats": s.metadata.get("stats"),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in summaries
        ]
    finally:
        db.close()


@router.get("/summaries/latest")
def get_latest_summary():
    """Get the most recent daily summary."""
    db = SessionLocal()
    try:
        summary = db.query(Event).filter(
            Event.event_type == "daily_summary"
        ).order_by(Event.created_at.desc()).first()
        
        if not summary:
            return {"message": "No summaries yet", "summary": None}
        
        return {
            "day_number": summary.metadata.get("day_number"),
            "summary": summary.metadata.get("summary"),
            "stats": summary.metadata.get("stats"),
            "created_at": summary.created_at.isoformat() if summary.created_at else None,
        }
    finally:
        db.close()


@router.get("/story")
async def story_so_far():
    """Get the 'Story So Far' overview."""
    try:
        story = await get_story_so_far()
        return {"story": story}
    except Exception as e:
        return {"story": "The simulation has just begun...", "error": str(e)}


@router.post("/summaries/generate")
async def trigger_summary_generation(day_number: int = Query(1)):
    """
    Manually trigger a summary generation.
    Admin endpoint for testing.
    """
    try:
        summary = await generate_daily_summary(day_number)
        return {"day_number": day_number, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== WORLD EVENTS =====

@router.get("/world-events")
def get_world_events(limit: int = Query(20, le=100)):
    """Get recent world/crisis events."""
    db = SessionLocal()
    try:
        events = db.query(Event).filter(
            Event.event_type == "world_event"
        ).order_by(Event.created_at.desc()).limit(limit).all()
        
        return [
            {
                "id": e.id,
                "event_name": e.metadata.get("event_name"),
                "description": e.description,
                "effect": e.metadata.get("effect"),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    finally:
        db.close()


@router.get("/active-effects")
def get_active_effects():
    """Get currently active environmental effects."""
    from app.services.events_generator import event_generator
    
    effects = event_generator.get_active_effects()
    
    return [
        {
            "event_id": e.event_id,
            "effect": e.effect,
            "expires_at": e.expires_at.isoformat(),
        }
        for e in effects
    ]
