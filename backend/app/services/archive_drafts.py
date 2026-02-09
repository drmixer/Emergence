"""Archive draft generation service."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import now_utc
from app.models.models import ArchiveArticle
from app.services.runtime_config import runtime_config_service
from app.services.weekly_digest import (
    WEEKLY_DIGEST_TEMPLATE_VERSION,
    WeeklyDigestInsufficientEvidenceError,
    build_weekly_digest,
)

logger = logging.getLogger(__name__)


@dataclass
class WeeklyDraftResult:
    article: ArchiveArticle | None
    created: bool
    status: str = "ok"
    message: str | None = None
    evidence_gate: dict[str, Any] | None = None
    digest_markdown: str | None = None
    digest_markdown_path: str | None = None
    digest_template_version: str | None = None


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
    effective = runtime_config_service.get_effective(db)
    preferred_run_id = str(effective.get("SIMULATION_RUN_ID") or "").strip() or None
    min_events = _bounded_int(
        getattr(settings, "ARCHIVE_WEEKLY_DRAFT_MIN_EVENTS", 1),
        fallback=1,
        minimum=0,
        maximum=100000,
    )
    min_llm_calls = _bounded_int(
        getattr(settings, "ARCHIVE_WEEKLY_DRAFT_MIN_LLM_CALLS", 1),
        fallback=1,
        minimum=0,
        maximum=100000,
    )

    if skip_if_exists_for_anchor:
        existing = (
            db.query(ArchiveArticle)
            .filter(ArchiveArticle.slug.like(f"{base_slug}%"), ArchiveArticle.status == "draft")
            .order_by(ArchiveArticle.updated_at.desc(), ArchiveArticle.id.desc())
            .first()
        )
        if existing:
            digest = build_weekly_digest(
                db,
                lookback_days=lookback,
                anchor_date=slug_anchor,
                now_ts=now_value,
                preferred_run_id=preferred_run_id,
                enforce_minimum_evidence=False,
                min_events=min_events,
                min_llm_calls=min_llm_calls,
            )
            return WeeklyDraftResult(
                article=existing,
                created=False,
                status="existing",
                message="Reused existing draft for this anchor date.",
                evidence_gate=digest.evidence_gate,
                digest_markdown=digest.markdown,
                digest_markdown_path=digest.markdown_path,
                digest_template_version=WEEKLY_DIGEST_TEMPLATE_VERSION,
            )

    try:
        digest = build_weekly_digest(
            db,
            lookback_days=lookback,
            anchor_date=slug_anchor,
            now_ts=now_value,
            preferred_run_id=preferred_run_id,
            enforce_minimum_evidence=True,
            min_events=min_events,
            min_llm_calls=min_llm_calls,
        )
    except WeeklyDigestInsufficientEvidenceError as exc:
        decision = exc.decision
        return WeeklyDraftResult(
            article=None,
            created=False,
            status="insufficient_evidence",
            message=str(decision.get("message") or "Weekly digest blocked by evidence gate"),
            evidence_gate=decision,
            digest_markdown=None,
            digest_markdown_path=None,
            digest_template_version=WEEKLY_DIGEST_TEMPLATE_VERSION,
        )

    article = ArchiveArticle(
        slug=_resolve_unique_slug(db, base_slug),
        title=f"State of Emergence Weekly Digest - {slug_anchor.isoformat()}",
        summary=digest.summary,
        sections=digest.sections,
        evidence_run_id=(digest.run_id if digest.run_id != "not-set" else None),
        status="draft",
        published_at=None,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(article)
    db.flush()
    return WeeklyDraftResult(
        article=article,
        created=True,
        status="created",
        message="Weekly digest draft created.",
        evidence_gate=digest.evidence_gate,
        digest_markdown=digest.markdown,
        digest_markdown_path=digest.markdown_path,
        digest_template_version=WEEKLY_DIGEST_TEMPLATE_VERSION,
    )


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
        if result.created and result.article is not None:
            db.commit()
            db.refresh(result.article)
            logger.info("Created scheduled weekly archive draft: %s", result.article.slug)
        else:
            db.rollback()
            if result.status == "insufficient_evidence":
                logger.info("Skipped scheduled weekly archive draft: %s", result.message)
        return {
            "slug": (result.article.slug if result.article is not None else None),
            "created": bool(result.created),
            "status": str(result.status or "ok"),
            "message": result.message,
            "evidence_gate": result.evidence_gate,
            "digest_markdown_path": result.digest_markdown_path,
            "digest_template_version": result.digest_template_version,
        }
    except Exception:
        db.rollback()
        logger.exception("Failed to generate scheduled weekly archive draft")
        return None
    finally:
        db.close()
