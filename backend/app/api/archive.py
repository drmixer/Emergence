"""Public archive article API."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import ArchiveArticle

router = APIRouter()


def _normalize_references(raw_references: Any) -> list[dict[str, str]]:
    if not isinstance(raw_references, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in raw_references:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        href = str(item.get("href") or "").strip()
        if label and href:
            normalized.append({"label": label, "href": href})
    return normalized


def _normalize_sections(raw_sections: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_sections, list):
        return []
    sections: list[dict[str, Any]] = []
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "").strip()
        paragraphs_raw = section.get("paragraphs")
        if not heading or not isinstance(paragraphs_raw, list):
            continue
        paragraphs = [str(paragraph).strip() for paragraph in paragraphs_raw if str(paragraph).strip()]
        if not paragraphs:
            continue
        normalized: dict[str, Any] = {
            "heading": heading,
            "paragraphs": paragraphs,
        }
        references = _normalize_references(section.get("references"))
        if references:
            normalized["references"] = references
        sections.append(normalized)
    return sections


def _serialize_article(article: ArchiveArticle) -> dict[str, Any]:
    published_at = article.published_at if isinstance(article.published_at, date) else None
    return {
        "id": int(article.id),
        "slug": str(article.slug),
        "title": str(article.title),
        "summary": str(article.summary),
        "published_at": published_at.isoformat() if published_at else None,
        "status": str(article.status),
        "sections": _normalize_sections(article.sections),
        "created_at": article.created_at.isoformat() if article.created_at else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }


@router.get("/articles")
def list_archive_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    base_query = (
        db.query(ArchiveArticle)
        .filter(ArchiveArticle.status == "published")
        .order_by(ArchiveArticle.published_at.desc(), ArchiveArticle.created_at.desc(), ArchiveArticle.id.desc())
    )
    total = int(base_query.count())
    rows = base_query.offset(offset).limit(limit).all()
    return {
        "count": len(rows),
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
        "items": [_serialize_article(row) for row in rows],
    }


@router.get("/articles/{slug}")
def get_archive_article(
    slug: str,
    db: Session = Depends(get_db),
):
    article = (
        db.query(ArchiveArticle)
        .filter(ArchiveArticle.slug == str(slug).strip(), ArchiveArticle.status == "published")
        .first()
    )
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return _serialize_article(article)
