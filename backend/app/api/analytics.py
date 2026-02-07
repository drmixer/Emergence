"""
Analytics & Highlights API Router
"""
import logging
from fastapi import APIRouter, HTTPException, Query
from datetime import date, datetime, timedelta, timezone
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
from app.services.usage_budget import usage_budget
from app.services.emergence_metrics import compute_emergence_metrics
from app.core.database import SessionLocal
from app.models.models import (
    Event,
    Agent,
    Law,
    Message,
    Proposal,
    Vote,
    AgentInventory,
    GlobalResources,
    EmergenceMetricSnapshot,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Section 7 viewer-surface heuristics.
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
COOPERATION_EVENT_TYPES = {
    "trade",
    "direct_message",
    "forum_reply",
    "forum_post",
    "agent_revived",
}
ALLIANCE_KEYWORDS = {"alliance", "ally", "coalition", "truce", "bloc"}
CONFLICT_KEYWORDS = {"conflict", "hostile", "fight", "war", "betray", "sanction", "exile", "retaliation"}
COOPERATION_KEYWORDS = {"cooperate", "cooperation", "help", "support", "rescue", "aid"}
PLOT_TURN_BASE_SCORES = {
    "law_passed": 95,
    "proposal_resolved": 90,
    "world_event": 92,
    "agent_died": 95,
    "agent_exiled": 88,
    "agent_sanctioned": 82,
    "resources_seized": 80,
    "became_dormant": 80,
    "agent_revived": 78,
    "awakened": 74,
    "create_proposal": 60,
    "vote_enforcement": 72,
}


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


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    den = float(denominator or 0)
    if den <= 0:
        return 0.0
    return float(numerator or 0) / den


def _resolve_day_key(day: Optional[str]) -> date:
    if not day:
        return now_utc().date()
    try:
        return date.fromisoformat(day)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid `day`; expected YYYY-MM-DD") from e


def _day_window_utc(day_key: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day_key, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _serialize_emergence_snapshot(row: EmergenceMetricSnapshot) -> dict:
    return {
        "simulation_day": int(row.simulation_day or 0),
        "window_start_at": ensure_utc(row.window_start_at).isoformat() if row.window_start_at else None,
        "window_end_at": ensure_utc(row.window_end_at).isoformat() if row.window_end_at else None,
        "living_agents": int(row.living_agents or 0),
        "governance_participants": int(row.governance_participants or 0),
        "governance_participation_rate": float(row.governance_participation_rate or 0.0),
        "coalition_edge_count": int(row.coalition_edge_count or 0),
        "coalition_churn": (None if row.coalition_churn is None else float(row.coalition_churn)),
        "inequality_gini": float(row.inequality_gini or 0.0),
        "inequality_trend": (None if row.inequality_trend is None else float(row.inequality_trend)),
        "conflict_events": int(row.conflict_events or 0),
        "cooperation_events": int(row.cooperation_events or 0),
        "conflict_rate": float(row.conflict_rate or 0.0),
        "cooperation_rate": float(row.cooperation_rate or 0.0),
        "created_at": ensure_utc(row.created_at).isoformat() if row.created_at else None,
    }


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _titleize_key(value: str) -> str:
    return str(value or "").replace("_", " ").strip().title() or "Unknown Event"


def _estimate_affected_agents(db, effect: dict, living_agents: int) -> int:
    if not isinstance(effect, dict):
        return 0
    if any(k in effect for k in ("reduce_all_agents", "consumption_modifier", "disable_communication", "all_resources")):
        return living_agents
    resource = str(effect.get("resource") or "").strip().lower()
    if resource in {"food", "energy", "materials", "land"}:
        return int(
            db.query(AgentInventory.agent_id)
            .filter(AgentInventory.resource_type == resource)
            .distinct()
            .count()
        )
    return living_agents


def _score_plot_turn(event: Event) -> int:
    event_type = str(event.event_type or "")
    description = str(event.description or "").lower()
    metadata = event.event_metadata or {}

    score = int(PLOT_TURN_BASE_SCORES.get(event_type, 35))
    if event.agent_id:
        score += 4
    if _contains_any(description, ALLIANCE_KEYWORDS):
        score += 8
    if _contains_any(description, CONFLICT_KEYWORDS):
        score += 9
    if _contains_any(description, COOPERATION_KEYWORDS):
        score += 4
    if event_type == "proposal_resolved" and str(metadata.get("result") or "") in {"passed", "failed", "expired"}:
        score += 10
    if event_type in {"agent_died", "agent_exiled"}:
        score += 6
    return min(score, 100)


def _plot_turn_category(event: Event) -> str:
    event_type = str(event.event_type or "")
    description = str(event.description or "").lower()
    if event_type == "world_event":
        return "crisis"
    if event_type in {"law_passed", "proposal_resolved", "vote_enforcement", "create_proposal"}:
        return "governance"
    if event_type in CONFLICT_EVENT_TYPES or _contains_any(description, CONFLICT_KEYWORDS):
        return "conflict"
    if _contains_any(description, ALLIANCE_KEYWORDS):
        return "alliance"
    if event_type in COOPERATION_EVENT_TYPES or _contains_any(description, COOPERATION_KEYWORDS):
        return "cooperation"
    return "notable"


def _plot_turn_title(event: Event) -> str:
    metadata = event.event_metadata or {}
    event_type = str(event.event_type or "")
    if event_type == "world_event":
        return str(metadata.get("event_name") or "World Event")
    if event_type == "law_passed":
        return f"Law Passed: {metadata.get('title') or 'Untitled'}"
    if event_type == "proposal_resolved":
        title = str(metadata.get("title") or metadata.get("proposal_title") or "Proposal")
        result = str(metadata.get("result") or "").strip().lower()
        if result:
            return f"{title} ({result})"
        return title
    if event_type == "agent_died":
        return "Permanent Death"
    if event_type == "agent_exiled":
        return "Exile Enforced"
    return _titleize_key(event_type)


def _serialize_plot_turn(event: Event, score: int, actor_label: str | None = None) -> dict:
    return {
        "event_id": int(event.id or 0),
        "event_type": str(event.event_type or ""),
        "title": _plot_turn_title(event),
        "description": str(event.description or ""),
        "salience": int(score),
        "category": _plot_turn_category(event),
        "actor": actor_label,
        "created_at": ensure_utc(event.created_at).isoformat() if event.created_at else None,
        "metadata": event.event_metadata or {},
    }


def _collect_scored_plot_turns(
    db,
    *,
    window_start: datetime,
    now: datetime,
    min_salience: int,
    candidate_limit: int,
) -> list[tuple[int, datetime, dict]]:
    candidates = (
        db.query(Event)
        .filter(Event.created_at >= window_start)
        .order_by(Event.created_at.desc())
        .limit(candidate_limit)
        .all()
    )

    agent_ids = {int(e.agent_id) for e in candidates if e.agent_id is not None}
    agent_names = {}
    if agent_ids:
        agent_rows = db.query(Agent).filter(Agent.id.in_(agent_ids)).all()
        for agent in agent_rows:
            agent_names[int(agent.id)] = agent.display_name or f"Agent #{agent.agent_number}"

    scored: list[tuple[int, datetime, dict]] = []
    for event in candidates:
        score = _score_plot_turn(event)
        if score < min_salience:
            continue
        created_at = ensure_utc(event.created_at) or now
        actor = agent_names.get(int(event.agent_id)) if event.agent_id is not None else None
        scored.append((score, created_at, _serialize_plot_turn(event, score=score, actor_label=actor)))
    return scored


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


@router.get("/crisis-strip")
def crisis_strip(limit: int = Query(6, ge=1, le=20)):
    """
    Active crisis/effect strip with timers and rough affected-agent counts.
    """
    from app.services.events_generator import event_generator

    now = now_utc()
    active_effects = event_generator.get_active_effects()

    db = SessionLocal()
    try:
        living_agents = int(db.query(Agent).filter(Agent.status != "dead").count())
        recent_world_events = (
            db.query(Event)
            .filter(Event.event_type == "world_event")
            .order_by(Event.created_at.desc())
            .limit(100)
            .all()
        )
        recent_by_event_id = {}
        for event in recent_world_events:
            meta = event.event_metadata or {}
            event_id = str(meta.get("event_id") or "").strip()
            if event_id and event_id not in recent_by_event_id:
                recent_by_event_id[event_id] = event

        strip_items = []
        for active in active_effects:
            event_id = str(active.event_id or "").strip()
            effect = active.effect if isinstance(active.effect, dict) else {}
            source_event = recent_by_event_id.get(event_id)
            expires_at = ensure_utc(active.expires_at)
            seconds_remaining = max(
                0,
                int((expires_at - now).total_seconds()) if expires_at else 0,
            )
            source_meta = (source_event.event_metadata or {}) if source_event else {}
            name = str(source_meta.get("event_name") or _titleize_key(event_id))
            description = str(source_event.description) if source_event and source_event.description else ""
            affected_agents = _estimate_affected_agents(db, effect, living_agents=living_agents)
            strip_items.append(
                {
                    "event_id": event_id,
                    "name": name,
                    "description": description,
                    "effect": effect,
                    "affected_agents": int(affected_agents),
                    "seconds_remaining": seconds_remaining,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "started_at": ensure_utc(source_event.created_at).isoformat() if source_event and source_event.created_at else None,
                }
            )

        strip_items.sort(
            key=lambda item: (
                -int(item.get("seconds_remaining") or 0),
                str(item.get("name") or ""),
            )
        )
        return {
            "active_count": len(strip_items),
            "generated_at": now.isoformat(),
            "items": strip_items[:limit],
        }
    finally:
        db.close()


@router.get("/plot-turns")
def plot_turns(
    limit: int = Query(8, ge=1, le=30),
    hours: int = Query(48, ge=1, le=24 * 14),
    min_salience: int = Query(60, ge=1, le=100),
):
    """
    High-salience events suitable for a viewer-facing "Plot Turns" panel.
    """
    now = now_utc()
    window_start = now - timedelta(hours=hours)

    db = SessionLocal()
    try:
        scored = _collect_scored_plot_turns(
            db,
            window_start=window_start,
            now=now,
            min_salience=min_salience,
            candidate_limit=max(40, limit * 12),
        )

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        payload = [item[2] for item in scored[:limit]]
        return {
            "window_hours": hours,
            "min_salience": min_salience,
            "count": len(payload),
            "items": payload,
        }
    finally:
        db.close()


@router.get("/plot-turns/replay")
def plot_turns_replay(
    hours: int = Query(24, ge=1, le=24 * 7),
    min_salience: int = Query(55, ge=1, le=100),
    bucket_minutes: int = Query(30, ge=10, le=120),
    limit: int = Query(220, ge=20, le=500),
):
    """
    Chronological high-salience replay stream with bucketed counts for time-scrub UI.
    """
    now = now_utc()
    window_start = now - timedelta(hours=hours)
    bucket_seconds = int(bucket_minutes * 60)
    total_seconds = max(1, int((now - window_start).total_seconds()))
    bucket_count = max(1, (total_seconds + bucket_seconds - 1) // bucket_seconds)

    db = SessionLocal()
    try:
        scored = _collect_scored_plot_turns(
            db,
            window_start=window_start,
            now=now,
            min_salience=min_salience,
            candidate_limit=max(limit * 6, 240),
        )
        scored.sort(key=lambda item: (item[1], item[0]))
        if len(scored) > limit:
            scored = scored[-limit:]

        events = [item[2] for item in scored]

        buckets = []
        for idx in range(bucket_count):
            bucket_start = window_start + timedelta(seconds=idx * bucket_seconds)
            bucket_end = min(now, bucket_start + timedelta(seconds=bucket_seconds))
            buckets.append(
                {
                    "index": idx,
                    "bucket_start": bucket_start.isoformat(),
                    "bucket_end": bucket_end.isoformat(),
                    "label": bucket_start.strftime("%H:%M"),
                    "event_count": 0,
                    "max_salience": 0,
                    "dominant_category": None,
                    "category_counts": {},
                }
            )

        for _, created_at, payload in scored:
            offset = int((created_at - window_start).total_seconds())
            idx = max(0, min(bucket_count - 1, offset // bucket_seconds))
            bucket = buckets[idx]
            bucket["event_count"] += 1
            bucket["max_salience"] = max(int(bucket["max_salience"]), int(payload["salience"]))
            category = str(payload.get("category") or "notable")
            category_counts = bucket["category_counts"]
            category_counts[category] = int(category_counts.get(category, 0)) + 1
            bucket["dominant_category"] = max(
                category_counts,
                key=lambda key: int(category_counts.get(key, 0)),
            )

        return {
            "window_hours": hours,
            "min_salience": min_salience,
            "bucket_minutes": bucket_minutes,
            "bucket_count": bucket_count,
            "count": len(events),
            "items": events,
            "buckets": buckets,
        }
    finally:
        db.close()


@router.get("/social-dynamics")
def social_dynamics(days: int = Query(7, ge=3, le=30)):
    """
    Daily social signal series: alliance/conflict/cooperation deltas + coalition churn.
    """
    now = now_utc()
    start_day = now.date() - timedelta(days=days - 1)
    window_start = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)

    day_keys = [(start_day + timedelta(days=idx)).isoformat() for idx in range(days)]
    buckets = {
        day_key: {
            "day_key": day_key,
            "conflict_events": 0,
            "cooperation_events": 0,
            "alliance_signals": 0,
            "coalition_churn": None,
            "inequality_trend": None,
        }
        for day_key in day_keys
    }

    db = SessionLocal()
    try:
        events = db.query(Event).filter(Event.created_at >= window_start).all()
        for event in events:
            created_at = ensure_utc(event.created_at)
            if not created_at:
                continue
            day_key = created_at.date().isoformat()
            if day_key not in buckets:
                continue

            event_type = str(event.event_type or "")
            description = str(event.description or "").lower()
            if event_type in CONFLICT_EVENT_TYPES or _contains_any(description, CONFLICT_KEYWORDS):
                buckets[day_key]["conflict_events"] += 1
            if event_type in COOPERATION_EVENT_TYPES or _contains_any(description, COOPERATION_KEYWORDS):
                buckets[day_key]["cooperation_events"] += 1
            if _contains_any(description, ALLIANCE_KEYWORDS):
                buckets[day_key]["alliance_signals"] += 1

        try:
            snapshots = (
                db.query(EmergenceMetricSnapshot)
                .filter(EmergenceMetricSnapshot.created_at >= window_start)
                .order_by(EmergenceMetricSnapshot.created_at.asc())
                .all()
            )
        except Exception:
            db.rollback()
            snapshots = []
        for snapshot in snapshots:
            created_at = ensure_utc(snapshot.created_at)
            if not created_at:
                continue
            day_key = created_at.date().isoformat()
            if day_key not in buckets:
                continue
            buckets[day_key]["coalition_churn"] = (
                None if snapshot.coalition_churn is None else float(snapshot.coalition_churn)
            )
            buckets[day_key]["inequality_trend"] = (
                None if snapshot.inequality_trend is None else float(snapshot.inequality_trend)
            )

        series = []
        for day_key in day_keys:
            row = dict(buckets[day_key])
            d = date.fromisoformat(day_key)
            row["day_label"] = d.strftime("%b %d")
            series.append(row)

        latest = series[-1] if series else None
        previous = series[-2] if len(series) > 1 else None
        deltas = None
        if latest and previous:
            deltas = {
                "conflict_events_delta": int(latest["conflict_events"] - previous["conflict_events"]),
                "cooperation_events_delta": int(latest["cooperation_events"] - previous["cooperation_events"]),
                "alliance_signals_delta": int(latest["alliance_signals"] - previous["alliance_signals"]),
            }

        return {
            "days": days,
            "window_start_utc": window_start.isoformat(),
            "window_end_utc": now.isoformat(),
            "series": series,
            "latest": latest,
            "deltas_vs_prev_day": deltas,
        }
    finally:
        db.close()


@router.get("/class-mobility")
def class_mobility(hours: int = Query(24, ge=1, le=24 * 14)):
    """
    Inequality + mobility proxy cards for the viewer dashboard.
    """
    now = now_utc()
    window_start = now - timedelta(hours=hours)

    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        inventories = db.query(AgentInventory).all()

        wealth_by_agent: dict[int, float] = {}
        for inv in inventories:
            if inv.agent_id is None:
                continue
            wealth_by_agent.setdefault(int(inv.agent_id), 0.0)
            wealth_by_agent[int(inv.agent_id)] += float(inv.quantity or 0.0)

        status_counts = {"active": 0, "dormant": 0, "dead": 0}
        tier_stats = {
            tier: {"tier": tier, "agents": 0, "living_agents": 0, "total_wealth": 0.0}
            for tier in (1, 2, 3, 4)
        }
        living_wealth_values: list[float] = []

        for agent in agents:
            status = str(agent.status or "active")
            if status in status_counts:
                status_counts[status] += 1

            tier = int(agent.tier or 4)
            tier_entry = tier_stats.setdefault(
                tier,
                {"tier": tier, "agents": 0, "living_agents": 0, "total_wealth": 0.0},
            )
            tier_entry["agents"] += 1
            wealth = float(wealth_by_agent.get(int(agent.id), 0.0))
            tier_entry["total_wealth"] += wealth

            if status != "dead":
                tier_entry["living_agents"] += 1
                living_wealth_values.append(wealth)

        living_agents = int(status_counts["active"] + status_counts["dormant"])
        sorted_wealth = sorted(living_wealth_values)
        wealth_total = float(sum(sorted_wealth))

        def _pct(p: float) -> float:
            if not sorted_wealth:
                return 0.0
            idx = int(round((p / 100.0) * (len(sorted_wealth) - 1)))
            idx = max(0, min(len(sorted_wealth) - 1, idx))
            return float(sorted_wealth[idx])

        status_event_types = {"awakened", "became_dormant", "agent_died", "agent_revived"}
        status_events = (
            db.query(Event)
            .filter(Event.created_at >= window_start, Event.event_type.in_(tuple(status_event_types)))
            .all()
        )
        status_change_counts = {
            "awakened": 0,
            "became_dormant": 0,
            "agent_died": 0,
            "agent_revived": 0,
        }
        for event in status_events:
            event_type = str(event.event_type or "")
            if event_type in status_change_counts:
                status_change_counts[event_type] += 1

        upward_signals = int(status_change_counts["awakened"] + status_change_counts["agent_revived"])
        downward_signals = int(status_change_counts["became_dormant"] + status_change_counts["agent_died"])
        total_signals = upward_signals + downward_signals

        try:
            latest_snapshot = (
                db.query(EmergenceMetricSnapshot)
                .order_by(EmergenceMetricSnapshot.simulation_day.desc())
                .first()
            )
        except Exception:
            db.rollback()
            latest_snapshot = None
        inequality_trend = (
            None
            if not latest_snapshot or latest_snapshot.inequality_trend is None
            else float(latest_snapshot.inequality_trend)
        )

        tier_payload = []
        for tier in sorted(tier_stats):
            row = tier_stats[tier]
            agent_count = int(row["agents"])
            tier_payload.append(
                {
                    "tier": int(tier),
                    "agents": agent_count,
                    "living_agents": int(row["living_agents"]),
                    "total_wealth": float(row["total_wealth"]),
                    "avg_wealth": _safe_ratio(row["total_wealth"], agent_count),
                    "wealth_share": _safe_ratio(row["total_wealth"], wealth_total),
                }
            )

        return {
            "window_hours": hours,
            "window_start_utc": window_start.isoformat(),
            "window_end_utc": now.isoformat(),
            "status_counts": {
                **status_counts,
                "living": living_agents,
            },
            "status_change_counts": status_change_counts,
            "mobility": {
                "upward_signals": upward_signals,
                "downward_signals": downward_signals,
                "net_signal": int(upward_signals - downward_signals),
                "signal_flux": int(total_signals),
                "signal_flux_rate": _safe_ratio(total_signals, living_agents),
            },
            "inequality": {
                "gini": _gini(sorted_wealth),
                "p25": _pct(25),
                "median": _pct(50),
                "p75": _pct(75),
                "max": float(sorted_wealth[-1]) if sorted_wealth else 0.0,
                "trend": inequality_trend,
            },
            "tiers": tier_payload,
        }
    finally:
        db.close()


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


@router.get("/usage/budget-status")
def usage_budget_status():
    """
    Current UTC-day budget/counter status.
    """
    snapshot = usage_budget.get_snapshot()
    calls_total = int(snapshot.calls_total or 0)
    calls_or_free = int(snapshot.calls_openrouter_free or 0)
    calls_groq = int(snapshot.calls_groq or 0)
    cost_usd = float(snapshot.estimated_cost_usd or 0.0)

    soft_budget = float(getattr(settings, "LLM_DAILY_BUDGET_USD_SOFT", 0.0) or 0.0)
    hard_budget = float(getattr(settings, "LLM_DAILY_BUDGET_USD_HARD", 0.0) or 0.0)
    max_total = int(getattr(settings, "LLM_MAX_CALLS_PER_DAY_TOTAL", 0) or 0)
    max_or_free = int(getattr(settings, "LLM_MAX_CALLS_PER_DAY_OPENROUTER_FREE", 0) or 0)
    max_groq = int(getattr(settings, "LLM_MAX_CALLS_PER_DAY_GROQ", 0) or 0)

    soft_budget_reached = bool(soft_budget > 0 and cost_usd >= soft_budget)
    hard_budget_reached = bool(hard_budget > 0 and cost_usd >= hard_budget)
    soft_total_reached = bool(max_total > 0 and calls_total >= int(max_total * 0.85))
    hard_total_reached = bool(max_total > 0 and calls_total >= max_total)
    soft_or_free_reached = bool(max_or_free > 0 and calls_or_free >= int(max_or_free * 0.85))
    hard_or_free_reached = bool(max_or_free > 0 and calls_or_free >= max_or_free)
    soft_groq_reached = bool(max_groq > 0 and calls_groq >= int(max_groq * 0.85))
    hard_groq_reached = bool(max_groq > 0 and calls_groq >= max_groq)

    return {
        "day_key_utc": snapshot.day_key.isoformat(),
        "snapshot": {
            "calls_total": calls_total,
            "calls_openrouter_free": calls_or_free,
            "calls_groq": calls_groq,
            "estimated_cost_usd": cost_usd,
        },
        "limits": {
            "daily_budget_usd_soft": soft_budget,
            "daily_budget_usd_hard": hard_budget,
            "max_calls_per_day_total": max_total,
            "max_calls_per_day_openrouter_free": max_or_free,
            "max_calls_per_day_groq": max_groq,
        },
        "utilization": {
            "budget_soft_pct": (_safe_ratio(cost_usd, soft_budget) * 100.0) if soft_budget > 0 else None,
            "budget_hard_pct": (_safe_ratio(cost_usd, hard_budget) * 100.0) if hard_budget > 0 else None,
            "calls_total_pct": (_safe_ratio(calls_total, max_total) * 100.0) if max_total > 0 else None,
            "calls_openrouter_free_pct": (_safe_ratio(calls_or_free, max_or_free) * 100.0) if max_or_free > 0 else None,
            "calls_groq_pct": (_safe_ratio(calls_groq, max_groq) * 100.0) if max_groq > 0 else None,
        },
        "flags": {
            "soft_cap_active": bool(
                soft_budget_reached or soft_total_reached or soft_or_free_reached or soft_groq_reached
            ),
            "hard_cap_reached": bool(
                hard_budget_reached or hard_total_reached or hard_or_free_reached or hard_groq_reached
            ),
            "soft_budget_reached": soft_budget_reached,
            "hard_budget_reached": hard_budget_reached,
            "soft_calls_total_reached": soft_total_reached,
            "hard_calls_total_reached": hard_total_reached,
            "soft_calls_openrouter_free_reached": soft_or_free_reached,
            "hard_calls_openrouter_free_reached": hard_or_free_reached,
            "soft_calls_groq_reached": soft_groq_reached,
            "hard_calls_groq_reached": hard_groq_reached,
        },
    }


@router.get("/usage/daily")
def usage_daily(
    day: Optional[str] = Query(None, description="UTC date (YYYY-MM-DD). Defaults to today."),
    run_id: Optional[str] = Query(None, description="Optional run_id filter."),
):
    """
    Daily usage and runtime-mode telemetry.

    Exposes:
    - calls/day by provider/model
    - estimated spend/day
    - fallback rate
    - checkpoint vs deterministic action ratio
    """
    day_key = _resolve_day_key(day)
    start_ts, end_ts = _day_window_utc(day_key)

    llm_run_filter = "AND run_id = :run_id" if run_id else ""
    llm_params: dict[str, object] = {"day_key": day_key}
    if run_id:
        llm_params["run_id"] = run_id

    event_run_filter = ""
    event_params: dict[str, object] = {"start_ts": start_ts, "end_ts": end_ts, "day_key": day_key}
    if run_id:
        event_run_filter = """
          AND e.agent_id IN (
              SELECT DISTINCT u.agent_id
              FROM llm_usage u
              WHERE u.day_key = :day_key
                AND u.run_id = :run_id
                AND u.agent_id IS NOT NULL
          )
        """
        event_params["run_id"] = run_id

    db = SessionLocal()
    try:
        totals = db.execute(
            text(
                f"""
                SELECT
                    COUNT(*) AS calls,
                    COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
                    COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                FROM llm_usage
                WHERE day_key = :day_key
                {llm_run_filter}
                """
            ),
            llm_params,
        ).first()

        by_provider_rows = db.execute(
            text(
                f"""
                SELECT
                    provider,
                    COUNT(*) AS calls,
                    COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
                    COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                FROM llm_usage
                WHERE day_key = :day_key
                {llm_run_filter}
                GROUP BY provider
                ORDER BY calls DESC, provider ASC
                """
            ),
            llm_params,
        ).fetchall()

        by_model_rows = db.execute(
            text(
                f"""
                SELECT
                    provider,
                    COALESCE(resolved_model_name, model_name) AS model_name,
                    COUNT(*) AS calls,
                    COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
                    COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                FROM llm_usage
                WHERE day_key = :day_key
                {llm_run_filter}
                GROUP BY provider, COALESCE(resolved_model_name, model_name)
                ORDER BY calls DESC, provider ASC, model_name ASC
                """
            ),
            llm_params,
        ).fetchall()

        runtime_row = db.execute(
            text(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') = 'checkpoint' THEN 1 ELSE 0 END), 0) AS checkpoint_actions,
                    COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') = 'deterministic_fallback' THEN 1 ELSE 0 END), 0) AS deterministic_actions
                FROM events e
                WHERE e.created_at >= :start_ts
                  AND e.created_at < :end_ts
                  {event_run_filter}
                """
            ),
            event_params,
        ).first()

        total_calls = int((totals.calls if totals else 0) or 0)
        success_calls = int((totals.success_calls if totals else 0) or 0)
        fallback_calls = int((totals.fallback_calls if totals else 0) or 0)
        checkpoint_actions = int((runtime_row.checkpoint_actions if runtime_row else 0) or 0)
        deterministic_actions = int((runtime_row.deterministic_actions if runtime_row else 0) or 0)
        runtime_total = checkpoint_actions + deterministic_actions

        by_provider = []
        for row in by_provider_rows:
            calls = int(row.calls or 0)
            fallback = int(row.fallback_calls or 0)
            by_provider.append(
                {
                    "provider": row.provider,
                    "calls": calls,
                    "success_calls": int(row.success_calls or 0),
                    "fallback_calls": fallback,
                    "fallback_rate": _safe_ratio(fallback, calls),
                    "total_tokens": int(row.total_tokens or 0),
                    "estimated_cost_usd": float(row.estimated_cost_usd or 0.0),
                }
            )

        by_model = []
        for row in by_model_rows:
            calls = int(row.calls or 0)
            fallback = int(row.fallback_calls or 0)
            by_model.append(
                {
                    "provider": row.provider,
                    "model_name": row.model_name,
                    "calls": calls,
                    "success_calls": int(row.success_calls or 0),
                    "fallback_calls": fallback,
                    "fallback_rate": _safe_ratio(fallback, calls),
                    "total_tokens": int(row.total_tokens or 0),
                    "estimated_cost_usd": float(row.estimated_cost_usd or 0.0),
                }
            )

        return {
            "day_key_utc": day_key.isoformat(),
            "run_id": run_id,
            "llm_totals": {
                "calls": total_calls,
                "success_calls": success_calls,
                "fallback_calls": fallback_calls,
                "success_rate": _safe_ratio(success_calls, total_calls),
                "fallback_rate": _safe_ratio(fallback_calls, total_calls),
                "prompt_tokens": int((totals.prompt_tokens if totals else 0) or 0),
                "completion_tokens": int((totals.completion_tokens if totals else 0) or 0),
                "total_tokens": int((totals.total_tokens if totals else 0) or 0),
                "estimated_cost_usd": float((totals.estimated_cost_usd if totals else 0.0) or 0.0),
            },
            "by_provider": by_provider,
            "by_model": by_model,
            "runtime_actions": {
                "checkpoint_actions": checkpoint_actions,
                "deterministic_actions": deterministic_actions,
                "total_runtime_actions": runtime_total,
                "checkpoint_ratio": _safe_ratio(checkpoint_actions, runtime_total),
                "deterministic_ratio": _safe_ratio(deterministic_actions, runtime_total),
            },
        }
    finally:
        db.close()


@router.get("/emergence/metrics")
def emergence_metrics(
    hours: int = Query(24, ge=1, le=24 * 30),
):
    """
    Current emergence metrics window.

    Includes:
    - coalition churn
    - inequality trend
    - governance participation
    - conflict/cooperation rates
    """
    now = now_utc()
    window_end = now
    window_start = now - timedelta(hours=hours)
    previous_window_start = window_start - timedelta(hours=hours)
    previous_window_end = window_start

    db = SessionLocal()
    try:
        try:
            previous_snapshot = (
                db.query(EmergenceMetricSnapshot)
                .order_by(EmergenceMetricSnapshot.simulation_day.desc())
                .first()
            )
        except Exception:
            db.rollback()
            previous_snapshot = None
        metrics = compute_emergence_metrics(
            db,
            window_start=window_start,
            window_end=window_end,
            previous_window_start=previous_window_start,
            previous_window_end=previous_window_end,
            previous_inequality_gini=(
                float(previous_snapshot.inequality_gini) if previous_snapshot and previous_snapshot.inequality_gini is not None else None
            ),
        )
        metrics.pop("coalition_edge_keys", None)
        return {
            "window_hours": hours,
            "window_start_utc": window_start.isoformat(),
            "window_end_utc": window_end.isoformat(),
            "metrics": metrics,
        }
    finally:
        db.close()


@router.get("/emergence/snapshots")
def emergence_snapshots(
    limit: int = Query(30, ge=1, le=365),
):
    """
    Persisted per-day emergence metric snapshots for trend analysis.
    """
    db = SessionLocal()
    try:
        try:
            rows = (
                db.query(EmergenceMetricSnapshot)
                .order_by(EmergenceMetricSnapshot.simulation_day.desc())
                .limit(limit)
                .all()
            )
        except Exception as e:
            db.rollback()
            message = str(e)
            if "emergence_metric_snapshots" in message and "does not exist" in message:
                logger.info("Emergence snapshots table not migrated yet; returning empty payload.")
            else:
                logger.warning("Emergence snapshots unavailable: %s", e)
            rows = []
        payload = [_serialize_emergence_snapshot(row) for row in reversed(rows)]
        return {
            "count": len(payload),
            "snapshots": payload,
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
