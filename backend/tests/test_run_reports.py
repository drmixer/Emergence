from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import AdminConfigChange, Agent, AgentInventory, Event, SimulationRun
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
    assert "condition:baseline_v1" in tags
    assert "run_class:unknown" in tags
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


def test_resolve_status_label_blocks_replicated_for_exploratory_run_class():
    status_label = run_reports._resolve_status_label(
        condition_name="baseline_v1",
        replicate_count=9,
        run_class="special_exploratory",
    )
    assert status_label == run_reports.STATUS_OBSERVATIONAL


def test_story_payload_and_markdown_include_exploratory_claim_boundary():
    snapshot = _sample_snapshot()
    snapshot["run_class"] = "special_exploratory"

    payload = run_reports._build_story_payload(
        snapshot=snapshot,
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="baseline_v1",
        season_number=2,
        replicate_count=1,
    )
    markdown = run_reports._story_markdown(payload)

    assert payload["run_class"] == "special_exploratory"
    assert payload["exploratory_label"] == "exploratory"
    assert "Tournament claim boundary" in markdown


def _build_snapshot_session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SimulationRun.__table__.create(bind=engine)
    Agent.__table__.create(bind=engine)
    AgentInventory.__table__.create(bind=engine)
    Event.__table__.create(bind=engine)
    AdminConfigChange.__table__.create(bind=engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NULL,
                    agent_id INTEGER NULL,
                    success BOOLEAN NOT NULL DEFAULT 1,
                    fallback_used BOOLEAN NOT NULL DEFAULT 0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    provider TEXT NULL,
                    model_name TEXT NULL,
                    resolved_model_name TEXT NULL,
                    created_at TIMESTAMP NULL
                )
                """
            )
        )

    return sessionmaker(bind=engine, future=True)()


def test_collect_run_snapshot_uses_runtime_tagged_events_when_llm_usage_is_absent():
    db_session = _build_snapshot_session()
    try:
        started_at = datetime(2026, 4, 7, 21, 0, tzinfo=timezone.utc)
        agent = Agent(
            agent_number=7,
            display_name="Tagged Agent",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        db_session.add(agent)
        db_session.flush()
        db_session.add(
            SimulationRun(
                run_id="run-event-only",
                run_mode="test",
                protocol_version="protocol_v1",
                condition_name="behavior_eval_control_v1",
                run_class="standard_72h",
                started_at=started_at,
            )
        )
        db_session.add(
            Event(
                agent_id=agent.id,
                event_type="reserve_aid",
                description="shared reserve kept the run traceable",
                event_metadata={"runtime": {"run_id": "run-event-only", "run_mode": "test"}},
                created_at=started_at + run_reports.timedelta(minutes=2),
            )
        )
        db_session.commit()

        snapshot = run_reports._collect_run_snapshot(db_session, run_id="run-event-only")

        assert snapshot["verification_source"] == "event_metadata_runtime_run_id"
        assert snapshot["verification_state"] == "partial"
        assert snapshot["activity"]["total_events"] == 1
        assert snapshot["key_moments"][0]["event_type"] == "reserve_aid"
    finally:
        db_session.close()
