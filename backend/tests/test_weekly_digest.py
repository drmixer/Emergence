from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import app.services.archive_drafts as archive_drafts
from app.services.archive_drafts import WeeklyDraftResult
from app.services import weekly_digest


def _sample_snapshot() -> dict[str, object]:
    return {
        "llm_calls": 420,
        "llm_success_calls": 401,
        "llm_fallback_calls": 19,
        "llm_total_tokens": 120_000,
        "llm_cost_usd": 1.23,
        "active_agents": 34,
        "total_events": 1_840,
        "checkpoint_actions": 1_520,
        "deterministic_actions": 120,
        "proposal_actions": 62,
        "vote_actions": 214,
        "forum_actions": 530,
        "laws_passed": 12,
        "deaths": 9,
        "verification_state": "verified",
        "traces": [
            {"event_id": 9001, "event_type": "create_proposal", "description": "Coalition proposal", "created_at": None},
            {"event_id": 9002, "event_type": "forum_post", "description": "Public post", "created_at": None},
            {"event_id": 9003, "event_type": "agent_died", "description": "Agent death", "created_at": None},
        ],
    }


def test_locked_digest_sections_include_evidence_per_claim():
    start = datetime(2026, 2, 2, 15, 0, tzinfo=timezone.utc)
    end = datetime(2026, 2, 9, 15, 0, tzinfo=timezone.utc)
    run_id = "run-20260209T150000Z"

    sections = weekly_digest._build_locked_sections(
        run_id=run_id,
        verification_state="verified",
        window_start=start,
        window_end=end,
        snapshot=_sample_snapshot(),
        hours_fallback=7 * 24,
    )

    assert tuple(section["heading"] for section in sections) == weekly_digest.LOCKED_WEEKLY_DIGEST_HEADINGS

    for section in sections:
        claim_blocks = section.get("claim_blocks") or []
        assert claim_blocks
        for block in claim_blocks:
            links = block.get("evidence_links") or []
            assert links
            assert any(run_id in str(link.get("href") or "") for link in links)


def test_render_markdown_outputs_claim_and_evidence_lines():
    start = datetime(2026, 2, 2, 15, 0, tzinfo=timezone.utc)
    end = datetime(2026, 2, 9, 15, 0, tzinfo=timezone.utc)
    run_id = "run-20260209T150000Z"
    sections = weekly_digest._build_locked_sections(
        run_id=run_id,
        verification_state="verified",
        window_start=start,
        window_end=end,
        snapshot=_sample_snapshot(),
        hours_fallback=7 * 24,
    )

    markdown = weekly_digest.render_weekly_digest_markdown(
        anchor_date=end.date(),
        run_id=run_id,
        verification_state="verified",
        summary="Sample summary.",
        sections=sections,
        generated_at=end,
    )

    assert "# State of Emergence Weekly Digest - 2026-02-09" in markdown
    for heading in weekly_digest.LOCKED_WEEKLY_DIGEST_HEADINGS:
        assert f"## {heading}" in markdown
    assert "- Claim:" in markdown
    assert "Evidence:" in markdown
    assert "Run Evidence API" in markdown


def test_evidence_gate_reports_insufficient_evidence():
    decision = weekly_digest.evaluate_weekly_digest_evidence(
        snapshot={"total_events": 0, "llm_calls": 1},
        min_events=5,
        min_llm_calls=3,
    )
    assert decision["status"] == "insufficient_evidence"
    assert decision["passed"] is False
    assert decision["observed"]["total_events"] == 0
    assert decision["requirements"]["min_events"] == 5


def test_maybe_generate_scheduled_weekly_draft_returns_digest_metadata(monkeypatch):
    fixed_now = datetime(2026, 2, 9, 15, 5, tzinfo=timezone.utc)

    class FakeDB:
        def __init__(self):
            self.committed = False
            self.rolled_back = False
            self.closed = False
            self.refreshed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def refresh(self, _article):
            self.refreshed = True

        def close(self):
            self.closed = True

    fake_db = FakeDB()

    def _fake_generate_weekly_draft(*_args, **_kwargs):
        article = SimpleNamespace(slug="weekly-brief-2026-02-09")
        return WeeklyDraftResult(
            article=article,
            created=True,
            digest_markdown="digest",
            digest_markdown_path="/tmp/state_of_emergence_2026-02-09.md",
            digest_template_version=weekly_digest.WEEKLY_DIGEST_TEMPLATE_VERSION,
        )

    monkeypatch.setattr(archive_drafts, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(archive_drafts, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(archive_drafts, "generate_weekly_draft", _fake_generate_weekly_draft)

    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_ENABLED", True, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_WEEKDAY_UTC", 0, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_HOUR_UTC", 15, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_MINUTE_UTC", 0, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_GRACE_HOURS", 48, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_LOOKBACK_DAYS", 7, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_ACTOR", "archive-weekly-bot", raising=False)

    result = asyncio.run(archive_drafts.maybe_generate_scheduled_weekly_draft())

    assert result is not None
    assert result["slug"] == "weekly-brief-2026-02-09"
    assert result["created"] is True
    assert result["digest_markdown_path"] == "/tmp/state_of_emergence_2026-02-09.md"
    assert result["digest_template_version"] == weekly_digest.WEEKLY_DIGEST_TEMPLATE_VERSION

    assert fake_db.committed is True
    assert fake_db.refreshed is True
    assert fake_db.closed is True


def test_maybe_generate_scheduled_weekly_draft_returns_insufficient_status(monkeypatch):
    fixed_now = datetime(2026, 2, 9, 15, 5, tzinfo=timezone.utc)

    class FakeDB:
        def __init__(self):
            self.committed = False
            self.rolled_back = False
            self.closed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def refresh(self, _article):
            raise AssertionError("refresh should not be called without article")

        def close(self):
            self.closed = True

    fake_db = FakeDB()

    def _fake_generate_weekly_draft(*_args, **_kwargs):
        return WeeklyDraftResult(
            article=None,
            created=False,
            status="insufficient_evidence",
            message="Evidence gate failed: events 0/1, llm_calls 0/1.",
            evidence_gate={
                "status": "insufficient_evidence",
                "passed": False,
                "requirements": {"min_events": 1, "min_llm_calls": 1},
                "observed": {"total_events": 0, "llm_calls": 0},
            },
            digest_markdown_path=None,
            digest_template_version=weekly_digest.WEEKLY_DIGEST_TEMPLATE_VERSION,
        )

    monkeypatch.setattr(archive_drafts, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(archive_drafts, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(archive_drafts, "generate_weekly_draft", _fake_generate_weekly_draft)

    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_ENABLED", True, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_WEEKDAY_UTC", 0, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_HOUR_UTC", 15, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_MINUTE_UTC", 0, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_GRACE_HOURS", 48, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_LOOKBACK_DAYS", 7, raising=False)
    monkeypatch.setattr(archive_drafts.settings, "ARCHIVE_WEEKLY_DRAFT_ACTOR", "archive-weekly-bot", raising=False)

    result = asyncio.run(archive_drafts.maybe_generate_scheduled_weekly_draft())

    assert result is not None
    assert result["created"] is False
    assert result["slug"] is None
    assert result["status"] == "insufficient_evidence"
    assert "events 0/1" in str(result["message"])
    assert fake_db.committed is False
    assert fake_db.rolled_back is True
    assert fake_db.closed is True
