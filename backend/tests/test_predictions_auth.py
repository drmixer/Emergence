from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.predictions import PredictionMarket

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
