"""Admin archive management API (token-protected)."""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, text
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminActor, assert_admin_write_access, require_admin_auth
from app.core.database import get_db
from app.core.time import now_utc
from app.models.models import ArchiveArticle
from app.services.archive_drafts import generate_weekly_draft
from app.services.condition_reports import evaluate_run_claim_readiness
from app.services.run_reports import generate_run_bundle_for_run_id, normalize_report_tags

router = APIRouter()
BASELINE_ARTICLE_SLUG = "before-the-first-full-run"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9:_-]{1,64}$")
CONTENT_TYPES = ("technical_report", "approachable_article")
STATUS_LABELS = ("observational", "replicated")
EVIDENCE_COMPLETENESS = ("full", "partial")


def _assert_writes_enabled(actor: AdminActor) -> None:
    assert_admin_write_access(client_ip=actor.client_ip)


class ArticleReferencePayload(BaseModel):
    label: str = Field(..., min_length=1, max_length=240)
    href: str = Field(..., min_length=1, max_length=500)


class ArticleSectionPayload(BaseModel):
    heading: str = Field(..., min_length=1, max_length=240)
    paragraphs: list[str] = Field(..., min_length=1)
    references: list[ArticleReferencePayload] = Field(default_factory=list)


class ArticleUpsertRequest(BaseModel):
    slug: str = Field(..., min_length=3, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(..., min_length=3, max_length=255)
    summary: str = Field(..., min_length=20, max_length=800)
    sections: list[ArticleSectionPayload] = Field(..., min_length=1)
    evidence_run_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9:_-]+$")
    content_type: Literal["technical_report", "approachable_article"] | None = None
    status_label: Literal["observational", "replicated"] | None = None
    evidence_completeness: Literal["full", "partial"] | None = None
    tags: list[str] | None = None
    linked_record_ids: list[int] | None = None
    status: Literal["draft", "published"] = "draft"
    published_at: date | None = None


class ArticlePublishRequest(BaseModel):
    published_at: date | None = None
    evidence_run_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9:_-]+$")


class WeeklyDraftRequest(BaseModel):
    lookback_days: int = Field(default=7, ge=1, le=30)


class RunBundleRebuildRequest(BaseModel):
    run_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_-]+$")
    condition_name: str | None = Field(default=None, max_length=120, pattern=r"^[A-Za-z0-9:_-]+$")
    season_number: int | None = Field(default=None, ge=1, le=9999)
    actor_id: str | None = Field(default=None, max_length=120)


def _serialize_section(section: ArticleSectionPayload) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "heading": section.heading.strip(),
        "paragraphs": [paragraph.strip() for paragraph in section.paragraphs if paragraph.strip()],
    }
    references = [
        {"label": ref.label.strip(), "href": ref.href.strip()}
        for ref in section.references
        if ref.label.strip() and ref.href.strip()
    ]
    if references:
        payload["references"] = references
    return payload


def _serialize_article(article: ArchiveArticle) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    raw_sections = article.sections if isinstance(article.sections, list) else []
    for section in raw_sections:
        if isinstance(section, dict):
            sections.append(section)
    tags = normalize_report_tags(article.tags if isinstance(article.tags, list) else [])
    linked_record_ids = _normalize_linked_record_ids(article.linked_record_ids)
    return {
        "id": int(article.id),
        "slug": str(article.slug),
        "title": str(article.title),
        "summary": str(article.summary),
        "sections": sections,
        "content_type": str(article.content_type or "approachable_article"),
        "status_label": str(article.status_label or "observational"),
        "evidence_completeness": str(article.evidence_completeness or "partial"),
        "tags": tags,
        "linked_record_ids": linked_record_ids,
        "evidence_run_id": str(article.evidence_run_id or "").strip() or None,
        "status": str(article.status),
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "created_by": article.created_by,
        "updated_by": article.updated_by,
        "created_at": article.created_at.isoformat() if article.created_at else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }


def _normalize_run_id(raw_value: str | None) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    if not RUN_ID_PATTERN.match(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="evidence_run_id must match [A-Za-z0-9:_-] and be at most 64 characters",
        )
    return value


def _normalize_content_type(raw_value: str | None) -> str:
    value = str(raw_value or "approachable_article").strip().lower()
    return value if value in CONTENT_TYPES else "approachable_article"


def _normalize_status_label(raw_value: str | None) -> str:
    value = str(raw_value or "observational").strip().lower()
    return value if value in STATUS_LABELS else "observational"


def _normalize_evidence_completeness(raw_value: str | None) -> str:
    value = str(raw_value or "partial").strip().lower()
    return value if value in EVIDENCE_COMPLETENESS else "partial"


def _normalize_linked_record_ids(raw_value: Any) -> list[int]:
    if not isinstance(raw_value, list):
        return []
    deduped: list[int] = []
    seen: set[int] = set()
    for item in raw_value:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_tag_filters(raw_value: str | None) -> list[str]:
    parts = [part.strip() for part in str(raw_value or "").split(",")]
    return normalize_report_tags([part for part in parts if part])


def _assert_publish_guardrails(
    db: Session,
    *,
    article_slug: str,
    evidence_run_id: str | None,
    status_label: str | None = None,
) -> str | None:
    normalized_run_id = _normalize_run_id(evidence_run_id)
    normalized_status_label = _normalize_status_label(status_label)
    if article_slug == BASELINE_ARTICLE_SLUG:
        # Baseline methodology post is allowed without run-backed telemetry.
        return normalized_run_id

    if not normalized_run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Publishing requires evidence_run_id for non-baseline articles",
        )

    telemetry = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS calls,
              COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
              MIN(created_at) AS first_seen_at
            FROM llm_usage
            WHERE run_id = :run_id
            """
        ),
        {"run_id": normalized_run_id},
    ).first()
    calls = int((telemetry.calls if telemetry else 0) or 0)
    success_calls = int((telemetry.success_calls if telemetry else 0) or 0)
    first_seen_at = telemetry.first_seen_at if telemetry else None

    if calls <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Run ID '{normalized_run_id}' has no telemetry rows in llm_usage",
        )
    if success_calls <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Run ID '{normalized_run_id}' has no successful telemetry calls",
        )

    if first_seen_at is not None:
        event_count = int(
            db.execute(
                text("SELECT COUNT(*) FROM events WHERE created_at >= :start_ts"),
                {"start_ts": first_seen_at},
            ).scalar()
            or 0
        )
        if event_count <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Run ID '{normalized_run_id}' has no event activity after telemetry start",
            )

    if normalized_status_label == "replicated":
        try:
            readiness = evaluate_run_claim_readiness(db, run_id=normalized_run_id, min_replicates=3)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        gate_reason = str(readiness.get("gate_reason") or "").strip() or "replicate_threshold_not_met"
        if gate_reason == "exploratory_run_class":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Run ID '{normalized_run_id}' is special_exploratory; "
                    "replicated status is blocked for exploratory runs"
                ),
            )
        if not bool(readiness.get("meets_replicate_threshold")):
            replicate_count = int(readiness.get("replicate_count") or 1)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Run ID '{normalized_run_id}' has only {replicate_count} comparable replicate(s); "
                    "replicated status requires >= 3 with run_class/duration consistency"
                ),
            )

    return normalized_run_id


@router.get("/articles")
def list_admin_archive_articles(
    status_filter: Literal["draft", "published", "all"] = Query(default="all", alias="status"),
    content_type_filter: Literal["technical_report", "approachable_article", "all"] = Query(
        default="all", alias="content_type"
    ),
    tag_filter: str | None = Query(default=None, alias="tag"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _actor: AdminActor = Depends(require_admin_auth),
):
    query = db.query(ArchiveArticle)
    if status_filter != "all":
        query = query.filter(ArchiveArticle.status == status_filter)
    if content_type_filter != "all":
        query = query.filter(ArchiveArticle.content_type == content_type_filter)
    for tag in _normalize_tag_filters(tag_filter):
        query = query.filter(cast(ArchiveArticle.tags, String).like(f'%"{tag}"%'))
    query = query.order_by(ArchiveArticle.published_at.desc(), ArchiveArticle.updated_at.desc(), ArchiveArticle.id.desc())
    total = int(query.count())
    rows = query.offset(offset).limit(limit).all()
    return {
        "count": len(rows),
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
        "items": [_serialize_article(row) for row in rows],
    }


@router.post("/articles")
def create_admin_archive_article(
    request: ArticleUpsertRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled(actor)
    existing = db.query(ArchiveArticle).filter(ArchiveArticle.slug == request.slug.strip()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    evidence_run_id = _normalize_run_id(request.evidence_run_id)
    if request.status == "published":
        evidence_run_id = _assert_publish_guardrails(
            db,
            article_slug=request.slug.strip(),
            evidence_run_id=evidence_run_id,
            status_label=request.status_label,
        )

    article = ArchiveArticle(
        slug=request.slug.strip(),
        title=request.title.strip(),
        summary=request.summary.strip(),
        sections=[_serialize_section(section) for section in request.sections],
        content_type=_normalize_content_type(request.content_type),
        status_label=_normalize_status_label(request.status_label),
        evidence_completeness=_normalize_evidence_completeness(request.evidence_completeness),
        tags=normalize_report_tags(request.tags or []),
        linked_record_ids=_normalize_linked_record_ids(request.linked_record_ids or []),
        evidence_run_id=evidence_run_id,
        status=request.status,
        published_at=request.published_at
        if request.published_at
        else (date.today() if request.status == "published" else None),
        created_by=actor.actor_id,
        updated_by=actor.actor_id,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return _serialize_article(article)


@router.patch("/articles/{article_id}")
def update_admin_archive_article(
    article_id: int,
    request: ArticleUpsertRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled(actor)
    article = db.query(ArchiveArticle).filter(ArchiveArticle.id == int(article_id)).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    slug = request.slug.strip()
    slug_owner = db.query(ArchiveArticle).filter(ArchiveArticle.slug == slug, ArchiveArticle.id != article.id).first()
    if slug_owner:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")

    article.slug = slug
    article.title = request.title.strip()
    article.summary = request.summary.strip()
    article.sections = [_serialize_section(section) for section in request.sections]
    article.content_type = _normalize_content_type(request.content_type or article.content_type)
    article.status_label = _normalize_status_label(request.status_label or article.status_label)
    article.evidence_completeness = _normalize_evidence_completeness(
        request.evidence_completeness or article.evidence_completeness
    )
    article.tags = normalize_report_tags(request.tags if request.tags is not None else (article.tags or []))
    article.linked_record_ids = _normalize_linked_record_ids(
        request.linked_record_ids if request.linked_record_ids is not None else (article.linked_record_ids or [])
    )
    article.evidence_run_id = _normalize_run_id(request.evidence_run_id)
    article.status = request.status
    article.updated_by = actor.actor_id
    if request.status == "published":
        article.evidence_run_id = _assert_publish_guardrails(
            db,
            article_slug=slug,
            evidence_run_id=article.evidence_run_id,
            status_label=article.status_label,
        )
        article.published_at = request.published_at or article.published_at or date.today()
    else:
        article.published_at = request.published_at

    db.commit()
    db.refresh(article)
    return _serialize_article(article)


@router.post("/articles/{article_id}/publish")
def publish_admin_archive_article(
    article_id: int,
    request: ArticlePublishRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled(actor)
    article = db.query(ArchiveArticle).filter(ArchiveArticle.id == int(article_id)).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    resolved_evidence_run_id = _assert_publish_guardrails(
        db,
        article_slug=str(article.slug),
        evidence_run_id=request.evidence_run_id or article.evidence_run_id,
        status_label=article.status_label,
    )
    article.status = "published"
    article.evidence_run_id = resolved_evidence_run_id
    article.published_at = request.published_at or article.published_at or date.today()
    article.updated_by = actor.actor_id
    db.commit()
    db.refresh(article)
    return _serialize_article(article)


@router.post("/articles/{article_id}/unpublish")
def unpublish_admin_archive_article(
    article_id: int,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled(actor)
    article = db.query(ArchiveArticle).filter(ArchiveArticle.id == int(article_id)).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    article.status = "draft"
    article.updated_by = actor.actor_id
    db.commit()
    db.refresh(article)
    return _serialize_article(article)


@router.delete("/articles/{article_id}")
def delete_admin_archive_article(
    article_id: int,
    db: Session = Depends(get_db),
    _actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled(actor)
    article = db.query(ArchiveArticle).filter(ArchiveArticle.id == int(article_id)).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    db.delete(article)
    db.commit()
    return {"ok": True}


@router.post("/drafts/weekly")
def generate_weekly_archive_draft(
    request: WeeklyDraftRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled(actor)
    now = now_utc()
    result = generate_weekly_draft(
        db,
        actor_id=actor.actor_id,
        lookback_days=int(request.lookback_days),
        anchor_date=now.date(),
        now_ts=now,
        skip_if_exists_for_anchor=True,
    )
    if result.created and result.article is not None:
        db.commit()
        db.refresh(result.article)
    else:
        db.rollback()

    payload = _serialize_article(result.article) if result.article is not None else {}
    payload["generated"] = bool(result.created)
    payload["status"] = str(result.status or "ok")
    payload["message"] = result.message
    payload["evidence_gate"] = result.evidence_gate
    payload["digest_markdown"] = result.digest_markdown
    payload["digest_markdown_path"] = result.digest_markdown_path
    payload["digest_template_version"] = result.digest_template_version
    return payload


@router.post("/reports/rebuild")
def rebuild_run_report_bundle(
    request: RunBundleRebuildRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled(actor)
    # Ensure request-side validation happens in this request's DB transaction context first.
    _ = db
    resolved_actor_id = str(request.actor_id or "").strip() or f"admin:{actor.actor_id}"
    try:
        result = generate_run_bundle_for_run_id(
            run_id=str(request.run_id or "").strip(),
            actor_id=resolved_actor_id,
            condition_name=(str(request.condition_name or "").strip() or None),
            season_number=request.season_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    result["status"] = "generated"
    return result
