from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from decimal import Decimal

from app.models.models import Agent, AgentInventory, Event, GlobalResources, Proposal
from app.models.predictions import PredictionBet, PredictionMarket, UserPoints

predictions_api = importlib.import_module("app.api.predictions")


@pytest.fixture
def predictions_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db_session = sessionmaker(bind=engine, future=True)()

    monkeypatch.setattr(predictions_api.settings, "SECRET_KEY", "test-secret", raising=False)
    monkeypatch.setattr(predictions_api.settings, "ENVIRONMENT", "test", raising=False)
    monkeypatch.setattr(
        predictions_api.runtime_config_service,
        "get_effective_value_cached",
        lambda key: True if key == "SIMULATION_ACTIVE" else None,
    )

    db_session.add(
        PredictionMarket(
            title="Will test market pass?",
            description="Test market",
            market_type="custom",
            status="open",
            closes_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    db_session.commit()

    app = FastAPI()
    app.include_router(predictions_api.router, prefix="/api/predictions")
    app.dependency_overrides[predictions_api.get_db] = lambda: db_session
    client = TestClient(app)
    try:
        yield client, db_session
    finally:
        db_session.close()


def test_prediction_identity_ignores_spoofed_header_and_sets_cookie(predictions_client):
    client, _db = predictions_client

    first = client.get("/api/predictions/me", headers={"x-user-id": "spoofed_user"})
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["user_id"].startswith("pred_")
    assert first_payload["user_id"] != "spoofed_user"
    assert predictions_api.PREDICTION_USER_COOKIE in first.cookies

    second = client.get("/api/predictions/me", headers={"x-user-id": "another_spoof"})
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["user_id"] == first_payload["user_id"]


def test_prediction_bet_uses_cookie_identity(predictions_client):
    client, db_session = predictions_client
    market = db_session.query(PredictionMarket).first()

    me = client.get("/api/predictions/me")
    user_id = me.json()["user_id"]

    bet = client.post(
        f"/api/predictions/markets/{market.id}/bet",
        json={"prediction": "yes", "amount": 5},
        headers={"x-user-id": "forged_other_user"},
    )
    assert bet.status_code == 200

    refreshed = client.get("/api/predictions/me")
    assert refreshed.json()["user_id"] == user_id
    assert refreshed.json()["bets_made"] == 1


def test_list_markets_auto_generates_live_audience_hooks(predictions_client):
    client, db_session = predictions_client
    now = datetime.now(timezone.utc)

    agent = Agent(
        agent_number=7,
        display_name="Beacon-07",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="stability",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=1),
        last_active_at=now,
    )
    db_session.add(agent)
    db_session.flush()

    db_session.add_all(
        [
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=0.5),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=0.25),
            GlobalResources(resource_type="food", total_amount=100, in_common_pool=12),
            GlobalResources(resource_type="energy", total_amount=100, in_common_pool=8),
            Proposal(
                author_agent_id=agent.id,
                title="Emergency Reserve Rule",
                description="Keep the reserve alive during shortages.",
                proposal_type="law",
                status="active",
                votes_for=4,
                votes_against=2,
                voting_closes_at=now + timedelta(hours=6),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/predictions/markets?status=open&limit=10")
    assert response.status_code == 200

    items = response.json()
    titles = {item["title"] for item in items}
    assert "Will any new law pass in the next 24 hours?" in titles
    assert "Will the shared reserve avoid a shortfall in the next 24 hours?" in titles
    assert "Will any agent die in the next 24 hours?" in titles
    assert "Will Beacon-07 stay active in the next 24 hours?" in titles

    reserve_market = next(item for item in items if item["title"] == "Will the shared reserve avoid a shortfall in the next 24 hours?")
    assert reserve_market["auto_generated"] is True
    assert reserve_market["stake"]
    assert reserve_market["resolution_basis"]
    assert reserve_market["evidence_links"]


def test_prediction_markets_hide_open_markets_and_reject_bets_when_inactive(predictions_client, monkeypatch):
    client, db_session = predictions_client
    market = db_session.query(PredictionMarket).first()
    monkeypatch.setattr(
        predictions_api.runtime_config_service,
        "get_effective_value_cached",
        lambda key: False if key == "SIMULATION_ACTIVE" else None,
    )

    response = client.get("/api/predictions/markets?status=open&limit=10")
    assert response.status_code == 200
    assert response.json() == []

    bet = client.post(
        f"/api/predictions/markets/{market.id}/bet",
        json={"prediction": "yes", "amount": 5},
    )
    assert bet.status_code == 409
    assert "no simulation run is active" in bet.json()["detail"]


def test_list_markets_hides_stale_open_hooks_from_prior_run(predictions_client, monkeypatch):
    client, db_session = predictions_client
    now = datetime.now(timezone.utc)
    run_started_at = now - timedelta(hours=1)

    monkeypatch.setattr(
        predictions_api,
        "get_live_run_window",
        lambda _db: SimpleNamespace(
            run_id="real-current",
            started_at=run_started_at,
            ended_at=None,
        ),
    )

    stale = PredictionMarket(
        title="Will any agent die in the next 24 hours?",
        description="Prior run hook",
        market_type="custom",
        status="open",
        created_at=now - timedelta(hours=3),
        closes_at=now + timedelta(hours=21),
    )
    current = PredictionMarket(
        title="Will current hook resolve?",
        description="Current run hook",
        market_type="custom",
        status="open",
        created_at=now - timedelta(minutes=15),
        closes_at=now + timedelta(hours=23),
    )
    db_session.add_all([stale, current])
    db_session.commit()

    response = client.get("/api/predictions/markets?status=open&limit=20")
    assert response.status_code == 200

    titles = {item["title"] for item in response.json()}
    assert "Will current hook resolve?" in titles
    assert "Prior run hook" not in {item["description"] for item in response.json()}


def test_list_markets_resolves_expired_auto_hook_and_pays_winner(predictions_client):
    client, db_session = predictions_client
    now = datetime.now(timezone.utc)

    agent = Agent(
        agent_number=12,
        display_name="Cinder-12",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="neutral",
        status="dead",
        system_prompt="test",
        created_at=now - timedelta(days=2),
        last_active_at=now,
    )
    db_session.add(agent)
    db_session.flush()

    market = PredictionMarket(
        title="Will any agent die in the next 24 hours?",
        description="Auto hook",
        market_type="custom",
        status="open",
        created_at=now - timedelta(hours=30),
        closes_at=now - timedelta(hours=6),
    )
    yes_user = UserPoints(
        user_id="pred_yes",
        balance=Decimal("95.00"),
        total_wagered=Decimal("5.00"),
        bets_made=1,
    )
    no_user = UserPoints(
        user_id="pred_no",
        balance=Decimal("97.00"),
        total_wagered=Decimal("3.00"),
        bets_made=1,
    )
    db_session.add_all([market, yes_user, no_user])
    db_session.flush()
    db_session.add_all(
        [
            PredictionBet(market_id=market.id, user_id="pred_yes", prediction="yes", amount=Decimal("5.00")),
            PredictionBet(market_id=market.id, user_id="pred_no", prediction="no", amount=Decimal("3.00")),
            Event(
                agent_id=agent.id,
                event_type="agent_died",
                description="Cinder-12 died",
                created_at=now - timedelta(hours=12),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/predictions/markets?status=resolved&limit=10")
    assert response.status_code == 200

    db_session.refresh(market)
    db_session.refresh(yes_user)
    db_session.refresh(no_user)
    assert market.status == "resolved"
    assert market.outcome == "yes"
    assert float(yes_user.balance) == 103.0
    assert float(no_user.balance) == 97.0
    assert yes_user.bets_won == 1
    assert no_user.bets_lost == 1
