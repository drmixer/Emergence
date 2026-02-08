"""Admin archive management API (token-protected)."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminActor, require_admin_auth
from app.core.config import settings
from app.core.database import get_db
from app.core.time import now_utc
from app.models.models import ArchiveArticle
from app.services.archive_drafts import generate_weekly_draft

router = APIRouter()


def _assert_writes_enabled() -> None:
    if not bool(getattr(settings, "ADMIN_WRITE_ENABLED", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin write controls are disabled in this environment",
        )


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
    status: Literal["draft", "published"] = "draft"
    published_at: date | None = None


class ArticlePublishRequest(BaseModel):
    published_at: date | None = None


class WeeklyDraftRequest(BaseModel):
    lookback_days: int = Field(default=7, ge=1, le=30)


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
    return {
        "id": int(article.id),
        "slug": str(article.slug),
        "title": str(article.title),
        "summary": str(article.summary),
        "sections": sections,
        "status": str(article.status),
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "created_by": article.created_by,
        "updated_by": article.updated_by,
        "created_at": article.created_at.isoformat() if article.created_at else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }


@router.get("/articles")
def list_admin_archive_articles(
    status_filter: Literal["draft", "published", "all"] = Query(default="all", alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _actor: AdminActor = Depends(require_admin_auth),
):
    query = db.query(ArchiveArticle)
    if status_filter != "all":
        query = query.filter(ArchiveArticle.status == status_filter)
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
    _assert_writes_enabled()
    existing = db.query(ArchiveArticle).filter(ArchiveArticle.slug == request.slug.strip()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")

    article = ArchiveArticle(
        slug=request.slug.strip(),
        title=request.title.strip(),
        summary=request.summary.strip(),
        sections=[_serialize_section(section) for section in request.sections],
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
    _assert_writes_enabled()
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
    article.status = request.status
    article.updated_by = actor.actor_id
    if request.status == "published":
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
    _assert_writes_enabled()
    article = db.query(ArchiveArticle).filter(ArchiveArticle.id == int(article_id)).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    article.status = "published"
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
    _assert_writes_enabled()
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
    _assert_writes_enabled()
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
    _assert_writes_enabled()
    now = now_utc()
    result = generate_weekly_draft(
        db,
        actor_id=actor.actor_id,
        lookback_days=int(request.lookback_days),
        anchor_date=now.date(),
        now_ts=now,
        skip_if_exists_for_anchor=True,
    )
    if result.created:
        db.commit()
        db.refresh(result.article)

    payload = _serialize_article(result.article)
    payload["generated"] = bool(result.created)
    return payload
