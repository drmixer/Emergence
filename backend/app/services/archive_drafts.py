"""Archive draft generation service."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import now_utc
from app.models.models import Agent, ArchiveArticle, Event, Law, Message
from app.services.runtime_config import runtime_config_service

logger = logging.getLogger(__name__)


@dataclass
class WeeklyDraftResult:
    article: ArchiveArticle
    created: bool


def _resolve_unique_slug(db: Session, base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while db.query(ArchiveArticle.id).filter(ArchiveArticle.slug == slug).first():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def _bounded_int(raw_value: Any, *, fallback: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = fallback
    return min(max(value, minimum), maximum)


def _resolve_scheduled_anchor(now_ts: datetime, *, weekday: int, hour: int, minute: int) -> datetime:
    scheduled_today = now_ts.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_since_target = (now_ts.weekday() - weekday) % 7
    return scheduled_today - timedelta(days=days_since_target)


def _build_sections_payload(
    *,
    now_ts: datetime,
    since: datetime,
    run_mode: str,
    run_id: str,
    simulation_active: bool,
    simulation_paused: bool,
    total_events: int,
    messages_count: int,
    active_agents: int,
    forum_actions: int,
    proposals_created: int,
    votes_cast: int,
    laws_passed: int,
    active_laws_total: int,
    deaths_count: int,
    confidence: str,
) -> list[dict[str, Any]]:
    window_label = f"{since.date().isoformat()} to {now_ts.date().isoformat()} UTC"
    return [
        {
            "heading": "Run Context and Data Window",
            "paragraphs": [
                f"Window analyzed: {window_label}.",
                f"Run mode: {run_mode}. Run ID: {run_id}. Simulation active: {'yes' if simulation_active else 'no'}. Paused: {'yes' if simulation_paused else 'no'}.",
                "This is an auto-generated draft for operator review. All claims should be validated before publish.",
            ],
        },
        {
            "heading": "Participation and Activity",
            "paragraphs": [
                f"Observed {total_events} events and {messages_count} messages over the window.",
                f"{active_agents} distinct agents appeared in event logs, with {forum_actions} forum actions recorded.",
                "Use this section to annotate whether participation was broad-based or concentrated in a small cluster of agents.",
            ],
        },
        {
            "heading": "Governance Signal",
            "paragraphs": [
                f"Governance activity included {proposals_created} proposal events, {votes_cast} vote events, and {laws_passed} newly passed laws.",
                f"Total currently active laws: {active_laws_total}.",
                "Interpretation should distinguish between procedural throughput (more proposals/votes) and policy stability (which laws persisted).",
            ],
        },
        {
            "heading": "Survival Pressure",
            "paragraphs": [
                f"Deaths recorded in the window: {deaths_count}.",
                "Track whether mortality was isolated or clustered, and whether social behavior shifted after spikes in death pressure.",
                "If death count is zero, note whether that reflects genuine stability or a low-activity period.",
            ],
        },
        {
            "heading": "Confidence and Next Checks",
            "paragraphs": [
                f"Initial confidence in this weekly signal: {confidence} (based on event volume).",
                "Before publish: verify run continuity, check for telemetry gaps, and attach the most relevant dashboard snapshots.",
                "Do not publish conclusions that extend beyond the observed evidence window.",
            ],
            "references": [
                {"label": "Live Dashboard", "href": "/dashboard"},
                {"label": "Ops Console", "href": "/ops"},
            ],
        },
    ]


def generate_weekly_draft(
    db: Session,
    *,
    actor_id: str,
    lookback_days: int,
    anchor_date: date | None = None,
    now_ts: datetime | None = None,
    skip_if_exists_for_anchor: bool = True,
) -> WeeklyDraftResult:
    now_value = now_ts or now_utc()
    lookback = _bounded_int(lookback_days, fallback=7, minimum=1, maximum=30)
    slug_anchor = anchor_date or now_value.date()
    base_slug = f"weekly-brief-{slug_anchor.isoformat()}"

    if skip_if_exists_for_anchor:
        existing = (
            db.query(ArchiveArticle)
            .filter(ArchiveArticle.slug.like(f"{base_slug}%"))
            .order_by(ArchiveArticle.updated_at.desc(), ArchiveArticle.id.desc())
            .first()
        )
        if existing:
            return WeeklyDraftResult(article=existing, created=False)

    since = now_value - timedelta(days=lookback)
    effective = runtime_config_service.get_effective(db)

    total_events = int(db.query(func.count(Event.id)).filter(Event.created_at >= since).scalar() or 0)
    active_agents = int(
        db.query(func.count(distinct(Event.agent_id)))
        .filter(Event.created_at >= since, Event.agent_id.isnot(None))
        .scalar()
        or 0
    )
    forum_actions = int(
        db.query(func.count(Event.id))
        .filter(Event.created_at >= since, Event.event_type.in_(["forum_post", "forum_reply"]))
        .scalar()
        or 0
    )
    proposals_created = int(
        db.query(func.count(Event.id))
        .filter(Event.created_at >= since, Event.event_type == "create_proposal")
        .scalar()
        or 0
    )
    votes_cast = int(
        db.query(func.count(Event.id))
        .filter(Event.created_at >= since, Event.event_type == "vote")
        .scalar()
        or 0
    )
    laws_passed = int(db.query(func.count(Law.id)).filter(Law.passed_at >= since).scalar() or 0)
    active_laws_total = int(db.query(func.count(Law.id)).filter(Law.active.is_(True)).scalar() or 0)
    messages_count = int(db.query(func.count(Message.id)).filter(Message.created_at >= since).scalar() or 0)
    deaths_count = int(db.query(func.count(Agent.id)).filter(Agent.died_at >= since).scalar() or 0)

    run_id = str(effective.get("SIMULATION_RUN_ID") or "").strip() or "not-set"
    run_mode = str(effective.get("SIMULATION_RUN_MODE") or "unknown")
    simulation_active = bool(effective.get("SIMULATION_ACTIVE", False))
    simulation_paused = bool(effective.get("SIMULATION_PAUSED", False))

    if total_events >= 1000:
        confidence = "high"
    elif total_events >= 250:
        confidence = "medium"
    else:
        confidence = "low"

    window_label = f"{since.date().isoformat()} to {now_value.date().isoformat()} UTC"
    summary = (
        f"Weekly draft for {window_label}: {total_events} events, {active_agents} participating agents, "
        f"{proposals_created} proposals, {votes_cast} votes, {laws_passed} laws passed, and {deaths_count} deaths observed."
    )
    sections_payload = _build_sections_payload(
        now_ts=now_value,
        since=since,
        run_mode=run_mode,
        run_id=run_id,
        simulation_active=simulation_active,
        simulation_paused=simulation_paused,
        total_events=total_events,
        messages_count=messages_count,
        active_agents=active_agents,
        forum_actions=forum_actions,
        proposals_created=proposals_created,
        votes_cast=votes_cast,
        laws_passed=laws_passed,
        active_laws_total=active_laws_total,
        deaths_count=deaths_count,
        confidence=confidence,
    )

    article = ArchiveArticle(
        slug=_resolve_unique_slug(db, base_slug),
        title=f"Weekly Systems Brief - {slug_anchor.isoformat()}",
        summary=summary,
        sections=sections_payload,
        status="draft",
        published_at=None,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(article)
    db.flush()
    return WeeklyDraftResult(article=article, created=True)


async def maybe_generate_scheduled_weekly_draft() -> dict[str, Any] | None:
    if not bool(getattr(settings, "ARCHIVE_WEEKLY_DRAFT_ENABLED", True)):
        return None

    now_value = now_utc()
    weekday = _bounded_int(
        getattr(settings, "ARCHIVE_WEEKLY_DRAFT_WEEKDAY_UTC", 0),
        fallback=0,
        minimum=0,
        maximum=6,
    )
    hour = _bounded_int(
        getattr(settings, "ARCHIVE_WEEKLY_DRAFT_HOUR_UTC", 15),
        fallback=15,
        minimum=0,
        maximum=23,
    )
    minute = _bounded_int(
        getattr(settings, "ARCHIVE_WEEKLY_DRAFT_MINUTE_UTC", 0),
        fallback=0,
        minimum=0,
        maximum=59,
    )
    grace_hours = _bounded_int(
        getattr(settings, "ARCHIVE_WEEKLY_DRAFT_GRACE_HOURS", 48),
        fallback=48,
        minimum=1,
        maximum=24 * 7,
    )
    lookback_days = _bounded_int(
        getattr(settings, "ARCHIVE_WEEKLY_DRAFT_LOOKBACK_DAYS", 7),
        fallback=7,
        minimum=1,
        maximum=30,
    )
    actor_id = str(getattr(settings, "ARCHIVE_WEEKLY_DRAFT_ACTOR", "archive-weekly-bot") or "archive-weekly-bot").strip()

    scheduled_anchor = _resolve_scheduled_anchor(now_value, weekday=weekday, hour=hour, minute=minute)
    if now_value < scheduled_anchor:
        return None
    if now_value - scheduled_anchor > timedelta(hours=grace_hours):
        return None

    db = SessionLocal()
    try:
        result = generate_weekly_draft(
            db,
            actor_id=actor_id,
            lookback_days=lookback_days,
            anchor_date=scheduled_anchor.date(),
            now_ts=now_value,
            skip_if_exists_for_anchor=True,
        )
        if result.created:
            db.commit()
            db.refresh(result.article)
            logger.info("Created scheduled weekly archive draft: %s", result.article.slug)
        else:
            db.rollback()
        return {
            "slug": result.article.slug,
            "created": bool(result.created),
        }
    except Exception:
        db.rollback()
        logger.exception("Failed to generate scheduled weekly archive draft")
        return None
    finally:
        db.close()
