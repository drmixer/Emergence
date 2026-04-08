"""Durable operator-review queue for social post drafts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.time import now_utc
from app.models.models import SocialPostDraft
from app.services.runtime_config import runtime_config_service

PENDING_REVIEW = "pending_review"
POSTED = "posted"
DISMISSED = "dismissed"
ALL_STATUSES = {PENDING_REVIEW, POSTED, DISMISSED}


@dataclass(frozen=True)
class DraftCreateResult:
    draft: SocialPostDraft
    created: bool


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_status(value: str | None) -> str:
    normalized = str(value or PENDING_REVIEW).strip().lower()
    return normalized if normalized in ALL_STATUSES else PENDING_REVIEW


def _runtime_value(key: str, *, max_length: int | None = None) -> str | None:
    value = str(runtime_config_service.get_effective_value_cached(key) or "").strip()
    if not value:
        return None
    if max_length is not None:
        return value[:max_length]
    return value


def _build_dedupe_key(*, platform: str, draft_type: str, full_text: str, url: str | None) -> str:
    payload = "|".join(
        [
            str(platform or "").strip().lower(),
            str(draft_type or "").strip().lower(),
            _normalize_text(full_text),
            str(url or "").strip(),
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def serialize_social_draft(draft: SocialPostDraft) -> dict[str, Any]:
    return {
        "id": int(draft.id),
        "platform": str(draft.platform or "x"),
        "draft_type": str(draft.draft_type or ""),
        "status": str(draft.status or PENDING_REVIEW),
        "text": str(draft.text or ""),
        "full_text": str(draft.full_text or ""),
        "url": str(draft.url or "").strip() or None,
        "image_path": str(draft.image_path or "").strip() or None,
        "priority": int(draft.priority or 5),
        "run_id": str(draft.run_id or "").strip() or None,
        "run_mode": str(draft.run_mode or "").strip() or None,
        "source_service": str(draft.source_service or "").strip() or None,
        "source_event_type": str(draft.source_event_type or "").strip() or None,
        "source_record_id": int(draft.source_record_id) if draft.source_record_id is not None else None,
        "dedupe_key": str(draft.dedupe_key or "").strip() or None,
        "metadata": draft.metadata_json if isinstance(draft.metadata_json, dict) else {},
        "error_message": str(draft.error_message or "").strip() or None,
        "review_note": str(draft.review_note or "").strip() or None,
        "posted_url": str(draft.posted_url or "").strip() or None,
        "external_post_id": str(draft.external_post_id or "").strip() or None,
        "reviewed_by": str(draft.reviewed_by or "").strip() or None,
        "reviewed_at": draft.reviewed_at.isoformat() if draft.reviewed_at else None,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


def create_social_draft(
    *,
    platform: str = "x",
    draft_type: str,
    text: str,
    full_text: str,
    url: str | None = None,
    image_path: str | None = None,
    priority: int = 5,
    source_service: str | None = None,
    source_event_type: str | None = None,
    source_record_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        result = _create_or_refresh_social_draft(
            db,
            platform=platform,
            draft_type=draft_type,
            text=text,
            full_text=full_text,
            url=url,
            image_path=image_path,
            priority=priority,
            source_service=source_service,
            source_event_type=source_event_type,
            source_record_id=source_record_id,
            metadata=metadata,
            error_message=error_message,
        )
        db.commit()
        db.refresh(result.draft)
        payload = serialize_social_draft(result.draft)
        payload["created"] = result.created
        return payload
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _create_or_refresh_social_draft(
    db: Session,
    *,
    platform: str,
    draft_type: str,
    text: str,
    full_text: str,
    url: str | None,
    image_path: str | None,
    priority: int,
    source_service: str | None,
    source_event_type: str | None,
    source_record_id: int | None,
    metadata: dict[str, Any] | None,
    error_message: str | None,
) -> DraftCreateResult:
    normalized_full_text = str(full_text or "").strip()
    normalized_text = str(text or "").strip() or normalized_full_text
    normalized_url = str(url or "").strip() or None
    dedupe_key = _build_dedupe_key(
        platform=platform,
        draft_type=draft_type,
        full_text=normalized_full_text,
        url=normalized_url,
    )
    existing = (
        db.query(SocialPostDraft)
        .filter(
            SocialPostDraft.platform == str(platform or "x").strip().lower(),
            SocialPostDraft.dedupe_key == dedupe_key,
            SocialPostDraft.status == PENDING_REVIEW,
        )
        .order_by(SocialPostDraft.id.desc())
        .first()
    )
    if existing is not None:
        if error_message:
            existing.error_message = str(error_message).strip()[:2000]
        if metadata:
            merged_metadata = dict(existing.metadata_json or {})
            merged_metadata.update(metadata)
            existing.metadata_json = merged_metadata
        existing.updated_at = now_utc()
        return DraftCreateResult(draft=existing, created=False)

    draft = SocialPostDraft(
        platform=str(platform or "x").strip().lower() or "x",
        draft_type=str(draft_type or "unknown").strip()[:32] or "unknown",
        status=PENDING_REVIEW,
        text=normalized_text,
        full_text=normalized_full_text,
        url=normalized_url,
        image_path=str(image_path or "").strip() or None,
        priority=max(1, min(10, int(priority or 5))),
        run_id=_runtime_value("SIMULATION_RUN_ID", max_length=64),
        run_mode=_runtime_value("SIMULATION_RUN_MODE", max_length=16),
        source_service=str(source_service or "").strip()[:64] or None,
        source_event_type=str(source_event_type or "").strip()[:64] or None,
        source_record_id=int(source_record_id) if source_record_id is not None else None,
        dedupe_key=dedupe_key,
        metadata_json=dict(metadata or {}),
        error_message=str(error_message or "").strip()[:2000] or None,
    )
    db.add(draft)
    db.flush()
    return DraftCreateResult(draft=draft, created=True)


def count_social_drafts(db: Session, *, platform: str = "x", status_filter: str = PENDING_REVIEW) -> int:
    query = db.query(SocialPostDraft).filter(SocialPostDraft.platform == str(platform or "x").strip().lower())
    normalized_status = _normalize_status(status_filter)
    if normalized_status in ALL_STATUSES:
        query = query.filter(SocialPostDraft.status == normalized_status)
    return int(query.count())


def list_social_drafts(
    db: Session,
    *,
    platform: str = "x",
    status_filter: str = "all",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    query = db.query(SocialPostDraft).filter(SocialPostDraft.platform == str(platform or "x").strip().lower())
    normalized_status = str(status_filter or "all").strip().lower()
    if normalized_status in ALL_STATUSES:
        query = query.filter(SocialPostDraft.status == normalized_status)
    query = query.order_by(SocialPostDraft.created_at.desc(), SocialPostDraft.id.desc())
    total = int(query.count())
    rows = query.offset(max(0, int(offset))).limit(max(1, int(limit))).all()
    return {
        "count": len(rows),
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
        "items": [serialize_social_draft(row) for row in rows],
    }


def update_social_draft(
    db: Session,
    *,
    draft_id: int,
    status: str,
    reviewed_by: str | None = None,
    review_note: str | None = None,
    posted_url: str | None = None,
    external_post_id: str | None = None,
) -> SocialPostDraft | None:
    draft = db.query(SocialPostDraft).filter(SocialPostDraft.id == int(draft_id)).first()
    if draft is None:
        return None
    draft.status = _normalize_status(status)
    draft.reviewed_by = str(reviewed_by or "").strip()[:120] or None
    draft.review_note = str(review_note or "").strip()[:4000] or None
    draft.posted_url = str(posted_url or "").strip()[:500] or None
    draft.external_post_id = str(external_post_id or "").strip()[:128] or None
    draft.reviewed_at = now_utc()
    return draft


def list_draft_texts_for_dedupe(
    db: Session,
    *,
    platform: str = "x",
    draft_type: str,
    statuses: Iterable[str] = (PENDING_REVIEW, POSTED),
) -> list[str]:
    normalized_statuses = [status for status in (_normalize_status(value) for value in statuses) if status in ALL_STATUSES]
    if not normalized_statuses:
        return []
    rows = (
        db.query(SocialPostDraft.text, SocialPostDraft.full_text)
        .filter(
            SocialPostDraft.platform == str(platform or "x").strip().lower(),
            SocialPostDraft.draft_type == str(draft_type or "").strip()[:32],
            SocialPostDraft.status.in_(normalized_statuses),
        )
        .all()
    )
    dedupe_texts: list[str] = []
    for text_value, full_text_value in rows:
        for value in (text_value, full_text_value):
            normalized = str(value or "").strip()
            if normalized:
                dedupe_texts.append(normalized)
    return dedupe_texts
