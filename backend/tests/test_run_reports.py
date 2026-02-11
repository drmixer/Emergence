from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services import run_reports


def _sample_snapshot() -> dict[str, object]:
    return {
        "run_id": "run-20260210T120000Z",
        "activity": {
            "total_events": 240,
            "proposal_actions": 12,
            "vote_actions": 41,
            "laws_passed": 3,
            "conflict_events": 9,
            "cooperation_events": 25,
        },
        "llm": {
            "calls": 510,
            "estimated_cost_usd": 0.47,
        },
        "key_moments": [
            {"event_id": 1001, "event_type": "create_proposal", "description": "A coalition agenda formed."},
            {"event_id": 1002, "event_type": "vote", "description": "A split vote passed."},
        ],
    }


def test_build_required_report_tags_includes_required_keys():
    tags = run_reports.build_required_report_tags(
        run_id="run-20260210T120000Z",
        condition_name="baseline_v1",
        season_number=2,
        status_label="observational",
        evidence_completeness="full",
        topic_tags=["governance", "economy"],
    )
    assert "run_id:run-20260210t120000z" in tags
    assert "season:2" in tags
    assert "condition:baseline-v1" in tags
    assert "topic:governance" in tags
    assert "topic:economy" in tags
    assert "status:observational" in tags
    assert "evidence:full" in tags


def test_story_sections_enforce_evidence_links_and_claim_gate():
    sections = run_reports._build_story_sections(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        condition_name="baseline_v1",
        replicate_count=2,
    )
    assert sections
    assert any(section.get("heading") == "Limitations and Claim Boundaries" for section in sections)
    claim_texts = [paragraph for section in sections for paragraph in (section.get("paragraphs") or [])]
    assert any("replicate threshold" in str(text) for text in claim_texts)
    for section in sections:
        claim_blocks = section.get("claim_blocks") or []
        assert claim_blocks
        for claim in claim_blocks:
            links = claim.get("evidence_links") or []
            assert links


def test_merge_generated_tags_preserves_custom_tags_only():
    merged = run_reports._merge_generated_tags(
        existing_tags=[
            "topic:conflict",
            "custom:ops",
            "status:observational",
            "run_id:old-run",
        ],
        generated_tags=[
            "run_id:new-run",
            "status:replicated",
            "evidence:full",
        ],
    )
    assert "custom:ops" in merged
    assert "run_id:new-run" in merged
    assert "status:replicated" in merged
    assert "run_id:old-run" not in merged
    assert "status:observational" not in merged


def test_maybe_generate_scheduled_run_report_backfill_runs_generation(monkeypatch):
    class FakeResult:
        def fetchall(self):
            return [SimpleNamespace(run_id="run-20260210T120000Z")]

    class FakeDB:
        def __init__(self):
            self.committed = False
            self.closed = False

        def execute(self, *_args, **_kwargs):
            return FakeResult()

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

        def close(self):
            self.closed = True

    fake_db = FakeDB()
    generated_runs: list[str] = []

    def _fake_rebuild_run_bundle(db, *, run_id, actor_id, condition_name=None, season_number=None):
        _ = db
        _ = actor_id
        _ = condition_name
        _ = season_number
        generated_runs.append(run_id)
        return None

    monkeypatch.setattr(run_reports.settings, "RUN_REPORT_BACKFILL_ENABLED", True, raising=False)
    monkeypatch.setattr(run_reports.settings, "RUN_REPORT_BACKFILL_LOOKBACK_HOURS", 24, raising=False)
    monkeypatch.setattr(run_reports.settings, "RUN_REPORT_BACKFILL_MAX_RUNS_PER_PASS", 1, raising=False)
    monkeypatch.setattr(run_reports.settings, "RUN_REPORT_BACKFILL_ACTOR", "report-backfill-bot", raising=False)
    monkeypatch.setattr(run_reports, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(run_reports, "_bundle_complete", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(run_reports, "rebuild_run_bundle", _fake_rebuild_run_bundle)
    monkeypatch.setattr(
        run_reports,
        "generate_and_record_run_summary",
        lambda *_args, **_kwargs: {"payload": {"condition_name": "baseline_v1"}, "artifacts": {}},
    )
    monkeypatch.setattr(
        run_reports,
        "generate_and_record_condition_comparison",
        lambda *_args, **_kwargs: {"payload": {"condition_name": "baseline_v1"}, "artifacts": {}},
    )
    monkeypatch.setattr(
        run_reports.runtime_config_service,
        "get_effective_value_cached",
        lambda key: {"SIMULATION_RUN_ID": "", "SIMULATION_ACTIVE": False, "SIMULATION_PAUSED": True}.get(key),
    )

    payload = asyncio.run(run_reports.maybe_generate_scheduled_run_report_backfill())

    assert payload is not None
    assert payload.get("generated") == ["run-20260210T120000Z"]
    assert generated_runs == ["run-20260210T120000Z"]
    assert fake_db.committed is True
    assert fake_db.closed is True
