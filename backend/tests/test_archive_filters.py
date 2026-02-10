from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.api import admin_archive, archive


def test_public_archive_normalize_tag_filters_dedupes_and_normalizes():
    tags = archive._normalize_tag_filters(" RUN_ID:abc , topic:Governance, run_id:abc ")
    assert tags == ["run_id:abc", "topic:governance"]


def test_admin_archive_normalize_tag_filters_dedupes_and_normalizes():
    tags = admin_archive._normalize_tag_filters(" condition:Baseline_v1, condition:baseline_v1, topic:Conflict ")
    assert tags == ["condition:baseline_v1", "topic:conflict"]


def test_admin_archive_serialize_article_includes_content_metadata():
    now = datetime(2026, 2, 10, 14, 30, tzinfo=timezone.utc)
    article = SimpleNamespace(
        id=7,
        slug="run-demo-technical-report",
        title="Run Demo Technical Report",
        summary="Summary",
        sections=[{"heading": "One", "paragraphs": ["Two"], "references": []}],
        content_type="technical_report",
        status_label="replicated",
        evidence_completeness="full",
        tags=["run_id:run-demo", "topic:governance", "topic:governance"],
        linked_record_ids=[11, 11, 12, 0, -1, "x"],
        evidence_run_id="run-demo",
        status="draft",
        published_at=date(2026, 2, 10),
        created_by="tester",
        updated_by="tester",
        created_at=now,
        updated_at=now,
    )

    payload = admin_archive._serialize_article(article)

    assert payload["content_type"] == "technical_report"
    assert payload["status_label"] == "replicated"
    assert payload["evidence_completeness"] == "full"
    assert payload["tags"] == ["run_id:run-demo", "topic:governance"]
    assert payload["linked_record_ids"] == [11, 12]
    assert payload["evidence_run_id"] == "run-demo"
