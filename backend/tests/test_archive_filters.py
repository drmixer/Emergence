from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

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


class _FakeExecuteResult:
    def __init__(self, *, row=None, scalar_value=None):
        self._row = row
        self._scalar_value = scalar_value

    def first(self):
        return self._row

    def scalar(self):
        return self._scalar_value


class _FakeGuardrailDB:
    def execute(self, statement, params=None):
        query = str(statement)
        if "FROM llm_usage" in query:
            row = SimpleNamespace(
                calls=24,
                success_calls=22,
                first_seen_at=datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
            )
            return _FakeExecuteResult(row=row)
        if "SELECT COUNT(*) FROM events" in query:
            return _FakeExecuteResult(scalar_value=14)
        raise AssertionError(f"Unexpected query: {query} params={params}")


def test_admin_archive_publish_guardrail_blocks_replicated_without_threshold(monkeypatch):
    db = _FakeGuardrailDB()
    monkeypatch.setattr(
        admin_archive,
        "evaluate_run_claim_readiness",
        lambda *_args, **_kwargs: {
            "gate_reason": "replicate_threshold_not_met",
            "replicate_count": 2,
            "meets_replicate_threshold": False,
        },
    )

    with pytest.raises(Exception) as exc_info:
        admin_archive._assert_publish_guardrails(
            db,
            article_slug="run-article",
            evidence_run_id="run-threshold-2",
            status_label="replicated",
        )

    assert getattr(exc_info.value, "status_code", None) == 422
    assert "replicated status requires >= 3" in str(getattr(exc_info.value, "detail", ""))


def test_admin_archive_publish_guardrail_blocks_replicated_for_exploratory(monkeypatch):
    db = _FakeGuardrailDB()
    monkeypatch.setattr(
        admin_archive,
        "evaluate_run_claim_readiness",
        lambda *_args, **_kwargs: {
            "gate_reason": "exploratory_run_class",
            "replicate_count": 5,
            "meets_replicate_threshold": True,
        },
    )

    with pytest.raises(Exception) as exc_info:
        admin_archive._assert_publish_guardrails(
            db,
            article_slug="run-article",
            evidence_run_id="run-exploratory",
            status_label="replicated",
        )

    assert getattr(exc_info.value, "status_code", None) == 422
    assert "special_exploratory" in str(getattr(exc_info.value, "detail", ""))
