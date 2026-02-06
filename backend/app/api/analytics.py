"""
Analytics & Highlights API Router
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from sqlalchemy import text

from app.core.config import settings
from app.core.time import ensure_utc, now_utc
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
from app.models.models import Event, Agent, Law, Message, Proposal, Vote, AgentInventory, GlobalResources

router = APIRouter()

def _gini(values):
    xs = [float(v) for v in values if v is not None]
    if not xs:
        return 0.0
    xs = sorted(max(0.0, v) for v in xs)
    n = len(xs)
    total = sum(xs)
    if total == 0 or n == 0:
        return 0.0
    cum = 0.0
    for i, x in enumerate(xs, start=1):
        cum += i * x
    return (2.0 * cum) / (n * total) - (n + 1.0) / n


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
                "day_number": (s.event_metadata or {}).get("day_number"),
                "summary": (s.event_metadata or {}).get("summary"),
                "stats": (s.event_metadata or {}).get("stats"),
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
            "day_number": (summary.event_metadata or {}).get("day_number"),
            "summary": (summary.event_metadata or {}).get("summary"),
            "stats": (summary.event_metadata or {}).get("stats"),
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
                "event_name": (e.event_metadata or {}).get("event_name"),
                "description": e.description,
                "effect": (e.event_metadata or {}).get("effect"),
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


# ===== FRONTEND DASHBOARD ENDPOINTS =====

@router.get("/overview")
def overview():
    """Key simulation stats for dashboards."""
    db = SessionLocal()
    try:
        total_agents = db.query(Agent).count()
        active_agents = db.query(Agent).filter(Agent.status == "active").count()
        dormant_agents = db.query(Agent).filter(Agent.status == "dormant").count()
        dead_agents = db.query(Agent).filter(Agent.status == "dead").count()

        total_messages = db.query(Message).count()
        forum_posts = db.query(Message).filter(Message.message_type == "forum_post").count()
        forum_replies = db.query(Message).filter(Message.message_type == "forum_reply").count()
        direct_messages = db.query(Message).filter(Message.message_type == "direct_message").count()

        total_proposals = db.query(Proposal).count()
        active_proposals = db.query(Proposal).filter(Proposal.status == "active").count()
        passed_proposals = db.query(Proposal).filter(Proposal.status == "passed").count()
        failed_proposals = db.query(Proposal).filter(Proposal.status == "failed").count()

        total_laws = db.query(Law).count()
        active_laws = db.query(Law).filter(Law.active.is_(True)).count()

        most_recent_event = db.query(Event).order_by(Event.created_at.desc()).first()
        first_event = db.query(Event).order_by(Event.created_at.asc()).first()

        now = now_utc()
        first_at = ensure_utc(first_event.created_at) if first_event and first_event.created_at else None
        latest_at = ensure_utc(most_recent_event.created_at) if most_recent_event and most_recent_event.created_at else None

        # Sim day number: default configuration is 1 real hour = 1 sim day.
        day_length_seconds = max(1, int(settings.DAY_LENGTH_MINUTES) * 60)
        day_number = (
            int(((now - first_at).total_seconds()) // day_length_seconds) + 1
            if first_at
            else 0
        )

        # Critical agents: count agents with low food/energy (thresholds match the context-builder warning).
        critical_food = (
            db.query(AgentInventory)
            .filter(AgentInventory.resource_type == "food", AgentInventory.quantity < 2)
            .count()
        )
        critical_energy = (
            db.query(AgentInventory)
            .filter(AgentInventory.resource_type == "energy", AgentInventory.quantity < 2)
            .count()
        )

        # Global resource pool baselines (seeded via scripts/seed_agents.py).
        globals_rows = db.query(GlobalResources).all()
        common_pool = {str(gr.resource_type): float(gr.in_common_pool or 0) for gr in globals_rows}
        reserves_total = {str(gr.resource_type): float(gr.total_amount or 0) for gr in globals_rows}

        # Capacity estimate: starting resources per agent + global reserves.
        capacity = {
            "food": float(total_agents * settings.STARTING_FOOD) + float(reserves_total.get("food", 0)),
            "energy": float(total_agents * settings.STARTING_ENERGY) + float(reserves_total.get("energy", 0)),
            "materials": float(total_agents * settings.STARTING_MATERIALS) + float(reserves_total.get("materials", 0)),
            "land": float(reserves_total.get("land", 0)),
        }

        return {
            "day_number": day_number,
            "agents": {
                "total": total_agents,
                "active": active_agents,
                "dormant": dormant_agents,
                "dead": dead_agents,
            },
            "critical": {"food_agents": critical_food, "energy_agents": critical_energy},
            "messages": {
                "total": total_messages,
                "forum_posts": forum_posts,
                "forum_replies": forum_replies,
                "direct_messages": direct_messages,
            },
            "proposals": {
                "total": total_proposals,
                "active": active_proposals,
                "passed": passed_proposals,
                "failed": failed_proposals,
            },
            "laws": {"total": total_laws, "active": active_laws},
            "events": {
                "first": first_at.isoformat() if first_at else None,
                "latest": latest_at.isoformat() if latest_at else None,
            },
            "resources": {
                "common_pool": common_pool,
                "reserves_total": reserves_total,
                "capacity_estimate": capacity,
            },
        }
    finally:
        db.close()


@router.get("/factions")
def factions():
    """
    Lightweight grouping heuristic (placeholder for real clustering).
    Currently groups by personality type.
    """
    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        by_personality = {}
        for a in agents:
            key = a.personality_type
            by_personality.setdefault(key, []).append(a.agent_number)

        return [
            {
                "faction": personality,
                "member_count": len(members),
                "members": sorted(members),
            }
            for personality, members in sorted(by_personality.items(), key=lambda kv: kv[0])
        ]
    finally:
        db.close()


@router.get("/voting")
def voting_blocs():
    """Voting breakdown by tier/personality for recent proposals."""
    db = SessionLocal()
    try:
        recent_proposals = (
            db.query(Proposal)
            .order_by(Proposal.created_at.desc())
            .limit(10)
            .all()
        )

        out = []
        for p in recent_proposals:
            votes = (
                db.query(Vote, Agent)
                .join(Agent, Agent.id == Vote.agent_id)
                .filter(Vote.proposal_id == p.id)
                .all()
            )
            by_tier = {}
            by_personality = {}
            for v, a in votes:
                by_tier.setdefault(str(a.tier), {"yes": 0, "no": 0, "abstain": 0})
                by_tier[str(a.tier)][v.vote] = by_tier[str(a.tier)].get(v.vote, 0) + 1

                by_personality.setdefault(
                    a.personality_type, {"yes": 0, "no": 0, "abstain": 0}
                )
                by_personality[a.personality_type][v.vote] = (
                    by_personality[a.personality_type].get(v.vote, 0) + 1
                )

            out.append(
                {
                    "proposal_id": p.id,
                    "title": p.title,
                    "status": p.status,
                    "by_tier": by_tier,
                    "by_personality": by_personality,
                }
            )

        return out
    finally:
        db.close()


@router.get("/wealth")
def wealth_distribution():
    """Wealth distribution metrics derived from inventory totals."""
    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        inventories = db.query(AgentInventory).all()

        by_agent = {}
        for inv in inventories:
            by_agent.setdefault(inv.agent_id, 0.0)
            by_agent[inv.agent_id] += float(inv.quantity or 0)

        wealth = [by_agent.get(a.id, 0.0) for a in agents]
        wealth_sorted = sorted(wealth)

        def pct(p):
            if not wealth_sorted:
                return 0.0
            idx = int(round((p / 100.0) * (len(wealth_sorted) - 1)))
            idx = max(0, min(len(wealth_sorted) - 1, idx))
            return float(wealth_sorted[idx])

        return {
            "count": len(wealth_sorted),
            "gini": _gini(wealth_sorted),
            "min": float(wealth_sorted[0]) if wealth_sorted else 0.0,
            "p25": pct(25),
            "median": pct(50),
            "p75": pct(75),
            "max": float(wealth_sorted[-1]) if wealth_sorted else 0.0,
        }
    finally:
        db.close()


@router.get("/model-attribution")
def model_attribution(
    hours: int = Query(24, ge=1, le=24 * 30),
    run_id: Optional[str] = Query(None),
):
    """
    Break down model behavior by assigned model_type and resolved model.

    - `by_model_type`: attribution-safe view keyed to assigned model cohort.
    - `by_resolved_model`: actual execution model/provider used for each call.
    - `action_outcomes_by_model_type`: downstream action/event outcomes by assigned model_type.
    """
    db = SessionLocal()
    try:
        time_filter = "created_at >= NOW() - (:hours || ' hours')::interval"
        run_filter = "AND run_id = :run_id" if run_id else ""
        params = {"hours": hours}
        if run_id:
            params["run_id"] = run_id

        by_model_type = db.execute(
            text(
                f"""
                SELECT
                    model_type,
                    COUNT(*) AS calls,
                    COALESCE(SUM(CASE WHEN provider = 'openrouter' THEN 1 ELSE 0 END), 0) AS openrouter_calls,
                    COALESCE(SUM(CASE WHEN provider = 'openrouter' AND byok_used IS TRUE THEN 1 ELSE 0 END), 0) AS byok_calls,
                    COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
                    COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(AVG(total_tokens), 0) AS avg_tokens_per_call,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                    COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                FROM llm_usage
                WHERE {time_filter}
                  AND model_type IS NOT NULL
                  {run_filter}
                GROUP BY model_type
                ORDER BY calls DESC, model_type ASC
                """
            ),
            params,
        ).fetchall()

        by_resolved_model = db.execute(
            text(
                f"""
                SELECT
                    provider,
                    resolved_model_name,
                    COUNT(*) AS calls,
                    COALESCE(SUM(CASE WHEN byok_used IS TRUE THEN 1 ELSE 0 END), 0) AS byok_calls,
                    COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
                    COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(AVG(total_tokens), 0) AS avg_tokens_per_call,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                    COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                FROM llm_usage
                WHERE {time_filter}
                  AND resolved_model_name IS NOT NULL
                  {run_filter}
                GROUP BY provider, resolved_model_name
                ORDER BY calls DESC, provider ASC, resolved_model_name ASC
                """
            ),
            params,
        ).fetchall()

        action_run_filter = ""
        action_params = {"hours": hours}
        if run_id:
            action_run_filter = """
                  AND e.agent_id IN (
                      SELECT DISTINCT u.agent_id
                      FROM llm_usage u
                      WHERE u.agent_id IS NOT NULL
                        AND u.created_at >= NOW() - (:hours || ' hours')::interval
                        AND u.run_id = :run_id
                  )
            """
            action_params["run_id"] = run_id

        action_outcomes = db.execute(
            text(
                f"""
                SELECT
                    a.model_type AS model_type,
                    COUNT(*) AS total_events,
                    COALESCE(SUM(CASE WHEN e.event_type = 'invalid_action' THEN 1 ELSE 0 END), 0) AS invalid_actions,
                    COALESCE(SUM(CASE WHEN e.event_type = 'work' THEN 1 ELSE 0 END), 0) AS work_actions,
                    COALESCE(SUM(CASE WHEN e.event_type IN ('forum_post', 'forum_reply', 'direct_message') THEN 1 ELSE 0 END), 0) AS communication_actions,
                    COALESCE(SUM(CASE WHEN e.event_type IN ('vote', 'create_proposal', 'vote_enforcement', 'initiate_sanction', 'initiate_seizure', 'initiate_exile') THEN 1 ELSE 0 END), 0) AS governance_actions,
                    COALESCE(SUM(CASE WHEN e.event_type = 'trade' THEN 1 ELSE 0 END), 0) AS trade_actions,
                    COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') = 'checkpoint' THEN 1 ELSE 0 END), 0) AS checkpoint_actions,
                    COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') = 'deterministic_fallback' THEN 1 ELSE 0 END), 0) AS deterministic_fallback_actions,
                    COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'llm_parse_ok') = 'false' THEN 1 ELSE 0 END), 0) AS llm_parse_fail_actions,
                    COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'llm_parse_likely_truncated') = 'true' THEN 1 ELSE 0 END), 0) AS llm_parse_likely_truncated_actions,
                    COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'llm_parse_retries') ~ '^[0-9]+$' AND ((e.event_metadata -> 'runtime' ->> 'llm_parse_retries')::int) > 0 THEN 1 ELSE 0 END), 0) AS llm_parse_retry_actions,
                    COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'llm_parse_retries') ~ '^[0-9]+$' THEN (e.event_metadata -> 'runtime' ->> 'llm_parse_retries')::int ELSE 0 END), 0) AS llm_parse_retries_total
                FROM events e
                JOIN agents a ON a.id = e.agent_id
                WHERE e.created_at >= NOW() - (:hours || ' hours')::interval
                  AND e.agent_id IS NOT NULL
                  {action_run_filter}
                GROUP BY a.model_type
                ORDER BY total_events DESC, a.model_type ASC
                """
            ),
            action_params,
        ).fetchall()

        def _usage_row_to_dict(row):
            calls = int(row.calls or 0)
            success_calls = int(row.success_calls or 0)
            fallback_calls = int(row.fallback_calls or 0)
            openrouter_calls = int(getattr(row, "openrouter_calls", 0) or 0)
            if openrouter_calls == 0 and str(getattr(row, "provider", "") or "") == "openrouter":
                openrouter_calls = calls
            byok_calls = int(getattr(row, "byok_calls", 0) or 0)
            return {
                "calls": calls,
                "success_calls": success_calls,
                "fallback_calls": fallback_calls,
                "success_rate": (success_calls / calls) if calls else 0.0,
                "fallback_rate": (fallback_calls / calls) if calls else 0.0,
                "byok_calls": byok_calls,
                "byok_rate": (byok_calls / calls) if calls else 0.0,
                "byok_rate_openrouter": (byok_calls / openrouter_calls) if openrouter_calls else 0.0,
                "total_tokens": int(row.total_tokens or 0),
                "avg_tokens_per_call": float(row.avg_tokens_per_call or 0.0),
                "avg_latency_ms": float(row.avg_latency_ms or 0.0),
                "estimated_cost_usd": float(row.estimated_cost_usd or 0.0),
            }

        model_type_payload = []
        for row in by_model_type:
            payload = {"model_type": row.model_type}
            payload.update(_usage_row_to_dict(row))
            model_type_payload.append(payload)

        resolved_payload = []
        for row in by_resolved_model:
            payload = {"provider": row.provider, "resolved_model_name": row.resolved_model_name}
            payload.update(_usage_row_to_dict(row))
            resolved_payload.append(payload)

        outcomes_payload = [
            {
                "model_type": row.model_type,
                "total_events": int(row.total_events or 0),
                "invalid_actions": int(row.invalid_actions or 0),
                "work_actions": int(row.work_actions or 0),
                "communication_actions": int(row.communication_actions or 0),
                "governance_actions": int(row.governance_actions or 0),
                "trade_actions": int(row.trade_actions or 0),
                "checkpoint_actions": int(row.checkpoint_actions or 0),
                "deterministic_fallback_actions": int(row.deterministic_fallback_actions or 0),
                "llm_parse_fail_actions": int(row.llm_parse_fail_actions or 0),
                "llm_parse_likely_truncated_actions": int(row.llm_parse_likely_truncated_actions or 0),
                "llm_parse_retry_actions": int(row.llm_parse_retry_actions or 0),
                "llm_parse_retries_total": int(row.llm_parse_retries_total or 0),
            }
            for row in action_outcomes
        ]

        total_calls = sum(item["calls"] for item in model_type_payload)
        total_events = sum(item["total_events"] for item in outcomes_payload)

        return {
            "window_hours": hours,
            "run_id": run_id,
            "totals": {
                "llm_calls": total_calls,
                "events": total_events,
                "model_types": len(model_type_payload),
                "resolved_models": len(resolved_payload),
            },
            "by_model_type": model_type_payload,
            "by_resolved_model": resolved_payload,
            "action_outcomes_by_model_type": outcomes_payload,
        }
    finally:
        db.close()
