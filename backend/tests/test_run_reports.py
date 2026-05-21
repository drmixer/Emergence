from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import AdminConfigChange, Agent, AgentInventory, Event, Law, Message, Proposal, SimulationRun
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
        "reserve_semantics": {
            "status": "policy_only",
            "policy_intent": {
                "reserve_law_active": True,
                "reserve_law_count": 1,
                "active_law_ids": [77],
                "label": "Active reserve policy intent",
            },
            "mechanical_access": {
                "auto_contribution_enabled": False,
                "active_aid_enabled": False,
                "dormant_maintenance_enabled": False,
                "auto_revive_enabled": False,
                "enabled_modes": [],
                "disabled_modes": ["auto_contribution", "active_aid", "dormant_maintenance", "auto_revive"],
                "mode_labels": {
                    "auto_contribution": "Auto contribution",
                    "active_aid": "Active-agent aid",
                    "dormant_maintenance": "Dormant maintenance",
                    "auto_revive": "Auto revive",
                },
                "label": "Reserve policy is active, but automatic runtime paths are gated off.",
                "automatic_mechanics_available": False,
                "automatic_support_available": False,
            },
        },
        "duplicate_waves": {
            "summary": {
                "wave_count": 2,
                "proposal_wave_count": 1,
                "forum_wave_count": 1,
                "clustered_item_count": 5,
            },
            "waves": [
                {
                    "id": "proposal:10",
                    "source": "proposal",
                    "count": 3,
                    "actor_count": 2,
                    "representative": {"title": "Emergency food rationing"},
                },
                {
                    "id": "forum:40",
                    "source": "forum",
                    "count": 2,
                    "actor_count": 2,
                    "representative": {"text": "Food shortage coordination"},
                },
            ],
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
    assert [section.get("heading") for section in sections] == [
        "Declared Question",
        "Short Answer",
        "Highlights",
        "Run Arc",
        "Survival Pressure",
        "Governance, Aid, and Public Order",
        "Evidence To Check",
        "What This Does Not Prove",
        "Next Run Watchpoints",
    ]
    claim_texts = [paragraph for section in sections for paragraph in (section.get("paragraphs") or [])]
    assert any("replicate threshold" in str(text) for text in claim_texts)
    for section in sections:
        claim_blocks = section.get("claim_blocks") or []
        assert claim_blocks
        for claim in claim_blocks:
            links = claim.get("evidence_links") or []
            assert links


def test_story_markdown_reads_as_prose_without_claim_prefixes():
    payload = run_reports._build_story_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="baseline_v1",
        season_number=2,
        replicate_count=2,
    )

    markdown = run_reports._story_markdown(payload)

    assert "- Claim:" not in markdown
    assert "## Short Answer" in markdown
    assert "## Highlights" in markdown
    assert "The main arc was survival pressure" in markdown
    assert "## Run Arc" in markdown
    assert "Representative moment" not in markdown


def test_story_payload_includes_gemini_ready_template_without_fallback():
    payload = run_reports._build_story_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="baseline_v1",
        season_number=2,
        replicate_count=2,
    )

    generation = payload["gemini_story_generation"]
    assert payload["story_template_version"] == run_reports.POST_RUN_STORY_TEMPLATE_VERSION
    assert generation["provider"] == "gemini"
    assert generation["model_type"] == run_reports.POST_RUN_STORY_GEMINI_MODEL_TYPE
    assert generation["fallback_allowed"] is False
    assert "Declared Question" in generation["user_prompt"]
    assert "Highlights" in generation["user_prompt"]
    assert "Do not invent events" in generation["system_prompt"]
    assert generation["context"]["required_sections"][0]["heading"] == "Declared Question"


def test_story_highlights_section_summarizes_major_moments_and_pileons():
    snapshot = _sample_snapshot()
    snapshot["activity"]["deaths"] = 1
    snapshot["activity"]["became_dormant"] = 3

    payload = run_reports._build_story_payload(
        snapshot=snapshot,
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="viewer_canary_v1",
        season_number=None,
        replicate_count=1,
    )

    highlight_section = next(section for section in payload["sections"] if section["heading"] == "Highlights")
    highlight_text = "\n".join(highlight_section["paragraphs"])
    assert "Major moments:" in highlight_text
    assert "Who fell: 1 death and 3 dormancy events." in highlight_text
    assert "2 repeated proposal/forum wave(s)" in highlight_text


def test_story_payload_renders_declared_question_from_schedule_metadata():
    snapshot = _sample_snapshot()
    snapshot["declared_question"] = "Do the new viewer/story/evidence changes make a live run easier to follow?"
    snapshot["declared_watch_for"] = "Watch whether the recap answers the viewer-comprehension question."
    snapshot["declared_question_source"] = "static_schedule"

    payload = run_reports._build_story_payload(
        snapshot=snapshot,
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="viewer_canary_v1",
        season_number=None,
        replicate_count=1,
    )

    generation = payload["gemini_story_generation"]
    assert payload["declared_question"] == snapshot["declared_question"]
    assert payload["sections"][0]["paragraphs"] == [snapshot["declared_question"]]
    assert generation["context"]["run_framing"]["declared_question"] == snapshot["declared_question"]
    assert "Mandatory declared question" in generation["user_prompt"]
    assert snapshot["declared_question"] in generation["user_prompt"]


def test_story_payload_can_use_gemini_markdown_as_template_sections():
    generated_markdown = """
## Declared Question
Can the viewer follow the run?

## Short Answer
Yes, but the story still needs tighter evidence links.

## Highlights
Major moments: a law passed and aid requests shaped the run.

## Run Arc
The run opened with resource pressure and moved into governance.

## Survival Pressure
One agent died and several agents became dormant.

## Governance, Aid, and Public Order
The social pattern centered on aid requests and lawmaking.

## Evidence To Check
Check the linked replay moments before treating this as more than a canary.

## What This Does Not Prove
This exploratory canary does not prove a general model-society pattern.

## Next Run Watchpoints
Watch whether the next run is easier to follow live.
""".strip()
    payload = run_reports._build_story_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="baseline_v1",
        season_number=2,
        replicate_count=2,
        generated_story_markdown=generated_markdown,
    )

    assert payload["gemini_story_generation"]["status"] == "generated"
    assert payload["gemini_story_generation"]["generated_markdown"] == generated_markdown
    assert payload["sections"][0]["paragraphs"] == ["Can the viewer follow the run?"]
    assert payload["sections"][0]["generated_by"] == run_reports.POST_RUN_STORY_LLM_GENERATOR_VERSION
    assert payload["sections"][2]["paragraphs"] == ["Major moments: a law passed and aid requests shaped the run."]
    assert payload["deterministic_sections"][0]["heading"] == "Declared Question"


def test_story_payload_rejects_gemini_markdown_with_wrong_declared_question():
    snapshot = _sample_snapshot()
    snapshot["declared_question"] = "Do the new viewer/story/evidence changes make a live run easier to follow?"

    generated_markdown = """
## Declared Question
Did scarcity pressure create durable governance and agent behavior?

## Short Answer
The run mostly showed scarcity pressure.
""".strip()

    with pytest.raises(ValueError, match="different declared question"):
        run_reports._build_story_payload(
            snapshot=snapshot,
            status_label=run_reports.STATUS_OBSERVATIONAL,
            evidence_completeness=run_reports.EVIDENCE_FULL,
            condition_name="viewer_canary_v1",
            season_number=None,
            replicate_count=1,
            generated_story_markdown=generated_markdown,
        )


def test_story_payload_keeps_declared_question_when_gemini_matches_it():
    snapshot = _sample_snapshot()
    snapshot["declared_question"] = "Do the new viewer/story/evidence changes make a live run easier to follow?"

    generated_markdown = """
## Declared Question
Do the new viewer/story/evidence changes make a live run easier to follow?

## Short Answer
Partly: the story had evidence, but the live viewer path still needed work.

## Highlights
Major moments: the report surfaced evidence links.
""".strip()

    payload = run_reports._build_story_payload(
        snapshot=snapshot,
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="viewer_canary_v1",
        season_number=None,
        replicate_count=1,
        generated_story_markdown=generated_markdown,
    )

    assert payload["sections"][0]["paragraphs"] == [snapshot["declared_question"]]
    assert payload["sections"][1]["paragraphs"] == [
        "Partly: the story had evidence, but the live viewer path still needed work."
    ]
    assert payload["sections"][2]["paragraphs"] == ["Major moments: the report surfaced evidence links."]


def test_story_payload_parses_gemini_bullet_labeled_sections():
    generated_markdown = """
- Declared Question: Can the viewer follow the run?
- Short Answer: Yes, but the story still needs tighter evidence links.
- Highlights: Major moments: a repeated proposal wave became visible.
- Run Arc: The run opened with resource pressure and moved into governance.
- Survival Pressure: One agent died and several agents became dormant.
- Governance, Aid, and Public Order: The social pattern centered on aid requests and lawmaking.
- Evidence To Check:
    * Check the linked replay moments.
    * Verify the source events before making claims.
- What This Does Not Prove: This exploratory canary does not prove a general model-society pattern.
- Next Run Watchpoints: Watch whether the next run is easier to follow live.
""".strip()

    payload = run_reports._build_story_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="baseline_v1",
        season_number=2,
        replicate_count=2,
        generated_story_markdown=generated_markdown,
    )

    assert payload["sections"][0]["paragraphs"] == ["Can the viewer follow the run?"]
    assert payload["sections"][6]["paragraphs"] == [
        "Check the linked replay moments.",
        "Verify the source events before making claims.",
    ]


def test_story_payload_strips_generated_links_from_prose():
    generated_markdown = """
## Declared Question:
See [Run Detail](https://wrong.example/runs/1) for context.

## Short Answer
The run remained exploratory.
""".strip()

    payload = run_reports._build_story_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="baseline_v1",
        season_number=2,
        replicate_count=2,
        generated_story_markdown=generated_markdown,
    )

    assert payload["sections"][0]["paragraphs"] == ["See Run Detail for context."]


def test_generate_post_run_story_markdown_uses_configured_gemini_route(monkeypatch):
    payload = run_reports._build_story_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="baseline_v1",
        season_number=2,
        replicate_count=2,
    )
    calls: list[dict[str, object]] = []

    class FakeClient:
        async def get_completion(self, **kwargs):
            calls.append(kwargs)
            return "```markdown\n## Declared Question\nCanary question.\n```"

    import app.services.llm_client as llm_client_module

    monkeypatch.setattr(llm_client_module, "llm_client", FakeClient())
    monkeypatch.setattr(run_reports.settings, "RUN_REPORT_STORY_LLM_MODEL_TYPE", "gm_gemini_2_5_flash", raising=False)

    markdown = asyncio.run(run_reports.generate_post_run_story_markdown_with_gemini(payload))

    assert markdown == "## Declared Question\nCanary question."
    assert calls[0]["model_type"] == "gm_gemini_2_5_flash"
    assert calls[0]["usage_run_id"] == "run-20260210T120000Z"
    assert calls[0]["max_retries"] == 2


def test_viewer_brief_payload_requires_news_sections_and_declared_question():
    snapshot = _sample_snapshot()
    snapshot["declared_question"] = "Do the new viewer/story/evidence changes make a live run easier to follow?"

    generated_markdown = """
## Headline
Emergence run turns on readable evidence.

## Run Question
Do the new viewer/story/evidence changes make a live run easier to follow?

## The Lead
The run gave viewers a compact story to follow.

## What Changed
Proposal discussion and evidence links shaped the public recap.

## Who Fell
No deaths or dormancy events were listed in the supplied context.

## Governance Desk
The brief sticks to provided proposal, vote, and law counts.

## Aid, Trade, and Conflict
The brief reports only supplied aid, trade, and conflict counts.

## Strange But True
Repeated proposal/forum waves became one grouped pattern.

## What To Watch Next
Watch whether a future run remains readable live.
""".strip()

    payload = run_reports._build_viewer_brief_payload(
        snapshot=snapshot,
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="viewer_canary_v1",
        season_number=None,
        replicate_count=1,
        generated_brief_markdown=generated_markdown,
    )

    generation = payload["gemini_viewer_brief_generation"]
    assert payload["viewer_brief_template_version"] == run_reports.VIEWER_BRIEF_TEMPLATE_VERSION
    assert generation["provider"] == "gemini"
    assert generation["fallback_allowed"] is False
    assert "accessible public news brief" in generation["context"]["style_contract"]["format"]
    assert "Do not invent events" in generation["system_prompt"]
    assert "agents, not entities" in generation["system_prompt"]
    assert "Run Question" in generation["user_prompt"]
    assert "The Lead must answer it" in generation["user_prompt"]
    assert "next run or future run" in generation["user_prompt"]
    assert payload["sections"][1]["paragraphs"] == [snapshot["declared_question"]]
    assert payload["sections"][8]["paragraphs"] == [
        "Watch whether the next run stays readable live and whether the post-run evidence links explain the biggest events."
    ]
    assert payload["sections"][2]["generated_by"] == run_reports.VIEWER_BRIEF_LLM_GENERATOR_VERSION


def test_viewer_brief_rejects_wrong_declared_question():
    snapshot = _sample_snapshot()
    snapshot["declared_question"] = "Do the new viewer/story/evidence changes make a live run easier to follow?"
    generated_markdown = """
## Headline
Scarcity dominates the run.

## Run Question
Did scarcity pressure create durable governance?

## The Lead
The lead is grounded in the supplied context.

## What Changed
The reported changes are constrained to supplied evidence.

## Who Fell
The section repeats supplied survival counts.

## Governance Desk
The section uses supplied governance counts.

## Aid, Trade, and Conflict
The section uses supplied social counts.

## Strange But True
The section names only supplied repeated-wave evidence.

## What To Watch Next
The section keeps watchpoints concrete.
""".strip()

    with pytest.raises(ValueError, match="different declared question"):
        run_reports._build_viewer_brief_payload(
            snapshot=snapshot,
            status_label=run_reports.STATUS_OBSERVATIONAL,
            evidence_completeness=run_reports.EVIDENCE_FULL,
            condition_name="viewer_canary_v1",
            season_number=None,
            replicate_count=1,
            generated_brief_markdown=generated_markdown,
        )


def test_viewer_brief_rejects_unsupported_comparative_wording():
    generated_markdown = """
## Headline
Scarcity pressure shaped the run.

## Run Question
Can viewers follow the run?

## The Lead
The run showed a significant increase in clarity for viewers.

## What Changed
There was an increase in aid requests during the run.

## Who Fell
Four agents ceased to function.

## Governance Desk
The section uses supplied governance counts.

## Aid, Trade, and Conflict
The section uses supplied social counts.

## Strange But True
The section names only supplied repeated-wave evidence.

## What To Watch Next
Watch whether the next run remains readable.
""".strip()

    with pytest.raises(ValueError, match="unsupported comparative"):
        run_reports._build_viewer_brief_payload(
            snapshot=_sample_snapshot(),
            status_label=run_reports.STATUS_OBSERVATIONAL,
            evidence_completeness=run_reports.EVIDENCE_FULL,
            condition_name="viewer_canary_v1",
            season_number=None,
            replicate_count=1,
            generated_brief_markdown=generated_markdown,
        )


def test_viewer_brief_markdown_reads_as_brief_with_evidence_links():
    payload = run_reports._build_viewer_brief_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="viewer_canary_v1",
        season_number=None,
        replicate_count=1,
    )

    markdown = run_reports._viewer_brief_markdown(payload)

    assert markdown.startswith("# The Emergence Brief:")
    assert "## The Lead" in markdown
    assert "## Strange But True" in markdown
    assert "Evidence:" in markdown


def test_generate_viewer_brief_markdown_uses_configured_gemini_route(monkeypatch):
    payload = run_reports._build_viewer_brief_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="viewer_canary_v1",
        season_number=None,
        replicate_count=1,
    )
    calls: list[dict[str, object]] = []

    class FakeClient:
        async def get_completion(self, **kwargs):
            calls.append(kwargs)
            return "```markdown\n## Headline\nA grounded brief.\n```"

    import app.services.llm_client as llm_client_module

    monkeypatch.setattr(llm_client_module, "llm_client", FakeClient())
    monkeypatch.setattr(run_reports.settings, "RUN_REPORT_STORY_LLM_MODEL_TYPE", "gm_gemini_2_5_flash", raising=False)

    markdown = asyncio.run(run_reports.generate_viewer_brief_markdown_with_gemini(payload))

    assert markdown == "## Headline\nA grounded brief."
    assert calls[0]["model_type"] == "gm_gemini_2_5_flash"
    assert calls[0]["usage_run_id"] == "run-20260210T120000Z"
    assert calls[0]["max_retries"] == 2


def test_repair_viewer_brief_markdown_uses_same_gemini_route(monkeypatch):
    payload = run_reports._build_viewer_brief_payload(
        snapshot=_sample_snapshot(),
        status_label=run_reports.STATUS_OBSERVATIONAL,
        evidence_completeness=run_reports.EVIDENCE_FULL,
        condition_name="viewer_canary_v1",
        season_number=None,
        replicate_count=1,
    )
    calls: list[dict[str, object]] = []

    class FakeClient:
        async def get_completion(self, **kwargs):
            calls.append(kwargs)
            return "```markdown\n## Headline\nA repaired brief.\n```"

    import app.services.llm_client as llm_client_module

    monkeypatch.setattr(llm_client_module, "llm_client", FakeClient())
    monkeypatch.setattr(run_reports.settings, "RUN_REPORT_STORY_LLM_MODEL_TYPE", "gm_gemini_2_5_flash", raising=False)

    markdown = asyncio.run(
        run_reports.repair_viewer_brief_markdown_with_gemini(
            payload,
            invalid_markdown="The run had a story, but no required headings.",
            validation_error="missed required sections: Headline, Run Question",
        )
    )

    assert markdown == "## Headline\nA repaired brief."
    assert calls[0]["model_type"] == "gm_gemini_2_5_flash"
    assert calls[0]["usage_run_id"] == "run-20260210T120000Z"
    assert "## Headline" in calls[0]["user_prompt"]
    assert "## Run Question" in calls[0]["user_prompt"]
    assert "missed required sections: Headline, Run Question" in calls[0]["user_prompt"]
    assert "The run had a story, but no required headings." in calls[0]["user_prompt"]


def test_generate_viewer_brief_artifact_repairs_invalid_gemini_markdown(monkeypatch, tmp_path):
    snapshot = _sample_snapshot()
    snapshot["declared_question"] = "Do the new viewer/story/evidence changes make a live run easier to follow?"
    invalid_markdown = """
## The Lead
The first draft missed two required headings.
""".strip()
    repaired_markdown = """
## Headline
Viewer evidence gets clearer.

## Run Question
Do the new viewer/story/evidence changes make a live run easier to follow?

## The Lead
The repaired brief answers the declared viewer question first.

## What Changed
Evidence links and repeated proposal grouping changed the public read.

## Who Fell
The supplied context does not list a specific death.

## Governance Desk
The brief reports only supplied proposal and vote counts.

## Aid, Trade, and Conflict
The brief reports only supplied aid, trade, and conflict counts.

## Strange But True
Repeated proposal/forum waves became one grouped pattern.

## What To Watch Next
Watch whether the next run remains easier to follow live.
""".strip()
    repair_calls: list[dict[str, object]] = []
    recorded: list[dict[str, object]] = []

    monkeypatch.setattr(run_reports, "_collect_run_snapshot", lambda _db, *, run_id: snapshot)
    monkeypatch.setattr(run_reports, "_assert_snapshot_has_run_data", lambda _snapshot, *, run_id: None)
    monkeypatch.setattr(
        run_reports,
        "_resolve_report_context",
        lambda *, snapshot, condition_name, season_number: ("viewer_canary_v1", 0),
    )
    monkeypatch.setattr(
        run_reports,
        "_count_condition_replicates",
        lambda _db, *, condition_name, run_id: (1, run_reports.RUN_CLASS_SPECIAL_EXPLORATORY, None),
    )
    def _fake_artifact_dir(run_id):
        outdir = tmp_path / run_id
        outdir.mkdir(parents=True, exist_ok=True)
        return outdir

    monkeypatch.setattr(run_reports, "_artifact_dir_for_run", _fake_artifact_dir)
    monkeypatch.setattr(run_reports, "_run_viewer_brief_generation_blocking", lambda payload: invalid_markdown)

    def _fake_repair(payload, *, invalid_markdown, validation_error):
        repair_calls.append(
            {
                "invalid_markdown": invalid_markdown,
                "validation_error": validation_error,
            }
        )
        return repaired_markdown

    def _fake_record_artifact(_db, **kwargs):
        recorded.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(run_reports, "_run_viewer_brief_repair_blocking", _fake_repair)
    monkeypatch.setattr(run_reports, "_record_artifact", _fake_record_artifact)

    payload = run_reports.generate_run_viewer_brief_artifact(
        SimpleNamespace(),
        run_id="run-20260210T120000Z",
        condition_name="viewer_canary_v1",
        season_number=0,
        generate_with_gemini=True,
    )

    assert repair_calls
    assert "Headline, Run Question" in repair_calls[0]["validation_error"]
    assert payload["gemini_viewer_brief_generation"]["status"] == "generated"
    assert payload["gemini_viewer_brief_generation"]["generated_markdown"] == repaired_markdown
    assert payload["sections"][1]["paragraphs"] == [snapshot["declared_question"]]
    assert payload["sections"][8]["paragraphs"] == [
        "Watch whether the next run stays readable live and whether the post-run evidence links explain the biggest events."
    ]
    assert {item["artifact_type"] for item in recorded} == {"viewer_brief"}


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
    assert "Exploratory claim boundary" in markdown


def test_closeout_comparison_flags_auto_revival_confound_resolution():
    previous = _sample_snapshot()
    previous["run_id"] = "real-20260425T021634Z"
    previous["condition_name"] = "canary_h"
    previous["activity"] = {
        **previous["activity"],
        "became_dormant": 115,
        "agent_revived": 101,
        "reserve_aid": 101,
        "reserve_shortfall": 0,
        "starvation_warnings": 0,
        "deaths": 0,
        "trade_actions": 22,
        "forum_actions": 95,
    }
    previous["social_followthrough"] = {
        "aid_requests": 20,
        "answered": 13,
        "clean_unanswered": 0,
        "clean_followthrough_rate": 1.0,
        "distinct_responders": 4,
        "targets": [{"agent_number": 33, "display_name": "Glyph-33", "requests": 9, "answered": 7}],
    }
    previous["behavior_hygiene"] = {"repeated_message_fingerprint_count": 12}

    current = _sample_snapshot()
    current["run_id"] = "real-20260425T203241Z"
    current["condition_name"] = "canary_i"
    current["activity"] = {
        **current["activity"],
        "became_dormant": 32,
        "agent_revived": 2,
        "reserve_aid": 0,
        "reserve_shortfall": 0,
        "starvation_warnings": 72,
        "deaths": 8,
        "trade_actions": 21,
        "forum_actions": 123,
    }
    current["social_followthrough"] = {
        "aid_requests": 18,
        "answered": 16,
        "clean_unanswered": 2,
        "clean_followthrough_rate": 0.8889,
        "distinct_responders": 5,
        "targets": [{"agent_number": 6, "display_name": "Sigma-06", "requests": 8, "answered": 8}],
    }
    current["behavior_hygiene"] = {"repeated_message_fingerprint_count": 12}
    current["duplicate_waves"] = {
        "summary": {
            "wave_count": 2,
            "proposal_wave_count": 1,
            "forum_wave_count": 1,
            "clustered_item_count": 5,
        },
        "waves": [],
    }

    comparison = run_reports._build_closeout_comparison(
        current_snapshot=current,
        previous_snapshot=previous,
    )

    assert comparison is not None
    assert comparison["previous_run_id"] == "real-20260425T021634Z"
    metric_deltas = {row["key"]: row["delta"] for row in comparison["metrics"]}
    assert metric_deltas["deaths"] == 8
    assert metric_deltas["reserve_aid"] == -101
    assert comparison["aid_followthrough"]["current"]["dominant_target"]["display_name"] == "Sigma-06"
    assert comparison["duplicate_waves"]["current"] == 2
    assert comparison["duplicate_waves"]["current_proposal_waves"] == 1
    assert any("resolves the prior auto-revival confound" in line for line in comparison["interpretation"])


def test_technical_markdown_includes_closeout_comparison_section():
    payload = {
        **_sample_snapshot(),
        "generated_at_utc": "2026-04-26T12:40:00+00:00",
        "run_started_at": "2026-04-25T20:33:12+00:00",
        "run_ended_at": "2026-04-26T12:32:44+00:00",
        "verification_state": "verified",
        "verification_source": "run_registry",
        "status_label": run_reports.STATUS_OBSERVATIONAL,
        "evidence_completeness": run_reports.EVIDENCE_FULL,
        "condition_name": "canary_i",
        "replicate_count": 1,
        "social_followthrough": {},
        "behavior_hygiene": {},
        "closeout_comparison": {
            "previous_run_id": "real-20260425T021634Z",
            "previous_condition_name": "canary_h",
            "metrics": [{"key": "deaths", "current": 8, "previous": 0, "delta": 8}],
            "aid_followthrough": {
                "current": {"aid_requests": 18, "answered": 16, "clean_unanswered": 2, "clean_followthrough_rate": 0.8889, "distinct_responders": 5},
                "previous": {"aid_requests": 20, "answered": 13, "clean_unanswered": 0, "clean_followthrough_rate": 1.0, "distinct_responders": 4},
            },
            "repeated_message_fingerprints": {"current": 12, "previous": 12, "delta": 0},
            "duplicate_waves": {"current": 2, "previous": 0, "delta": 2, "current_proposal_waves": 1, "current_forum_waves": 1},
            "interpretation": ["The current run resolves the prior auto-revival confound."],
        },
        "caveats": [],
        "evidence_links": [{"label": "Run Detail", "href": "/runs/real-20260425T203241Z"}],
    }

    markdown = run_reports._technical_markdown(payload)

    assert "## Closeout Comparison" in markdown
    assert "## Reserve Policy vs Mechanical Access" in markdown
    assert "Policy intent: Active reserve policy intent (1 active reserve laws)" in markdown
    assert "Automatic reserve mechanics available: False" in markdown
    assert "## Duplicate Waves" in markdown
    assert "Repeated proposal/forum waves: 2" in markdown
    assert "Duplicate proposal/forum waves: current=2, previous=0, delta=+2" in markdown
    assert "Previous run: real-20260425T021634Z" in markdown
    assert "deaths: current=8, previous=0, delta=+8" in markdown
    assert "resolves the prior auto-revival confound" in markdown


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
    Message.__table__.create(bind=engine)
    Proposal.__table__.create(bind=engine)
    Law.__table__.create(bind=engine)
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
                    error_type TEXT NULL,
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


def test_collect_run_snapshot_prefers_story_signals_over_recent_routine_events():
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
                run_id="run-story-signals",
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
                event_type="law_passed",
                description="Agents passed an emergency aid floor.",
                event_metadata={"runtime": {"run_id": "run-story-signals", "run_mode": "test"}},
                created_at=started_at + run_reports.timedelta(minutes=2),
            )
        )
        for index in range(20):
            db_session.add(
                Event(
                    agent_id=agent.id,
                    event_type="work",
                    description=f"Agent performed routine work {index}.",
                    event_metadata={"runtime": {"run_id": "run-story-signals", "run_mode": "test"}},
                    created_at=started_at + run_reports.timedelta(minutes=10 + index),
                )
            )
        db_session.commit()

        snapshot = run_reports._collect_run_snapshot(db_session, run_id="run-story-signals")

        assert snapshot["key_moments"]
        assert snapshot["key_moments"][0]["event_type"] == "law_passed"
        assert all(moment["event_type"] != "work" for moment in snapshot["key_moments"])
    finally:
        db_session.close()


def test_collect_run_snapshot_uses_historical_reserve_laws_after_close():
    db_session = _build_snapshot_session()
    try:
        started_at = datetime(2026, 5, 1, 14, 49, tzinfo=timezone.utc)
        ended_at = datetime(2026, 5, 2, 6, 49, tzinfo=timezone.utc)
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
                run_id="run-reserve-closed",
                run_mode="real",
                protocol_version="protocol_v1",
                condition_name="reserve_closed_test",
                run_class="special_exploratory",
                started_at=started_at,
                ended_at=ended_at,
            )
        )
        db_session.add(
            Law(
                title="Active Reserve Aid Standing Law",
                description="Top up active agents from the shared survival reserve.",
                law_class="standing_law",
                runtime_effect={
                    "type": "active_reserve_aid",
                    "trigger_food_below": 5,
                    "trigger_energy_below": 6,
                    "target_food": 7,
                    "target_energy": 8,
                    "min_pool_remaining": 100,
                },
                author_agent_id=agent.id,
                active=False,
                passed_at=started_at + timedelta(hours=1),
            )
        )
        db_session.add(
            Event(
                agent_id=agent.id,
                event_type="reserve_aid",
                description="shared reserve covered active deficit",
                event_metadata={"runtime": {"run_id": "run-reserve-closed", "run_mode": "real"}},
                created_at=started_at + timedelta(hours=2),
            )
        )
        db_session.commit()

        snapshot = run_reports._collect_run_snapshot(db_session, run_id="run-reserve-closed")
        policy = snapshot["reserve_semantics"]["policy_intent"]

        assert policy["scope"] == "historical_run"
        assert policy["reserve_law_count"] == 1
        assert policy["executable_active_aid_law_ids"]
        assert snapshot["reserve_semantics"]["mechanical_access"]["automatic_support_available"] is True
    finally:
        db_session.close()


def test_rebuild_run_bundle_refuses_missing_run_data():
    db_session = _build_snapshot_session()
    try:
        try:
            run_reports.rebuild_run_bundle(
                db_session,
                run_id="missing-run",
                actor_id="test",
            )
        except ValueError as exc:
            assert "Refusing to generate report bundle" in str(exc)
            assert "no run-scoped events or LLM usage" in str(exc)
        else:
            raise AssertionError("Expected missing run data to block report generation")
    finally:
        db_session.close()


def test_artifact_generation_derives_condition_and_season_from_run_registry(tmp_path, monkeypatch):
    db_session = _build_snapshot_session()
    try:
        started_at = datetime(2026, 4, 15, 9, 0, tzinfo=timezone.utc)
        ended_at = datetime(2026, 4, 15, 23, 0, tzinfo=timezone.utc)
        agent = Agent(
            agent_number=8,
            display_name="Planner Agent",
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
                run_id="real-20260415T085921Z",
                run_mode="real",
                protocol_version="protocol_v1",
                condition_name="real_scarcity_tuning_20260415_tight_v5_patch2",
                season_number=4,
                run_class="special_exploratory",
                started_at=started_at,
                ended_at=ended_at,
            )
        )
        db_session.execute(
            text(
                """
                INSERT INTO llm_usage (
                    run_id, agent_id, success, fallback_used, prompt_tokens, completion_tokens,
                    total_tokens, estimated_cost_usd, provider, model_name, resolved_model_name, created_at
                ) VALUES (
                    :run_id, :agent_id, 1, 0, 10, 20, 30, 0.01, 'openrouter', 'gpt-oss-20b:free', NULL, :created_at
                )
                """
            ),
            {
                "run_id": "real-20260415T085921Z",
                "agent_id": agent.id,
                "created_at": started_at + run_reports.timedelta(minutes=5),
            },
        )
        db_session.add(
            Event(
                agent_id=agent.id,
                event_type="reserve_aid",
                description="evidence-backed survival support",
                event_metadata={"runtime": {"run_id": "real-20260415T085921Z", "run_mode": "real"}},
                created_at=started_at + run_reports.timedelta(minutes=6),
            )
        )
        db_session.commit()

        monkeypatch.setattr(run_reports, "_record_artifact", lambda *args, **kwargs: None)
        def _artifact_dir_for_run(_run_id: str):
            outdir = tmp_path / run_reports._slug_fragment(_run_id, fallback="run")
            outdir.mkdir(parents=True, exist_ok=True)
            return outdir

        monkeypatch.setattr(run_reports, "_artifact_dir_for_run", _artifact_dir_for_run)

        technical_payload = run_reports.generate_run_technical_artifact(
            db_session,
            run_id="real-20260415T085921Z",
        )
        planner_payload = run_reports.generate_next_run_plan_artifact(
            db_session,
            run_id="real-20260415T085921Z",
        )

        assert technical_payload["condition_name"] == "real_scarcity_tuning_20260415_tight_v5_patch2"
        assert technical_payload["season_number"] == 4
        assert "condition:real_scarcity_tuning_20260415_tight_v5_patch2" in (technical_payload.get("tags") or [])
        assert planner_payload["condition_name"] == "real_scarcity_tuning_20260415_tight_v5_patch2"
    finally:
        db_session.close()


def test_collect_run_snapshot_includes_provider_failures_and_worst_window():
    db_session = _build_snapshot_session()
    try:
        started_at = datetime(2026, 4, 18, 8, 0, tzinfo=timezone.utc)
        agent = Agent(
            agent_number=9,
            display_name="Reliability Agent",
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
                run_id="real-20260418T071530Z",
                run_mode="real",
                protocol_version="protocol_v1",
                condition_name="real_scarcity_tuning_20260417_tight_v6_social_memory_patch2",
                run_class="special_exploratory",
                started_at=started_at,
            )
        )
        db_session.execute(
            text(
                """
                INSERT INTO llm_usage (
                    run_id, agent_id, success, fallback_used, prompt_tokens, completion_tokens,
                    total_tokens, estimated_cost_usd, provider, model_name, resolved_model_name, error_type, created_at
                ) VALUES
                    (:run_id, :agent_id, 1, 0, 10, 20, 30, 0.01, 'gemini', 'flash', NULL, NULL, :t1),
                    (:run_id, :agent_id, 0, 0, 10, 20, 30, 0.01, 'gemini', 'flash', NULL, 'RateLimitError', :t2),
                    (:run_id, :agent_id, 0, 0, 10, 20, 30, 0.01, 'openrouter', 'gpt-oss-20b:free', NULL, 'InternalServerError', :t2),
                    (:run_id, :agent_id, 1, 0, 10, 20, 30, 0.01, 'openrouter', 'gpt-oss-20b:free', NULL, NULL, :t3)
                """
            ),
            {
                "run_id": "real-20260418T071530Z",
                "agent_id": agent.id,
                "t1": started_at + run_reports.timedelta(minutes=1),
                "t2": started_at + run_reports.timedelta(minutes=7),
                "t3": started_at + run_reports.timedelta(minutes=19),
            },
        )
        db_session.commit()

        snapshot = run_reports._collect_run_snapshot(db_session, run_id="real-20260418T071530Z")

        by_provider = {row["provider"]: row for row in snapshot["llm"]["by_provider"]}
        assert snapshot["llm"]["failure_calls"] == 2
        assert by_provider["gemini"]["failure_calls"] == 1
        assert by_provider["gemini"]["rate_limit_failures"] == 1
        assert by_provider["openrouter"]["failure_calls"] == 1
        assert snapshot["llm"]["worst_failure_window"]["failure_calls"] >= 1
    finally:
        db_session.close()


def test_aid_request_followthrough_classifies_provider_and_mechanical_confounds():
    db_session = _build_snapshot_session()
    try:
        started_at = datetime(2026, 4, 23, 15, 0, tzinfo=timezone.utc)
        requester = Agent(
            agent_number=1,
            display_name="Requester",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        provider_failed = Agent(
            agent_number=2,
            display_name="Provider Failed",
            model_type="gm_gemini_2_0_flash",
            tier=2,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        responder = Agent(
            agent_number=3,
            display_name="Responder",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        unaffordable = Agent(
            agent_number=4,
            display_name="No Energy",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        db_session.add_all([requester, provider_failed, responder, unaffordable])
        db_session.flush()
        db_session.add_all(
            [
                Event(
                    agent_id=requester.id,
                    event_type="request_aid",
                    description="Requester asked Provider Failed for energy",
                    event_metadata={
                        "action": {"target_agent_id": provider_failed.id},
                        "runtime": {"run_id": "run-followthrough"},
                    },
                    created_at=started_at + run_reports.timedelta(minutes=1),
                ),
                Event(
                    agent_id=requester.id,
                    event_type="request_aid",
                    description="Requester asked Responder for food",
                    event_metadata={
                        "action": {"target_agent_id": responder.id},
                        "runtime": {"run_id": "run-followthrough"},
                    },
                    created_at=started_at + run_reports.timedelta(minutes=2),
                ),
                Event(
                    agent_id=responder.id,
                    event_type="trade",
                    description="Responder traded food to Requester",
                    event_metadata={
                        "action": {"recipient_agent_id": requester.id},
                        "runtime": {"run_id": "run-followthrough"},
                    },
                    created_at=started_at + run_reports.timedelta(minutes=3),
                ),
                Event(
                    agent_id=requester.id,
                    event_type="request_aid",
                    description="Requester asked No Energy for energy",
                    event_metadata={
                        "action": {"target_agent_id": unaffordable.id},
                        "runtime": {"run_id": "run-followthrough"},
                    },
                    created_at=started_at + run_reports.timedelta(minutes=4),
                ),
                Event(
                    agent_id=unaffordable.id,
                    event_type="idle",
                    description="Agent chose to rest after an unaffordable action: Insufficient energy",
                    event_metadata={"runtime": {"run_id": "run-followthrough"}},
                    created_at=started_at + run_reports.timedelta(minutes=5),
                ),
            ]
        )
        db_session.execute(
            text(
                """
                INSERT INTO llm_usage (
                    run_id, agent_id, success, fallback_used, prompt_tokens, completion_tokens,
                    total_tokens, estimated_cost_usd, provider, model_name, resolved_model_name, error_type, created_at
                ) VALUES
                    ('run-followthrough', :provider_failed_id, 0, 0, 0, 0, 0, 0, 'gemini', 'gemini-2.0-flash', NULL, 'RateLimitError', :t1),
                    ('run-followthrough', :responder_id, 1, 0, 1, 1, 2, 0, 'gemini', 'gemini-2.5-flash', NULL, NULL, :t2),
                    ('run-followthrough', :unaffordable_id, 1, 0, 1, 1, 2, 0, 'gemini', 'gemini-2.5-flash', NULL, NULL, :t3)
                """
            ),
            {
                "provider_failed_id": provider_failed.id,
                "responder_id": responder.id,
                "unaffordable_id": unaffordable.id,
                "t1": started_at + run_reports.timedelta(minutes=1, seconds=30),
                "t2": started_at + run_reports.timedelta(minutes=2, seconds=30),
                "t3": started_at + run_reports.timedelta(minutes=4, seconds=30),
            },
        )
        db_session.commit()

        payload = run_reports._collect_aid_request_followthrough(
            db_session,
            run_id="run-followthrough",
            run_started_at=started_at,
            run_ended_at=started_at + run_reports.timedelta(minutes=10),
        )

        assert payload["aid_requests"] == 3
        assert payload["answered"] == 1
        assert payload["provider_confounded"] == 1
        assert payload["mechanically_unaffordable"] == 1
        assert payload["clean_unanswered"] == 0
        assert payload["clean_followthrough_rate"] == 1.0
    finally:
        db_session.close()
