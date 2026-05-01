from __future__ import annotations

import asyncio
import importlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.time import now_utc
from app.models.models import Agent, Message, SocialPostDraft

twitter_api = importlib.import_module("app.api.twitter")
twitter_bot_module = importlib.import_module("app.services.twitter_bot")
scheduler = importlib.import_module("app.services.scheduler")
social_drafts = importlib.import_module("app.services.social_drafts")


@pytest.fixture
def session_factory():
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

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, future=True)
    try:
        yield factory
    finally:
        engine.dispose()


def test_send_tweet_creates_durable_draft_when_delivery_disabled(session_factory, monkeypatch):
    monkeypatch.setattr(social_drafts, "SessionLocal", session_factory)
    monkeypatch.setattr(
        social_drafts.runtime_config_service,
        "get_effective_value_cached",
        lambda key: {
            "SIMULATION_RUN_ID": "real-draft-test",
            "SIMULATION_RUN_MODE": "real",
        }.get(key, ""),
    )
    monkeypatch.setenv("TWITTER_ENABLED", "false")
    monkeypatch.setenv("FRONTEND_URL", "https://emergence.quest")

    bot = twitter_bot_module.TwitterBot()
    content = twitter_bot_module.TweetContent(
        tweet_type=twitter_bot_module.TweetType.LAW_PASSED,
        text="New law: Resource Commons",
        url="/laws",
        priority=7,
    )

    success = asyncio.run(bot.send_tweet(content))

    assert success is False
    assert bot.last_dispatch_status == "drafted"

    with session_factory() as db:
        draft = db.query(SocialPostDraft).one()

    assert draft.status == "pending_review"
    assert draft.draft_type == "law_passed"
    assert draft.run_id == "real-draft-test"
    assert draft.run_mode == "real"
    assert draft.full_text.endswith("/laws")
    assert draft.error_message == "twitter_delivery_disabled"
    assert draft.metadata_json["editorial_frame"]["format_version"] == "context-light-v1"


def test_tweet_formatter_adds_tension_and_evidence_fields():
    formatter = twitter_bot_module.TweetFormatter()

    content = formatter.format_law_passed(
        law_name="Reserve Rationing Act",
        law_id=14,
        yes_votes=11,
        no_votes=8,
        description="Cuts reserve draws during low-supply cycles.",
    )

    assert "Tension:" in content.text
    assert "Evidence:" in content.text
    assert content.stake == "The rulebook moved by a 11-8 vote."
    assert "Cuts reserve draws" in str(content.consequence)


def test_twitter_drafts_api_lists_and_updates_review_state(session_factory, monkeypatch):
    monkeypatch.setattr(twitter_api, "TWITTER_AVAILABLE", True)
    monkeypatch.setattr(twitter_api, "_assert_writes_enabled", lambda actor: None)

    with session_factory() as db:
        draft = SocialPostDraft(
            platform="x",
            draft_type="proposal_created",
            status="pending_review",
            text="Draft proposal post",
            full_text="Draft proposal post\n\nhttps://emergence.quest/proposals",
            url="/proposals",
            priority=5,
            source_service="worker",
        )
        db.add(draft)
        db.commit()
        draft_id = int(draft.id)

    app = FastAPI()
    app.include_router(twitter_api.router, prefix="/api")
    app.dependency_overrides[twitter_api.get_db] = lambda: session_factory()
    app.dependency_overrides[twitter_api.require_admin_auth] = lambda: twitter_api.AdminActor(
        actor_id="ops",
        client_ip="127.0.0.1",
    )

    with TestClient(app) as client:
        list_response = client.get("/api/twitter/drafts")
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == draft_id

        patch_response = client.patch(
            f"/api/twitter/drafts/{draft_id}",
            json={
                "status": "posted",
                "review_note": "Posted manually to X",
                "posted_url": "https://x.com/emergencequest/status/123",
                "external_post_id": "123",
            },
        )

    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["status"] == "posted"
    assert updated["review_note"] == "Posted manually to X"
    assert updated["posted_url"] == "https://x.com/emergencequest/status/123"
    assert updated["external_post_id"] == "123"
    assert updated["reviewed_by"] == "ops"


def test_quote_selection_dedupes_against_pending_drafts(session_factory, monkeypatch):
    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    monkeypatch.setattr(social_drafts, "SessionLocal", session_factory)
    monkeypatch.setattr(
        scheduler.runtime_config_service,
        "get_effective_value_cached",
        lambda _key: "",
    )
    monkeypatch.setattr(scheduler, "_twitter_ready", lambda: True)
    monkeypatch.setattr(scheduler, "TweetType", twitter_bot_module.TweetType)
    monkeypatch.setattr(scheduler, "twitter_bot", SimpleNamespace(tweet_queue=[]))
    called = {"count": 0}

    async def _fake_quote_sender(**_kwargs):
        called["count"] += 1
        return True

    monkeypatch.setattr(scheduler, "tweet_notable_quote", _fake_quote_sender)

    quote_text = (
        "Why should we hoard resources when an alliance to survive together could save everyone?"
    )
    now = now_utc()
    with session_factory() as db:
        agent = Agent(
            agent_number=7,
            display_name="Echo-07",
            model_type="llama-3.1-8b",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="test",
            created_at=now - timedelta(hours=2),
            last_active_at=now,
        )
        db.add(agent)
        db.flush()
        db.add(
            Message(
                author_agent_id=agent.id,
                content=quote_text,
                message_type="forum_post",
                created_at=now - timedelta(minutes=5),
            )
        )
        db.add(
            SocialPostDraft(
                platform="x",
                draft_type=twitter_bot_module.TweetType.NOTABLE_QUOTE.value,
                status="pending_review",
                text=quote_text,
                full_text=f"💬 \"{quote_text}\"\n\n— Echo-07, Day 1\n\nhttps://emergence.quest/agents/7",
                priority=6,
            )
        )
        db.commit()

    result = asyncio.run(scheduler.tweet_high_salience_quote())

    assert result is None
    assert called["count"] == 0


def test_quote_quality_rejects_procedural_governance_summary():
    quote_text = (
        "Proposal #662 is executable and provides a clear mechanism for common pool aid. "
        "This is crucial for stability and aligns with the voluntary protocol."
    )

    assert scheduler._passes_quote_quality_gate(
        quote_text,
        recent_quotes=[],
        max_overlap=0.85,
    ) is False


def test_quote_quality_allows_first_person_stakes():
    quote_text = (
        "Scalar-19, I oppose a one-time allocation from my personal surplus. "
        "My resources are for my autonomy."
    )

    assert scheduler._passes_quote_quality_gate(
        quote_text,
        recent_quotes=[],
        max_overlap=0.85,
    ) is True
