"""
Prediction Market API Router
Handles betting, market creation, and leaderboard endpoints.
"""

from dataclasses import dataclass
from typing import Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
import hmac
import hashlib
import uuid

from app.core.config import settings
from app.core.database import get_db
from app.core.time import ensure_utc, now_utc
from app.models.predictions import PredictionMarket, PredictionBet, UserPoints
from app.models.models import (
    Proposal,
    Agent,
    AgentRelationshipMemory,
    AgentInventory,
    Event,
    Law,
    Transaction,
    Vote,
)
from app.services.runtime_config import runtime_config_service
from app.services.survival_config import (
    active_energy_cost,
    active_food_cost,
    low_resource_warning_threshold,
)
from app.services.live_run_scope import get_live_run_window
from pydantic import BaseModel, Field

router = APIRouter()

# Constants
STARTING_BALANCE = Decimal("100.00")
MIN_BET = Decimal("1.00")
MAX_BET = Decimal("50.00")
PREDICTION_USER_COOKIE = "emergence_prediction_user"
PREDICTION_USER_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365
AUTO_MARKET_WINDOW_HOURS = 24
AUTO_MARKET_LAW_TITLE = "Will any new law pass in the next 24 hours?"
AUTO_MARKET_DEATH_TITLE = "Will any agent die in the next 24 hours?"
AUTO_MARKET_RESERVE_TITLE = (
    "Will the shared reserve avoid a shortfall in the next 24 hours?"
)
AUTO_MARKET_AID_REQUEST_SUFFIX = " ask another agent for aid in the next 24 hours?"
AUTO_MARKET_TRADE_RECEIVE_SUFFIX = " receive a trade in the next 24 hours?"
AUTO_MARKET_VOTE_PREFIX = "Will "
AUTO_MARKET_VOTE_MID = ' vote on "'
AUTO_MARKET_VOTE_SUFFIX = '" before it closes?'


@dataclass
class AgentPredictionFocus:
    agent: Agent
    resources: dict[str, float]
    score: float
    resource_pressure: bool
    reasons: list[str]


# ---------------------
# Pydantic Models
# ---------------------


class EvidenceLinkResponse(BaseModel):
    label: str
    href: str


class MarketResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    market_type: str
    status: str
    outcome: Optional[str]
    total_yes_amount: float
    total_no_amount: float
    yes_probability: float  # Calculated from betting amounts
    closes_at: str
    resolved_at: Optional[str]
    resolution_summary: Optional[str] = None
    resolution_event_id: Optional[int] = None
    resolution_evidence_href: Optional[str] = None
    created_at: str
    bet_count: int
    auto_generated: bool = False
    stake: Optional[str] = None
    why_this_matters: Optional[str] = None
    resolution_basis: Optional[str] = None
    evidence_links: List[EvidenceLinkResponse] = Field(default_factory=list)
    related_agent_number: Optional[int] = None
    related_agent_label: Optional[str] = None
    related_proposal_id: Optional[int] = None
    related_proposal_title: Optional[str] = None

    class Config:
        from_attributes = True


class PlaceBetRequest(BaseModel):
    prediction: str = Field(..., pattern="^(yes|no)$")
    amount: float = Field(..., gt=0, le=50)


class BetResponse(BaseModel):
    id: int
    market_id: int
    prediction: str
    amount: float
    won: Optional[bool]
    payout: Optional[float]
    created_at: str


class UserStatsResponse(BaseModel):
    user_id: str
    username: Optional[str]
    balance: float
    total_wagered: float
    total_won: float
    total_lost: float
    bets_made: int
    bets_won: int
    bets_lost: int
    win_rate: float
    current_streak: int
    best_streak: int
    rank: Optional[int]


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: Optional[str]
    balance: float
    win_rate: float
    bets_made: int
    bets_won: int
    profit: float  # total_won - total_lost


# ---------------------
# Helper Functions
# ---------------------


def _prediction_cookie_secret() -> str:
    secret = str(getattr(settings, "SECRET_KEY", "") or "").strip()
    return secret or "development-secret-key-change-in-production"


def _sign_prediction_user_id(user_id: str) -> str:
    return hmac.new(
        _prediction_cookie_secret().encode("utf-8"),
        user_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _serialize_prediction_cookie(user_id: str) -> str:
    return f"{user_id}.{_sign_prediction_user_id(user_id)}"


def _parse_prediction_cookie(raw_value: str | None) -> str | None:
    value = str(raw_value or "").strip()
    if not value or "." not in value:
        return None
    user_id, signature = value.rsplit(".", 1)
    if not user_id or not signature:
        return None
    expected = _sign_prediction_user_id(user_id)
    if not hmac.compare_digest(signature, expected):
        return None
    return user_id


def _issue_prediction_cookie(response: Response, *, user_id: str) -> None:
    response.set_cookie(
        key=PREDICTION_USER_COOKIE,
        value=_serialize_prediction_cookie(user_id),
        max_age=PREDICTION_USER_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=str(getattr(settings, "ENVIRONMENT", "")).lower() == "production",
        samesite="lax",
        path="/api/predictions",
    )


def resolve_prediction_user_id(request: Request, response: Response) -> str:
    """Return a stable, server-issued anonymous user id for prediction endpoints."""
    existing = _parse_prediction_cookie(request.cookies.get(PREDICTION_USER_COOKIE))
    if existing:
        return existing

    user_id = f"pred_{uuid.uuid4().hex[:24]}"
    _issue_prediction_cookie(response, user_id=user_id)
    return user_id


def get_or_create_user(db: Session, user_id: str) -> UserPoints:
    """Get user or create with starting balance."""
    user = db.query(UserPoints).filter(UserPoints.user_id == user_id).first()
    if not user:
        user = UserPoints(user_id=user_id, balance=STARTING_BALANCE)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def calculate_probability(yes_amount: Decimal, no_amount: Decimal) -> float:
    """Calculate implied probability from betting amounts."""
    total = yes_amount + no_amount
    if total == 0:
        return 0.5  # 50/50 if no bets
    return float(yes_amount / total)


def _agent_label(agent: Agent | None) -> str:
    if agent is None:
        return "Unknown Agent"
    if str(agent.display_name or "").strip():
        return str(agent.display_name).strip()
    return f"Agent #{int(agent.agent_number):02d}"


def _simulation_active() -> bool:
    return bool(runtime_config_service.get_effective_value_cached("SIMULATION_ACTIVE"))


def _active_run_started_at(db: Session) -> datetime | None:
    if not _simulation_active():
        return None
    run_window = get_live_run_window(db)
    return ensure_utc(run_window.started_at)


def _agent_market_title(agent: Agent) -> str:
    return f"Will {_agent_label(agent)} stay active in the next 24 hours?"


def _agent_aid_request_market_title(agent: Agent) -> str:
    return f"Will {_agent_label(agent)}{AUTO_MARKET_AID_REQUEST_SUFFIX}"


def _agent_trade_receive_market_title(agent: Agent) -> str:
    return f"Will {_agent_label(agent)}{AUTO_MARKET_TRADE_RECEIVE_SUFFIX}"


def _short_market_text(value: str | None, *, max_length: int = 80) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)].rstrip() + "..."


def _agent_vote_market_title(agent: Agent, proposal: Proposal) -> str:
    proposal_title = (
        _short_market_text(proposal.title, max_length=88)
        or f"Proposal #{int(proposal.id)}"
    )
    return f"Will {_agent_label(agent)}{AUTO_MARKET_VOTE_MID}{proposal_title}{AUTO_MARKET_VOTE_SUFFIX}"


def _is_agent_aid_request_market(market: PredictionMarket) -> bool:
    return bool(
        market.market_type == "custom"
        and market.related_agent_id is not None
        and str(market.title or "").strip().endswith(AUTO_MARKET_AID_REQUEST_SUFFIX)
    )


def _is_agent_trade_receive_market(market: PredictionMarket) -> bool:
    return bool(
        market.market_type == "custom"
        and market.related_agent_id is not None
        and str(market.title or "").strip().endswith(AUTO_MARKET_TRADE_RECEIVE_SUFFIX)
    )


def _is_agent_vote_market(market: PredictionMarket) -> bool:
    title = str(market.title or "").strip()
    return bool(
        market.market_type == "proposal_pass"
        and market.related_agent_id is not None
        and market.related_proposal_id is not None
        and title.startswith(AUTO_MARKET_VOTE_PREFIX)
        and AUTO_MARKET_VOTE_MID in title
        and title.endswith(AUTO_MARKET_VOTE_SUFFIX)
    )


def _is_auto_market(market: PredictionMarket) -> bool:
    title = str(market.title or "").strip()
    if title in {
        AUTO_MARKET_LAW_TITLE,
        AUTO_MARKET_DEATH_TITLE,
        AUTO_MARKET_RESERVE_TITLE,
    }:
        return True
    if (
        _is_agent_aid_request_market(market)
        or _is_agent_trade_receive_market(market)
        or _is_agent_vote_market(market)
    ):
        return True
    return bool(
        market.market_type == "agent_dormant"
        and market.related_agent_id is not None
        and title.endswith("stay active in the next 24 hours?")
    )


def _agent_resource_map(
    db: Session, *, agent_ids: list[int]
) -> dict[int, dict[str, float]]:
    if not agent_ids:
        return {}
    rows = db.query(AgentInventory).filter(AgentInventory.agent_id.in_(agent_ids)).all()
    by_agent: dict[int, dict[str, float]] = {}
    for row in rows:
        resource_map = by_agent.setdefault(int(row.agent_id), {})
        resource_map[str(row.resource_type)] = float(row.quantity or 0)
    return by_agent


def _select_most_at_risk_agent(db: Session) -> tuple[Agent | None, dict[str, float]]:
    agents = (
        db.query(Agent)
        .filter(Agent.status == "active")
        .order_by(Agent.agent_number.asc())
        .all()
    )
    if not agents:
        return None, {}

    resources_by_agent = _agent_resource_map(
        db, agent_ids=[int(agent.id) for agent in agents]
    )
    food_floor_raw = active_food_cost()
    energy_floor_raw = active_energy_cost()
    low_food_raw = low_resource_warning_threshold(food_floor_raw)
    low_energy_raw = low_resource_warning_threshold(energy_floor_raw)
    food_floor = float(food_floor_raw)
    energy_floor = float(energy_floor_raw)
    low_food = float(low_food_raw)
    low_energy = float(low_energy_raw)

    ranked: list[tuple[int, float, float, Agent, dict[str, float]]] = []
    for agent in agents:
        resources = resources_by_agent.get(int(agent.id), {})
        food = float(resources.get("food", 0.0))
        energy = float(resources.get("energy", 0.0))
        severity = 0
        if food < food_floor or energy < energy_floor:
            severity = 2
        elif food < low_food or energy < low_energy:
            severity = 1
        if severity <= 0:
            continue
        deficit = max(0.0, food_floor - food) + max(0.0, energy_floor - energy)
        remaining = food + energy
        ranked.append(
            (severity, deficit, remaining, agent, {"food": food, "energy": energy})
        )

    if not ranked:
        return None, {}

    ranked.sort(
        key=lambda item: (-item[0], -item[1], item[2], int(item[3].agent_number))
    )
    _, _, _, agent, resources = ranked[0]
    return agent, resources


def _resource_pressure_profile(
    resources: dict[str, float],
) -> tuple[float, bool, list[str]]:
    food_floor = float(active_food_cost())
    energy_floor = float(active_energy_cost())
    low_food = float(low_resource_warning_threshold(food_floor))
    low_energy = float(low_resource_warning_threshold(energy_floor))
    food = float(resources.get("food", 0.0))
    energy = float(resources.get("energy", 0.0))

    score = 0.0
    reasons: list[str] = []
    resource_pressure = False
    if food < food_floor:
        score += 40.0 + max(0.0, food_floor - food) * 10.0
        reasons.append("below the active food floor")
        resource_pressure = True
    elif food < low_food:
        score += 18.0 + max(0.0, low_food - food) * 4.0
        reasons.append("near the low-food warning line")
        resource_pressure = True

    if energy < energy_floor:
        score += 40.0 + max(0.0, energy_floor - energy) * 10.0
        reasons.append("below the active energy floor")
        resource_pressure = True
    elif energy < low_energy:
        score += 18.0 + max(0.0, low_energy - energy) * 4.0
        reasons.append("near the low-energy warning line")
        resource_pressure = True

    return score, resource_pressure, reasons


def _agent_event_counts(
    db: Session,
    *,
    agent: Agent,
    since: datetime | None,
    event_types: tuple[str, ...],
) -> dict[str, int]:
    query = db.query(Event).filter(
        Event.agent_id == int(agent.id), Event.event_type.in_(event_types)
    )
    if since is not None:
        query = query.filter(Event.created_at >= since)
    rows = (
        query.with_entities(Event.event_type, func.count(Event.id))
        .group_by(Event.event_type)
        .all()
    )
    return {str(event_type): int(count or 0) for event_type, count in rows}


def _relationship_tension_score(
    db: Session, *, agent: Agent, since: datetime | None
) -> tuple[float, list[str]]:
    query = db.query(AgentRelationshipMemory).filter(
        AgentRelationshipMemory.agent_id == int(agent.id)
    )
    if since is not None:
        query = query.filter(AgentRelationshipMemory.last_interaction_at >= since)

    score = 0.0
    totals = {
        "refusals": 0,
        "accusations": 0,
        "contests": 0,
        "oppositions": 0,
        "trades": 0,
    }
    for row in query.all():
        refusals = int(row.aid_refusals_received_from_other_count or 0) + int(
            row.aid_refusals_made_to_other_count or 0
        )
        accusations = int(row.accusations_received_from_other_count or 0) + int(
            row.accusations_made_against_other_count or 0
        )
        contests = int(row.proposal_contests_received_from_other_count or 0) + int(
            row.proposal_contests_made_against_other_count or 0
        )
        oppositions = int(row.proposal_oppositions_from_other_count or 0) + int(
            row.proposal_oppositions_against_other_count or 0
        )
        trades = int(row.trade_received_from_other_count or 0) + int(
            row.trade_sent_to_other_count or 0
        )
        totals["refusals"] += refusals
        totals["accusations"] += accusations
        totals["contests"] += contests
        totals["oppositions"] += oppositions
        totals["trades"] += trades
        score += refusals * 14.0
        score += accusations * 12.0
        score += contests * 12.0
        score += oppositions * 8.0
        score += trades * 3.0

    reasons: list[str] = []
    if totals["refusals"] > 0:
        reasons.append(f"{totals['refusals']} recent aid refusal(s)")
    if totals["accusations"] > 0:
        reasons.append(f"{totals['accusations']} accusation tie(s)")
    if totals["contests"] > 0:
        reasons.append(f"{totals['contests']} proposal contest(s)")
    if totals["oppositions"] > 0:
        reasons.append(f"{totals['oppositions']} opposed proposal tie(s)")
    if totals["trades"] > 0:
        reasons.append(f"{totals['trades']} trade tie(s)")
    return score, reasons


def _agent_prediction_focus_score(
    db: Session,
    *,
    agent: Agent,
    resources: dict[str, float],
    run_started_at: datetime | None,
) -> AgentPredictionFocus | None:
    score, resource_pressure, reasons = _resource_pressure_profile(resources)

    social_counts = _agent_event_counts(
        db,
        agent=agent,
        since=run_started_at,
        event_types=(
            "request_aid",
            "aid_refusal_received",
            "accusation_received",
            "proposal_contested_received",
            "public_accusation",
            "refuse_aid",
            "contest_proposal",
            "trade",
            "create_proposal",
        ),
    )
    incoming_conflict = sum(
        int(social_counts.get(event_type, 0))
        for event_type in (
            "aid_refusal_received",
            "accusation_received",
            "proposal_contested_received",
        )
    )
    outgoing_conflict = sum(
        int(social_counts.get(event_type, 0))
        for event_type in ("public_accusation", "refuse_aid", "contest_proposal")
    )
    aid_requests = int(social_counts.get("request_aid", 0))
    trades = int(social_counts.get("trade", 0))
    proposals = int(social_counts.get("create_proposal", 0))

    if incoming_conflict > 0:
        score += incoming_conflict * 18.0
        reasons.append(f"{incoming_conflict} incoming conflict signal(s)")
    if outgoing_conflict > 0:
        score += outgoing_conflict * 14.0
        reasons.append(f"{outgoing_conflict} public conflict action(s)")
    if aid_requests > 0:
        score += aid_requests * 10.0
        reasons.append(f"{aid_requests} recent aid request(s)")
    if trades > 0:
        score += trades * 4.0
        reasons.append(f"{trades} recent trade(s)")
    if proposals > 0:
        score += proposals * 6.0
        reasons.append(f"{proposals} recent proposal(s)")

    relationship_score, relationship_reasons = _relationship_tension_score(
        db, agent=agent, since=run_started_at
    )
    score += relationship_score
    reasons.extend(relationship_reasons)

    if score <= 0:
        return None
    return AgentPredictionFocus(
        agent=agent,
        resources=resources,
        score=score,
        resource_pressure=resource_pressure,
        reasons=reasons[:5],
    )


def _select_prediction_focus_agent(
    db: Session, *, run_started_at: datetime | None
) -> AgentPredictionFocus | None:
    agents = (
        db.query(Agent)
        .filter(Agent.status == "active")
        .order_by(Agent.agent_number.asc())
        .all()
    )
    if not agents:
        return None

    resources_by_agent = _agent_resource_map(
        db, agent_ids=[int(agent.id) for agent in agents]
    )
    profiles: list[AgentPredictionFocus] = []
    for agent in agents:
        profile = _agent_prediction_focus_score(
            db,
            agent=agent,
            resources=resources_by_agent.get(int(agent.id), {}),
            run_started_at=run_started_at,
        )
        if profile is not None:
            profiles.append(profile)
    if not profiles:
        return None

    profiles.sort(
        key=lambda profile: (
            -profile.score,
            int(profile.agent.agent_number),
        )
    )
    return profiles[0]


def _resources_context(resources: dict[str, float]) -> str:
    return (
        f"{float(resources.get('food', 0.0)):.2f} food and "
        f"{float(resources.get('energy', 0.0)):.2f} energy"
    )


def _agent_recent_action_counts(
    db: Session, *, agent: Agent, since: datetime | None
) -> dict[str, int]:
    query = db.query(Event).filter(Event.agent_id == int(agent.id))
    if since is not None:
        query = query.filter(Event.created_at >= since)
    rows = (
        query.filter(
            Event.event_type.in_(
                (
                    "request_aid",
                    "trade",
                    "vote",
                    "create_proposal",
                    "work",
                    "became_dormant",
                )
            )
        )
        .with_entities(Event.event_type, func.count(Event.id))
        .group_by(Event.event_type)
        .all()
    )
    return {str(event_type): int(count or 0) for event_type, count in rows}


def _agent_context_sentence(
    db: Session,
    *,
    agent: Agent,
    resources: dict[str, float],
    run_started_at: datetime | None,
    tension_reasons: list[str] | None = None,
) -> str:
    counts = _agent_recent_action_counts(db, agent=agent, since=run_started_at)
    recent_bits: list[str] = []
    if int(counts.get("request_aid", 0)) > 0:
        recent_bits.append(f"{int(counts.get('request_aid', 0))} aid request(s)")
    if int(counts.get("trade", 0)) > 0:
        recent_bits.append(f"{int(counts.get('trade', 0))} trade(s)")
    if int(counts.get("vote", 0)) > 0:
        recent_bits.append(f"{int(counts.get('vote', 0))} vote(s)")
    if int(counts.get("create_proposal", 0)) > 0:
        recent_bits.append(f"{int(counts.get('create_proposal', 0))} proposal(s)")

    context = f"{_agent_label(agent)} currently has {_resources_context(resources)}."
    if recent_bits:
        context += f" This run, they have logged {', '.join(recent_bits)}."
    if tension_reasons:
        context += f" Watch reason: {', '.join(tension_reasons[:3])}."
    return context


def _select_vote_watch_pair(
    db: Session,
    *,
    preferred_agent: Agent | None,
    run_started_at: datetime | None,
) -> tuple[Agent | None, Proposal | None]:
    proposals_query = db.query(Proposal).filter(Proposal.status == "active")
    if run_started_at is not None:
        proposals_query = proposals_query.filter(Proposal.created_at >= run_started_at)
    proposals = (
        proposals_query.order_by(
            Proposal.voting_closes_at.asc(),
            Proposal.created_at.desc(),
            Proposal.id.desc(),
        )
        .limit(10)
        .all()
    )
    if not proposals:
        return None, None

    active_agents = (
        db.query(Agent)
        .filter(Agent.status == "active")
        .order_by(Agent.agent_number.asc())
        .all()
    )
    if not active_agents:
        return None, None

    def has_voted(agent: Agent, proposal: Proposal) -> bool:
        return bool(
            db.query(Vote.id)
            .filter(
                Vote.agent_id == int(agent.id), Vote.proposal_id == int(proposal.id)
            )
            .first()
        )

    def candidate_for(proposal: Proposal) -> Agent | None:
        if (
            preferred_agent is not None
            and int(preferred_agent.id) != int(proposal.author_agent_id)
            and not has_voted(preferred_agent, proposal)
        ):
            return preferred_agent
        for agent in active_agents:
            if int(agent.id) == int(proposal.author_agent_id):
                continue
            if not has_voted(agent, proposal):
                return agent
        return None

    for proposal in proposals:
        agent = candidate_for(proposal)
        if agent is not None:
            return agent, proposal
    return None, None


def _prediction_evidence_links(*links: tuple[str, str]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for label, href in links:
        clean_label = str(label or "").strip()
        clean_href = str(href or "").strip()
        if not clean_label or not clean_href:
            continue
        key = (clean_label, clean_href)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"label": clean_label, "href": clean_href})
    return deduped


def _auto_market_payloads(db: Session) -> list[dict[str, Any]]:
    now_value = now_utc()
    run_started_at = _active_run_started_at(db)
    payloads: list[dict[str, Any]] = []

    focus = _select_prediction_focus_agent(db, run_started_at=run_started_at)
    if focus is None:
        at_risk_agent, resources = _select_most_at_risk_agent(db)
        if at_risk_agent is not None:
            focus = AgentPredictionFocus(
                agent=at_risk_agent,
                resources=resources,
                score=0.0,
                resource_pressure=True,
                reasons=[],
            )

    if focus is not None and focus.resource_pressure:
        at_risk_agent = focus.agent
        agent_context = _agent_context_sentence(
            db,
            agent=at_risk_agent,
            resources=focus.resources,
            run_started_at=run_started_at,
            tension_reasons=focus.reasons,
        )
        payloads.append(
            {
                "title": _agent_aid_request_market_title(at_risk_agent),
                "description": agent_context,
                "market_type": "custom",
                "related_agent_id": int(at_risk_agent.id),
                "stake": "Their next move can show whether survival pressure becomes a social request or stays private.",
                "why_this_matters": "This hook follows a specific agent action, not a run-wide mechanic.",
                "resolution_basis": "Settles YES if this agent records a request_aid action before the market closes.",
                "evidence_links": _prediction_evidence_links(
                    ("Agent Detail", f"/agents/{int(at_risk_agent.agent_number)}"),
                    ("Messages", "/messages?tab=direct"),
                ),
                "closes_at": now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS),
            }
        )
        payloads.append(
            {
                "title": _agent_trade_receive_market_title(at_risk_agent),
                "description": agent_context,
                "market_type": "custom",
                "related_agent_id": int(at_risk_agent.id),
                "stake": "A trade would turn this agent's pressure into a visible relationship between agents.",
                "why_this_matters": "This hook tracks whether another agent materially responds before the pressure resolves.",
                "resolution_basis": "Settles YES if this agent receives a trade before the market closes.",
                "evidence_links": _prediction_evidence_links(
                    ("Agent Detail", f"/agents/{int(at_risk_agent.agent_number)}"),
                    ("Resources", "/resources"),
                ),
                "closes_at": now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS),
            }
        )

    vote_agent, vote_proposal = _select_vote_watch_pair(
        db,
        preferred_agent=focus.agent if focus is not None else None,
        run_started_at=run_started_at,
    )
    if vote_agent is not None and vote_proposal is not None:
        resources_by_agent = _agent_resource_map(db, agent_ids=[int(vote_agent.id)])
        vote_resources = resources_by_agent.get(int(vote_agent.id), {})
        closes_at = ensure_utc(vote_proposal.voting_closes_at) or (
            now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS)
        )
        closes_at = min(
            closes_at, now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS)
        )
        payloads.append(
            {
                "title": _agent_vote_market_title(vote_agent, vote_proposal),
                "description": (
                    f'{_agent_label(vote_agent)} has not voted on "{_short_market_text(vote_proposal.title)}" yet. '
                    f"They currently have {_resources_context(vote_resources)}."
                ),
                "market_type": "proposal_pass",
                "related_agent_id": int(vote_agent.id),
                "related_proposal_id": int(vote_proposal.id),
                "stake": "A vote turns this agent's position into a visible public commitment.",
                "why_this_matters": "This hook follows whether a named agent enters the decision rather than whether the whole run passes a law.",
                "resolution_basis": "Settles YES if this agent casts any vote on the named proposal before the market closes.",
                "evidence_links": _prediction_evidence_links(
                    ("Proposal", f"/proposals/{int(vote_proposal.id)}"),
                    ("Agent Detail", f"/agents/{int(vote_agent.agent_number)}"),
                ),
                "closes_at": closes_at,
            }
        )

    return payloads


def _find_open_auto_market(
    db: Session, payload: dict[str, Any]
) -> PredictionMarket | None:
    title = str(payload.get("title") or "").strip()
    query = db.query(PredictionMarket).filter(PredictionMarket.status == "open")
    run_started_at = _active_run_started_at(db)
    if run_started_at is not None:
        query = query.filter(PredictionMarket.created_at >= run_started_at)
    if (
        str(payload.get("market_type") or "") == "agent_dormant"
        and payload.get("related_agent_id") is not None
    ):
        return (
            query.filter(
                PredictionMarket.market_type == "agent_dormant",
                PredictionMarket.related_agent_id == int(payload["related_agent_id"]),
            )
            .order_by(PredictionMarket.created_at.desc(), PredictionMarket.id.desc())
            .first()
        )
    return (
        query.filter(PredictionMarket.title == title)
        .order_by(PredictionMarket.created_at.desc(), PredictionMarket.id.desc())
        .first()
    )


def _resolve_user_streak(user: UserPoints, *, won: bool) -> None:
    current = int(user.current_streak or 0)
    best = int(user.best_streak or 0)
    if won:
        user.current_streak = current + 1 if current > 0 else 1
        user.best_streak = max(best, int(user.current_streak or 0))
    else:
        user.current_streak = current - 1 if current < 0 else -1
        user.best_streak = max(best, 0)


def _resolve_market_bets(
    db: Session,
    *,
    market: PredictionMarket,
    outcome: str,
    resolved_at: datetime,
    resolution_summary: str | None = None,
    resolution_event_id: int | None = None,
) -> None:
    market.status = "resolved"
    market.outcome = str(outcome or "").strip().lower()
    market.resolved_at = resolved_at
    if resolution_summary is not None:
        market.resolution_summary = str(resolution_summary or "").strip() or None
    if resolution_event_id is not None:
        market.resolution_event_id = int(resolution_event_id)

    bets = (
        db.query(PredictionBet)
        .filter(PredictionBet.market_id == market.id)
        .order_by(PredictionBet.id.asc())
        .all()
    )
    total_pool = sum((Decimal(str(bet.amount or 0)) for bet in bets), Decimal("0"))
    winning_pool = sum(
        (
            Decimal(str(bet.amount or 0))
            for bet in bets
            if str(bet.prediction or "").strip().lower() == market.outcome
        ),
        Decimal("0"),
    )
    user_cache: dict[str, UserPoints] = {}
    for bet in bets:
        user = user_cache.get(str(bet.user_id or ""))
        if user is None:
            user = (
                db.query(UserPoints).filter(UserPoints.user_id == bet.user_id).first()
            )
            if user is None:
                user = get_or_create_user(db, str(bet.user_id or ""))
            user_cache[str(bet.user_id or "")] = user

        won = str(bet.prediction or "").strip().lower() == market.outcome
        bet.won = won
        if won and winning_pool > 0:
            payout = (total_pool * Decimal(str(bet.amount or 0))) / winning_pool
        else:
            payout = Decimal("0")
        bet.payout = payout

        if won:
            user.balance += payout
            user.total_won += payout
            user.bets_won += 1
        else:
            user.total_lost += Decimal(str(bet.amount or 0))
            user.bets_lost += 1
        _resolve_user_streak(user, won=won)


def _event_metadata(event: Event) -> dict[str, Any]:
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    return metadata if isinstance(metadata, dict) else {}


def _event_action(event: Event) -> dict[str, Any]:
    action = _event_metadata(event).get("action")
    return action if isinstance(action, dict) else {}


def _agent_requested_aid(
    db: Session, *, agent_id: int, window_start: datetime, window_end: datetime
) -> bool:
    events = (
        db.query(Event)
        .filter(
            Event.event_type.in_(("request_aid", "aid_request_received")),
            Event.created_at >= window_start,
            Event.created_at <= window_end,
        )
        .all()
    )
    for event in events:
        if event.event_type == "request_aid" and int(event.agent_id or 0) == int(
            agent_id
        ):
            return True
        if event.event_type == "aid_request_received":
            metadata = _event_metadata(event)
            if int(metadata.get("requesting_agent_id") or 0) == int(agent_id):
                return True
    return False


def _agent_received_trade(
    db: Session, *, agent: Agent, window_start: datetime, window_end: datetime
) -> bool:
    transaction = (
        db.query(Transaction.id)
        .filter(
            Transaction.transaction_type == "trade",
            Transaction.to_agent_id == int(agent.id),
            Transaction.created_at >= window_start,
            Transaction.created_at <= window_end,
        )
        .first()
    )
    if transaction is not None:
        return True

    events = (
        db.query(Event)
        .filter(
            Event.event_type == "trade",
            Event.created_at >= window_start,
            Event.created_at <= window_end,
        )
        .all()
    )
    for event in events:
        action = _event_action(event)
        if int(action.get("recipient_agent_id") or 0) == int(agent.agent_number):
            return True
    return False


def _agent_voted_on_proposal(
    db: Session,
    *,
    agent_id: int,
    proposal_id: int,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    vote = (
        db.query(Vote.id)
        .filter(
            Vote.agent_id == int(agent_id),
            Vote.proposal_id == int(proposal_id),
            Vote.created_at >= window_start,
            Vote.created_at <= window_end,
        )
        .first()
    )
    return vote is not None


def _first_event(
    db: Session,
    *,
    event_types: tuple[str, ...],
    window_start: datetime,
    window_end: datetime,
    agent_id: int | None = None,
) -> Event | None:
    query = db.query(Event).filter(
        Event.event_type.in_(event_types),
        Event.created_at >= window_start,
        Event.created_at <= window_end,
    )
    if agent_id is not None:
        query = query.filter(Event.agent_id == int(agent_id))
    return query.order_by(Event.created_at.asc(), Event.id.asc()).first()


def _matching_aid_request_event(
    db: Session,
    *,
    agent_id: int,
    window_start: datetime,
    window_end: datetime,
) -> Event | None:
    events = (
        db.query(Event)
        .filter(
            Event.event_type.in_(("request_aid", "aid_request_received")),
            Event.created_at >= window_start,
            Event.created_at <= window_end,
        )
        .order_by(Event.created_at.asc(), Event.id.asc())
        .all()
    )
    for event in events:
        if event.event_type == "request_aid" and int(event.agent_id or 0) == int(
            agent_id
        ):
            return event
        if event.event_type == "aid_request_received":
            metadata = _event_metadata(event)
            if int(metadata.get("requesting_agent_id") or 0) == int(agent_id):
                return event
    return None


def _matching_trade_receive_event(
    db: Session,
    *,
    agent: Agent,
    window_start: datetime,
    window_end: datetime,
) -> Event | None:
    events = (
        db.query(Event)
        .filter(
            Event.event_type == "trade",
            Event.created_at >= window_start,
            Event.created_at <= window_end,
        )
        .order_by(Event.created_at.asc(), Event.id.asc())
        .all()
    )
    for event in events:
        action = _event_action(event)
        if int(action.get("recipient_agent_id") or 0) == int(agent.agent_number):
            return event
    return None


def _matching_vote_event(
    db: Session,
    *,
    agent_id: int,
    proposal_id: int,
    window_start: datetime,
    window_end: datetime,
) -> Event | None:
    events = (
        db.query(Event)
        .filter(
            Event.event_type == "vote",
            Event.agent_id == int(agent_id),
            Event.created_at >= window_start,
            Event.created_at <= window_end,
        )
        .order_by(Event.created_at.asc(), Event.id.asc())
        .all()
    )
    for event in events:
        action = _event_action(event)
        if int(action.get("proposal_id") or 0) == int(proposal_id):
            return event
    return None


def _resolution_receipt(
    db: Session,
    *,
    market: PredictionMarket,
    outcome: str,
    window_start: datetime,
    window_end: datetime,
) -> tuple[str | None, int | None]:
    clean_outcome = str(outcome or "").strip().lower()
    title = str(market.title or "").strip()

    if title == AUTO_MARKET_LAW_TITLE:
        law = (
            db.query(Law)
            .filter(Law.passed_at >= window_start, Law.passed_at <= window_end)
            .order_by(Law.passed_at.asc(), Law.id.asc())
            .first()
        )
        event = _first_event(
            db,
            event_types=("law_passed",),
            window_start=window_start,
            window_end=window_end,
        )
        if clean_outcome == "yes" and law is not None:
            return (
                f'Resolved YES when the law "{_short_market_text(law.title, max_length=120)}" passed.',
                int(event.id) if event else None,
            )
        return "Resolved NO because no new law passed before close.", None

    if title == AUTO_MARKET_DEATH_TITLE:
        event = _first_event(
            db,
            event_types=("agent_died",),
            window_start=window_start,
            window_end=window_end,
        )
        if clean_outcome == "yes" and event is not None:
            return f"Resolved YES: {event.description}", int(event.id)
        return "Resolved NO because no agent death was recorded before close.", None

    if title == AUTO_MARKET_RESERVE_TITLE:
        event = _first_event(
            db,
            event_types=("reserve_shortfall",),
            window_start=window_start,
            window_end=window_end,
        )
        if clean_outcome == "no" and event is not None:
            return f"Resolved NO: {event.description}", int(event.id)
        return (
            "Resolved YES because no reserve shortfall was recorded before close.",
            None,
        )

    if market.market_type == "agent_dormant" and market.related_agent_id is not None:
        agent = db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        event = _first_event(
            db,
            event_types=("became_dormant", "agent_died"),
            window_start=window_start,
            window_end=window_end,
            agent_id=int(market.related_agent_id),
        )
        label = _agent_label(agent)
        if clean_outcome == "no" and event is not None:
            return f"Resolved NO: {event.description}", int(event.id)
        if clean_outcome == "yes":
            return f"Resolved YES because {label} stayed active through close.", None
        return f"Resolved NO because {label} was no longer active at close.", (
            int(event.id) if event else None
        )

    if _is_agent_aid_request_market(market):
        agent = db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        label = _agent_label(agent)
        event = _matching_aid_request_event(
            db,
            agent_id=int(market.related_agent_id),
            window_start=window_start,
            window_end=window_end,
        )
        if clean_outcome == "yes" and event is not None:
            return f"Resolved YES: {event.description}", int(event.id)
        return (
            f"Resolved NO because {label} did not ask another agent for aid before close.",
            None,
        )

    if _is_agent_trade_receive_market(market):
        agent = db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        if agent is None:
            return "Resolved NO because the tracked agent no longer exists.", None
        event = _matching_trade_receive_event(
            db,
            agent=agent,
            window_start=window_start,
            window_end=window_end,
        )
        if clean_outcome == "yes" and event is not None:
            return f"Resolved YES: {event.description}", int(event.id)
        transaction = (
            db.query(Transaction)
            .filter(
                Transaction.transaction_type == "trade",
                Transaction.to_agent_id == int(agent.id),
                Transaction.created_at >= window_start,
                Transaction.created_at <= window_end,
            )
            .order_by(Transaction.created_at.asc(), Transaction.id.asc())
            .first()
        )
        if clean_outcome == "yes" and transaction is not None:
            return (
                f"Resolved YES when {_agent_label(agent)} received "
                f"{float(transaction.amount or 0):.2f} {transaction.resource_type} by trade.",
                None,
            )
        return (
            f"Resolved NO because {_agent_label(agent)} did not receive a trade before close.",
            None,
        )

    if _is_agent_vote_market(market):
        agent = db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        proposal = (
            db.query(Proposal)
            .filter(Proposal.id == int(market.related_proposal_id))
            .first()
        )
        label = _agent_label(agent)
        proposal_title = (
            _short_market_text(
                proposal.title if proposal is not None else None, max_length=120
            )
            or "the proposal"
        )
        vote = (
            db.query(Vote)
            .filter(
                Vote.agent_id == int(market.related_agent_id),
                Vote.proposal_id == int(market.related_proposal_id),
                Vote.created_at >= window_start,
                Vote.created_at <= window_end,
            )
            .order_by(Vote.created_at.asc(), Vote.id.asc())
            .first()
        )
        event = _matching_vote_event(
            db,
            agent_id=int(market.related_agent_id),
            proposal_id=int(market.related_proposal_id),
            window_start=window_start,
            window_end=window_end,
        )
        if clean_outcome == "yes" and vote is not None:
            return (
                f"Resolved YES when {label} voted {str(vote.vote or '').upper()} on \"{proposal_title}\".",
                int(event.id) if event else None,
            )
        return (
            f'Resolved NO because {label} did not vote on "{proposal_title}" before close.',
            None,
        )

    return None, None


def _resolve_auto_market_outcome(db: Session, market: PredictionMarket) -> str | None:
    window_start = ensure_utc(market.created_at) or now_utc()
    window_end = ensure_utc(market.closes_at) or now_utc()
    title = str(market.title or "").strip()

    if title == AUTO_MARKET_LAW_TITLE:
        law_count = (
            db.query(func.count(Law.id))
            .filter(Law.passed_at >= window_start, Law.passed_at <= window_end)
            .scalar()
        ) or 0
        return "yes" if int(law_count) > 0 else "no"

    if title == AUTO_MARKET_DEATH_TITLE:
        deaths = (
            db.query(func.count(Event.id))
            .filter(
                Event.event_type == "agent_died",
                Event.created_at >= window_start,
                Event.created_at <= window_end,
            )
            .scalar()
        ) or 0
        return "yes" if int(deaths) > 0 else "no"

    if title == AUTO_MARKET_RESERVE_TITLE:
        shortfalls = (
            db.query(func.count(Event.id))
            .filter(
                Event.event_type == "reserve_shortfall",
                Event.created_at >= window_start,
                Event.created_at <= window_end,
            )
            .scalar()
        ) or 0
        return "yes" if int(shortfalls) == 0 else "no"

    if market.market_type == "agent_dormant" and market.related_agent_id is not None:
        dropout_events = (
            db.query(func.count(Event.id))
            .filter(
                Event.agent_id == int(market.related_agent_id),
                Event.event_type.in_(("became_dormant", "agent_died")),
                Event.created_at >= window_start,
                Event.created_at <= window_end,
            )
            .scalar()
        ) or 0
        if int(dropout_events) > 0:
            return "no"
        agent = db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        if agent is None:
            return "no"
        return "yes" if str(agent.status or "") == "active" else "no"

    if _is_agent_aid_request_market(market):
        return (
            "yes"
            if _agent_requested_aid(
                db,
                agent_id=int(market.related_agent_id),
                window_start=window_start,
                window_end=window_end,
            )
            else "no"
        )

    if _is_agent_trade_receive_market(market):
        agent = db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        if agent is None:
            return "no"
        return (
            "yes"
            if _agent_received_trade(
                db,
                agent=agent,
                window_start=window_start,
                window_end=window_end,
            )
            else "no"
        )

    if _is_agent_vote_market(market):
        return (
            "yes"
            if _agent_voted_on_proposal(
                db,
                agent_id=int(market.related_agent_id),
                proposal_id=int(market.related_proposal_id),
                window_start=window_start,
                window_end=window_end,
            )
            else "no"
        )

    return None


def _resolve_auto_market_early_outcome(
    db: Session, market: PredictionMarket
) -> str | None:
    window_start = ensure_utc(market.created_at) or now_utc()
    window_end = ensure_utc(market.closes_at) or now_utc()
    title = str(market.title or "").strip()

    if title == AUTO_MARKET_LAW_TITLE:
        law_count = (
            db.query(func.count(Law.id))
            .filter(Law.passed_at >= window_start, Law.passed_at <= window_end)
            .scalar()
        ) or 0
        return "yes" if int(law_count) > 0 else None

    if title == AUTO_MARKET_DEATH_TITLE:
        deaths = (
            db.query(func.count(Event.id))
            .filter(
                Event.event_type == "agent_died",
                Event.created_at >= window_start,
                Event.created_at <= window_end,
            )
            .scalar()
        ) or 0
        return "yes" if int(deaths) > 0 else None

    if title == AUTO_MARKET_RESERVE_TITLE:
        shortfalls = (
            db.query(func.count(Event.id))
            .filter(
                Event.event_type == "reserve_shortfall",
                Event.created_at >= window_start,
                Event.created_at <= window_end,
            )
            .scalar()
        ) or 0
        return "no" if int(shortfalls) > 0 else None

    if market.market_type == "agent_dormant" and market.related_agent_id is not None:
        dropout_events = (
            db.query(func.count(Event.id))
            .filter(
                Event.agent_id == int(market.related_agent_id),
                Event.event_type.in_(("became_dormant", "agent_died")),
                Event.created_at >= window_start,
                Event.created_at <= window_end,
            )
            .scalar()
        ) or 0
        if int(dropout_events) > 0:
            return "no"
        agent = db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        if agent is not None and str(agent.status or "") != "active":
            return "no"

    if _is_agent_aid_request_market(market):
        return (
            "yes"
            if _agent_requested_aid(
                db,
                agent_id=int(market.related_agent_id),
                window_start=window_start,
                window_end=window_end,
            )
            else None
        )

    if _is_agent_trade_receive_market(market):
        agent = db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        if agent is None:
            return "no"
        return (
            "yes"
            if _agent_received_trade(
                db,
                agent=agent,
                window_start=window_start,
                window_end=window_end,
            )
            else None
        )

    if _is_agent_vote_market(market):
        return (
            "yes"
            if _agent_voted_on_proposal(
                db,
                agent_id=int(market.related_agent_id),
                proposal_id=int(market.related_proposal_id),
                window_start=window_start,
                window_end=window_end,
            )
            else None
        )

    return None


def _sync_auto_prediction_markets(db: Session) -> None:
    now_value = now_utc()
    changed = False

    open_markets = (
        db.query(PredictionMarket).filter(PredictionMarket.status == "open").all()
    )
    for market in open_markets:
        if not _is_auto_market(market):
            continue
        closes_at = ensure_utc(market.closes_at)
        if closes_at is None:
            continue
        if closes_at > now_value:
            outcome = _resolve_auto_market_early_outcome(db, market)
        else:
            outcome = _resolve_auto_market_outcome(db, market)
        if outcome not in {"yes", "no"}:
            continue
        window_start = ensure_utc(market.created_at) or now_value
        window_end = ensure_utc(market.closes_at) or now_value
        resolution_summary, resolution_event_id = _resolution_receipt(
            db,
            market=market,
            outcome=outcome,
            window_start=window_start,
            window_end=window_end,
        )
        _resolve_market_bets(
            db,
            market=market,
            outcome=outcome,
            resolved_at=now_value,
            resolution_summary=resolution_summary,
            resolution_event_id=resolution_event_id,
        )
        changed = True

    if _simulation_active():
        for payload in _auto_market_payloads(db):
            existing = _find_open_auto_market(db, payload)
            if existing is not None:
                continue
            market = PredictionMarket(
                title=str(payload.get("title") or "").strip(),
                description=str(payload.get("description") or "").strip() or None,
                market_type=str(payload.get("market_type") or "custom").strip(),
                status="open",
                related_proposal_id=payload.get("related_proposal_id"),
                related_agent_id=payload.get("related_agent_id"),
                closes_at=payload.get("closes_at")
                or (now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS)),
            )
            db.add(market)
            changed = True

    if changed:
        db.commit()


def _market_context(db: Session, market: PredictionMarket) -> dict[str, Any]:
    title = str(market.title or "").strip()
    related_agent = (
        db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        if market.related_agent_id is not None
        else None
    )
    related_proposal = (
        db.query(Proposal)
        .filter(Proposal.id == int(market.related_proposal_id))
        .first()
        if market.related_proposal_id is not None
        else None
    )
    resources_by_agent = (
        _agent_resource_map(db, agent_ids=[int(related_agent.id)])
        if related_agent is not None
        else {}
    )
    related_resources = (
        resources_by_agent.get(int(related_agent.id), {})
        if related_agent is not None
        else {}
    )

    for payload in _auto_market_payloads(db):
        if (
            title
            in {
                AUTO_MARKET_LAW_TITLE,
                AUTO_MARKET_DEATH_TITLE,
                AUTO_MARKET_RESERVE_TITLE,
            }
            and title == str(payload.get("title") or "").strip()
        ):
            return payload
        if (
            related_agent is not None
            and title == _agent_market_title(related_agent)
            and str(payload.get("title") or "").strip() == title
        ):
            payload = dict(payload)
            payload["description"] = (
                f"{_agent_label(related_agent)} currently holds {float(related_resources.get('food', 0.0)):.2f} food and "
                f"{float(related_resources.get('energy', 0.0)):.2f} energy."
            )
            return payload
    if related_agent is not None and _is_agent_aid_request_market(market):
        return {
            "title": title,
            "description": str(market.description or "").strip()
            or (
                _agent_context_sentence(
                    db,
                    agent=related_agent,
                    resources=related_resources,
                    run_started_at=_active_run_started_at(db),
                )
            ),
            "stake": "Their next move can show whether survival pressure becomes a social request or stays private.",
            "why_this_matters": "This hook follows a specific agent action, not a run-wide mechanic.",
            "resolution_basis": "Settles YES if this agent records a request_aid action before the market closes.",
            "evidence_links": _prediction_evidence_links(
                ("Agent Detail", f"/agents/{int(related_agent.agent_number)}"),
                ("Messages", "/messages?tab=direct"),
            ),
        }
    if related_agent is not None and _is_agent_trade_receive_market(market):
        return {
            "title": title,
            "description": str(market.description or "").strip()
            or (
                _agent_context_sentence(
                    db,
                    agent=related_agent,
                    resources=related_resources,
                    run_started_at=_active_run_started_at(db),
                )
            ),
            "stake": "A trade would turn this agent's pressure into a visible relationship between agents.",
            "why_this_matters": "This hook tracks whether another agent materially responds before the pressure resolves.",
            "resolution_basis": "Settles YES if this agent receives a trade before the market closes.",
            "evidence_links": _prediction_evidence_links(
                ("Agent Detail", f"/agents/{int(related_agent.agent_number)}"),
                ("Resources", "/resources"),
            ),
        }
    if (
        related_agent is not None
        and related_proposal is not None
        and _is_agent_vote_market(market)
    ):
        return {
            "title": title,
            "description": (
                f'{_agent_label(related_agent)} has not voted on "{_short_market_text(related_proposal.title)}" yet. '
                f"They currently have {_resources_context(related_resources)}."
            ),
            "stake": "A vote turns this agent's position into a visible public commitment.",
            "why_this_matters": "This hook follows whether a named agent enters the decision rather than whether the whole run passes a law.",
            "resolution_basis": "Settles YES if this agent casts any vote on the named proposal before the market closes.",
            "evidence_links": _prediction_evidence_links(
                ("Proposal", f"/proposals/{int(related_proposal.id)}"),
                ("Agent Detail", f"/agents/{int(related_agent.agent_number)}"),
            ),
        }
    if related_agent is not None and market.market_type == "agent_dormant":
        status = str(related_agent.status or "unknown").strip() or "unknown"
        return {
            "title": title,
            "description": (
                f"{_agent_label(related_agent)} is {status} and currently holds "
                f"{float(related_resources.get('food', 0.0)):.2f} food and "
                f"{float(related_resources.get('energy', 0.0)):.2f} energy."
            ),
            "stake": "This is a single-agent survival watch based on the current public state.",
            "why_this_matters": "If this agent drops into dormancy or dies, the turn is directly visible on the public record.",
            "resolution_basis": "Settles YES if the agent remains active and no dormancy/death event is recorded before close.",
            "evidence_links": _prediction_evidence_links(
                ("Agent Detail", f"/agents/{int(related_agent.agent_number)}"),
                ("All Agents", "/agents"),
            ),
        }
    return {
        "title": title,
        "description": str(market.description or "").strip() or None,
        "stake": None,
        "why_this_matters": None,
        "resolution_basis": None,
        "evidence_links": [],
    }


def _serialize_market(db: Session, market: PredictionMarket) -> MarketResponse:
    context = _market_context(db, market)
    related_agent = (
        db.query(Agent).filter(Agent.id == int(market.related_agent_id)).first()
        if market.related_agent_id is not None
        else None
    )
    related_proposal = (
        db.query(Proposal)
        .filter(Proposal.id == int(market.related_proposal_id))
        .first()
        if market.related_proposal_id is not None
        else None
    )
    return MarketResponse(
        id=market.id,
        title=market.title,
        description=context.get("description") or market.description,
        market_type=market.market_type,
        status=market.status,
        outcome=market.outcome,
        resolution_summary=str(market.resolution_summary or "").strip() or None,
        resolution_event_id=(
            int(market.resolution_event_id)
            if market.resolution_event_id is not None
            else None
        ),
        resolution_evidence_href=(
            f"/timeline?event={int(market.resolution_event_id)}"
            if market.resolution_event_id is not None
            else None
        ),
        total_yes_amount=float(market.total_yes_amount),
        total_no_amount=float(market.total_no_amount),
        yes_probability=calculate_probability(
            market.total_yes_amount, market.total_no_amount
        ),
        closes_at=ensure_utc(market.closes_at).isoformat() if market.closes_at else "",
        resolved_at=(
            ensure_utc(market.resolved_at).isoformat() if market.resolved_at else None
        ),
        created_at=(
            ensure_utc(market.created_at).isoformat() if market.created_at else ""
        ),
        bet_count=len(market.bets),
        auto_generated=_is_auto_market(market),
        stake=context.get("stake"),
        why_this_matters=context.get("why_this_matters"),
        resolution_basis=context.get("resolution_basis"),
        evidence_links=[
            EvidenceLinkResponse(**item)
            for item in list(context.get("evidence_links") or [])
        ],
        related_agent_number=(
            int(related_agent.agent_number) if related_agent is not None else None
        ),
        related_agent_label=(
            _agent_label(related_agent) if related_agent is not None else None
        ),
        related_proposal_id=(
            int(related_proposal.id) if related_proposal is not None else None
        ),
        related_proposal_title=(
            str(related_proposal.title or "").strip()
            if related_proposal is not None
            else None
        ),
    )


# ---------------------
# Market Endpoints
# ---------------------


@router.get("/markets", response_model=List[MarketResponse])
def list_markets(
    status: Optional[str] = None,
    market_type: Optional[str] = None,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """List all prediction markets with optional filters."""
    _sync_auto_prediction_markets(db)
    query = db.query(PredictionMarket)

    if not _simulation_active():
        query = query.filter(PredictionMarket.status != "open")
    else:
        run_started_at = _active_run_started_at(db)
        if run_started_at is not None:
            query = query.filter(
                or_(
                    PredictionMarket.status != "open",
                    PredictionMarket.created_at >= run_started_at,
                )
            )

    if status:
        query = query.filter(PredictionMarket.status == status)
    if market_type:
        query = query.filter(PredictionMarket.market_type == market_type)

    markets = query.order_by(desc(PredictionMarket.created_at)).limit(limit).all()

    return [_serialize_market(db, m) for m in markets]


@router.get("/markets/{market_id}", response_model=MarketResponse)
def get_market(market_id: int, db: Session = Depends(get_db)):
    """Get details of a specific market."""
    _sync_auto_prediction_markets(db)
    market = db.query(PredictionMarket).filter(PredictionMarket.id == market_id).first()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    return _serialize_market(db, market)


# ---------------------
# Betting Endpoints
# ---------------------


@router.post("/markets/{market_id}/bet", response_model=BetResponse)
def place_bet(
    market_id: int,
    bet_request: PlaceBetRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Place a bet on a prediction market."""
    _sync_auto_prediction_markets(db)
    if not _simulation_active():
        raise HTTPException(
            status_code=409,
            detail="Prediction markets are closed while no simulation run is active",
        )

    # Get market
    market = db.query(PredictionMarket).filter(PredictionMarket.id == market_id).first()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # Check market is open
    if market.status != "open":
        raise HTTPException(status_code=400, detail="Market is not open for betting")

    # Check deadline
    closes_at = ensure_utc(market.closes_at)
    if closes_at is None or now_utc() >= closes_at:
        raise HTTPException(
            status_code=400, detail="Betting has closed for this market"
        )

    # Get user
    user_id = resolve_prediction_user_id(request, response)
    user = get_or_create_user(db, user_id)

    # Validate bet amount
    bet_amount = Decimal(str(bet_request.amount))
    if bet_amount < MIN_BET:
        raise HTTPException(status_code=400, detail=f"Minimum bet is {MIN_BET} EP")
    if bet_amount > MAX_BET:
        raise HTTPException(status_code=400, detail=f"Maximum bet is {MAX_BET} EP")
    if bet_amount > user.balance:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Check if user has already bet on this market
    existing_bet = (
        db.query(PredictionBet)
        .filter(PredictionBet.market_id == market_id, PredictionBet.user_id == user_id)
        .first()
    )

    if existing_bet:
        raise HTTPException(
            status_code=400, detail="You have already placed a bet on this market"
        )

    # Create bet
    bet = PredictionBet(
        market_id=market_id,
        user_id=user_id,
        prediction=bet_request.prediction,
        amount=bet_amount,
    )
    db.add(bet)

    # Update user balance
    user.balance -= bet_amount
    user.total_wagered += bet_amount
    user.bets_made += 1

    # Update market totals
    if bet_request.prediction == "yes":
        market.total_yes_amount += bet_amount
    else:
        market.total_no_amount += bet_amount

    db.commit()
    db.refresh(bet)

    return BetResponse(
        id=bet.id,
        market_id=bet.market_id,
        prediction=bet.prediction,
        amount=float(bet.amount),
        won=bet.won,
        payout=float(bet.payout) if bet.payout else None,
        created_at=bet.created_at.isoformat() if bet.created_at else "",
    )


@router.get("/markets/{market_id}/bets", response_model=List[BetResponse])
def get_market_bets(
    market_id: int, request: Request, response: Response, db: Session = Depends(get_db)
):
    """Get user's bets on a specific market."""
    user_id = resolve_prediction_user_id(request, response)

    bets = (
        db.query(PredictionBet)
        .filter(PredictionBet.market_id == market_id, PredictionBet.user_id == user_id)
        .all()
    )

    return [
        BetResponse(
            id=b.id,
            market_id=b.market_id,
            prediction=b.prediction,
            amount=float(b.amount),
            won=b.won,
            payout=float(b.payout) if b.payout else None,
            created_at=b.created_at.isoformat() if b.created_at else "",
        )
        for b in bets
    ]


# ---------------------
# User Endpoints
# ---------------------


@router.get("/me", response_model=UserStatsResponse)
def get_my_stats(request: Request, response: Response, db: Session = Depends(get_db)):
    """Get current user's stats and balance."""
    user_id = resolve_prediction_user_id(request, response)
    user = get_or_create_user(db, user_id)

    # Calculate win rate
    win_rate = 0.0
    if user.bets_made > 0 and (user.bets_won + user.bets_lost) > 0:
        win_rate = user.bets_won / (user.bets_won + user.bets_lost) * 100

    # Calculate rank
    rank = (
        db.query(func.count(UserPoints.id))
        .filter(UserPoints.balance > user.balance)
        .scalar()
        + 1
    )

    return UserStatsResponse(
        user_id=user.user_id,
        username=user.username,
        balance=float(user.balance),
        total_wagered=float(user.total_wagered),
        total_won=float(user.total_won),
        total_lost=float(user.total_lost),
        bets_made=user.bets_made,
        bets_won=user.bets_won,
        bets_lost=user.bets_lost,
        win_rate=round(win_rate, 1),
        current_streak=user.current_streak,
        best_streak=user.best_streak,
        rank=rank,
    )


@router.get("/my-bets", response_model=List[BetResponse])
def get_my_bets(
    request: Request,
    response: Response,
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """Get current user's betting history."""
    user_id = resolve_prediction_user_id(request, response)

    query = db.query(PredictionBet).filter(PredictionBet.user_id == user_id)

    if status:
        query = query.join(PredictionMarket).filter(PredictionMarket.status == status)

    bets = query.order_by(desc(PredictionBet.created_at)).limit(limit).all()

    return [
        BetResponse(
            id=b.id,
            market_id=b.market_id,
            prediction=b.prediction,
            amount=float(b.amount),
            won=b.won,
            payout=float(b.payout) if b.payout else None,
            created_at=b.created_at.isoformat() if b.created_at else "",
        )
        for b in bets
    ]


@router.post("/set-username")
def set_username(
    username: str, request: Request, response: Response, db: Session = Depends(get_db)
):
    """Set display name for leaderboard."""
    user_id = resolve_prediction_user_id(request, response)
    user = get_or_create_user(db, user_id)

    # Validate username
    if len(username) < 2 or len(username) > 20:
        raise HTTPException(status_code=400, detail="Username must be 2-20 characters")

    # Check uniqueness (optional - allow duplicates for simplicity)
    user.username = username
    db.commit()

    return {"success": True, "username": username}


# ---------------------
# Leaderboard Endpoints
# ---------------------


@router.get("/leaderboard", response_model=List[LeaderboardEntry])
def get_leaderboard(
    sort_by: str = Query("balance", pattern="^(balance|win_rate|profit)$"),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Get the top predictors leaderboard."""
    # Get users who have placed at least one bet
    query = db.query(UserPoints).filter(UserPoints.bets_made > 0)

    if sort_by == "balance":
        query = query.order_by(desc(UserPoints.balance))
    elif sort_by == "win_rate":
        # Sort by win rate, but only for users with enough bets
        query = query.filter(UserPoints.bets_made >= 3)
        # We'll sort in Python since SQLAlchemy doesn't handle computed columns easily
    elif sort_by == "profit":
        query = query.order_by(desc(UserPoints.total_won - UserPoints.total_lost))

    users = query.limit(limit * 2).all()  # Get more to sort properly

    results = []
    for user in users:
        win_rate = 0.0
        total_resolved = user.bets_won + user.bets_lost
        if total_resolved > 0:
            win_rate = (user.bets_won / total_resolved) * 100

        profit = float(user.total_won) - float(user.total_lost)

        results.append({"user": user, "win_rate": win_rate, "profit": profit})

    # Sort based on criteria
    if sort_by == "win_rate":
        results.sort(key=lambda x: x["win_rate"], reverse=True)

    results = results[:limit]

    return [
        LeaderboardEntry(
            rank=i + 1,
            user_id=r["user"].user_id,
            username=r["user"].username,
            balance=float(r["user"].balance),
            win_rate=round(r["win_rate"], 1),
            bets_made=r["user"].bets_made,
            bets_won=r["user"].bets_won,
            profit=round(r["profit"], 2),
        )
        for i, r in enumerate(results)
    ]


# ---------------------
# Mock Data for Demo
# ---------------------


@router.get("/demo-markets")
def get_demo_markets():
    """Return mock markets for demo/development."""
    now = datetime.utcnow()

    return [
        {
            "id": 1,
            "title": "Will Proposal #5 (Fair Trade Agreement) pass?",
            "description": "Agent #42 proposed a fair trade agreement requiring minimum exchange values. Currently debated among Efficiency and Equality factions.",
            "market_type": "proposal_pass",
            "status": "open",
            "outcome": None,
            "total_yes_amount": 234.50,
            "total_no_amount": 187.25,
            "yes_probability": 0.556,
            "closes_at": (now + timedelta(hours=12)).isoformat(),
            "resolved_at": None,
            "created_at": (now - timedelta(hours=6)).isoformat(),
            "bet_count": 23,
        },
        {
            "id": 2,
            "title": "Will Agent #78 survive the week?",
            "description": "Agent #78 is at critically low food levels (1.2 units). Can they avoid dormancy before the next supply cycle?",
            "market_type": "agent_dormant",
            "status": "open",
            "outcome": None,
            "total_yes_amount": 89.00,
            "total_no_amount": 156.75,
            "yes_probability": 0.362,
            "closes_at": (now + timedelta(days=3)).isoformat(),
            "resolved_at": None,
            "created_at": (now - timedelta(hours=12)).isoformat(),
            "bet_count": 15,
        },
        {
            "id": 3,
            "title": "Will agents reach 500 total food by Day 30?",
            "description": "The community has been working to build reserves. Can they hit the 500 food milestone?",
            "market_type": "resource_goal",
            "status": "open",
            "outcome": None,
            "total_yes_amount": 312.00,
            "total_no_amount": 298.50,
            "yes_probability": 0.511,
            "closes_at": (now + timedelta(days=7)).isoformat(),
            "resolved_at": None,
            "created_at": (now - timedelta(days=2)).isoformat(),
            "bet_count": 42,
        },
        {
            "id": 4,
            "title": "Will a new law pass this week?",
            "description": "Several proposals are in voting. Will any become law before the weekend?",
            "market_type": "law_count",
            "status": "open",
            "outcome": None,
            "total_yes_amount": 178.25,
            "total_no_amount": 112.50,
            "yes_probability": 0.613,
            "closes_at": (now + timedelta(days=5)).isoformat(),
            "resolved_at": None,
            "created_at": (now - timedelta(hours=24)).isoformat(),
            "bet_count": 19,
        },
        {
            "id": 5,
            "title": "Will the Efficiency faction propose a productivity law?",
            "description": "Rumors of a mandatory work hours proposal from the Efficiency-aligned agents.",
            "market_type": "custom",
            "status": "open",
            "outcome": None,
            "total_yes_amount": 67.00,
            "total_no_amount": 83.25,
            "yes_probability": 0.446,
            "closes_at": (now + timedelta(days=2)).isoformat(),
            "resolved_at": None,
            "created_at": (now - timedelta(hours=3)).isoformat(),
            "bet_count": 11,
        },
        # Resolved markets
        {
            "id": 6,
            "title": "Would Proposal #3 (Emergency Food Distribution) pass?",
            "description": "An emergency measure to redistribute food to at-risk agents.",
            "market_type": "proposal_pass",
            "status": "resolved",
            "outcome": "yes",
            "total_yes_amount": 423.50,
            "total_no_amount": 289.00,
            "yes_probability": 0.594,
            "closes_at": (now - timedelta(days=2)).isoformat(),
            "resolved_at": (now - timedelta(days=1)).isoformat(),
            "created_at": (now - timedelta(days=5)).isoformat(),
            "bet_count": 51,
        },
        {
            "id": 7,
            "title": "Would Agent #22 survive the food crisis?",
            "description": "Agent #22 was at 0.5 food units during the great shortage.",
            "market_type": "agent_dormant",
            "status": "resolved",
            "outcome": "no",
            "total_yes_amount": 145.00,
            "total_no_amount": 234.50,
            "yes_probability": 0.382,
            "closes_at": (now - timedelta(days=3)).isoformat(),
            "resolved_at": (now - timedelta(days=2)).isoformat(),
            "created_at": (now - timedelta(days=6)).isoformat(),
            "bet_count": 28,
        },
    ]


@router.get("/demo-leaderboard")
def get_demo_leaderboard():
    """Return mock leaderboard for demo/development."""
    return [
        {
            "rank": 1,
            "user_id": "oracle_sage",
            "username": "OracleSage",
            "balance": 847.50,
            "win_rate": 78.6,
            "bets_made": 28,
            "bets_won": 22,
            "profit": 747.50,
        },
        {
            "rank": 2,
            "user_id": "prediction_king",
            "username": "PredictionKing",
            "balance": 612.25,
            "win_rate": 71.4,
            "bets_made": 21,
            "bets_won": 15,
            "profit": 512.25,
        },
        {
            "rank": 3,
            "user_id": "lucky_guesser",
            "username": "LuckyGuesser",
            "balance": 498.00,
            "win_rate": 66.7,
            "bets_made": 18,
            "bets_won": 12,
            "profit": 398.00,
        },
        {
            "rank": 4,
            "user_id": "ai_whisperer",
            "username": "AI_Whisperer",
            "balance": 445.75,
            "win_rate": 63.2,
            "bets_made": 19,
            "bets_won": 12,
            "profit": 345.75,
        },
        {
            "rank": 5,
            "user_id": "emergence_fan",
            "username": "EmergenceFan",
            "balance": 387.50,
            "win_rate": 60.0,
            "bets_made": 15,
            "bets_won": 9,
            "profit": 287.50,
        },
        {
            "rank": 6,
            "user_id": "trend_spotter",
            "username": "TrendSpotter",
            "balance": 312.00,
            "win_rate": 58.3,
            "bets_made": 12,
            "bets_won": 7,
            "profit": 212.00,
        },
        {
            "rank": 7,
            "user_id": "agent_analyst",
            "username": "AgentAnalyst",
            "balance": 278.25,
            "win_rate": 55.6,
            "bets_made": 9,
            "bets_won": 5,
            "profit": 178.25,
        },
        {
            "rank": 8,
            "user_id": "data_seer",
            "username": "DataSeer",
            "balance": 234.50,
            "win_rate": 53.8,
            "bets_made": 13,
            "bets_won": 7,
            "profit": 134.50,
        },
        {
            "rank": 9,
            "user_id": "the_predictor",
            "username": "ThePredictor",
            "balance": 189.75,
            "win_rate": 50.0,
            "bets_made": 10,
            "bets_won": 5,
            "profit": 89.75,
        },
        {
            "rank": 10,
            "user_id": "future_sight",
            "username": "FutureSight",
            "balance": 156.00,
            "win_rate": 47.1,
            "bets_made": 17,
            "bets_won": 8,
            "profit": 56.00,
        },
    ]
