"""
Prediction Market API Router
Handles betting, market creation, and leaderboard endpoints.
"""
from typing import Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
import hmac
import hashlib
import uuid

from app.core.config import settings
from app.core.database import get_db
from app.core.time import ensure_utc, now_utc
from app.models.predictions import PredictionMarket, PredictionBet, UserPoints
from app.models.models import Proposal, Agent, AgentInventory, Event, GlobalResources, Law
from app.services.survival_config import active_energy_cost, active_food_cost, low_resource_warning_threshold
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
AUTO_MARKET_RESERVE_TITLE = "Will the shared reserve avoid a shortfall in the next 24 hours?"


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
    created_at: str
    bet_count: int
    auto_generated: bool = False
    stake: Optional[str] = None
    why_this_matters: Optional[str] = None
    resolution_basis: Optional[str] = None
    evidence_links: List[EvidenceLinkResponse] = Field(default_factory=list)
    
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
        user = UserPoints(
            user_id=user_id,
            balance=STARTING_BALANCE
        )
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


def _agent_market_title(agent: Agent) -> str:
    return f"Will {_agent_label(agent)} stay active in the next 24 hours?"


def _is_auto_market(market: PredictionMarket) -> bool:
    title = str(market.title or "").strip()
    if title in {AUTO_MARKET_LAW_TITLE, AUTO_MARKET_DEATH_TITLE, AUTO_MARKET_RESERVE_TITLE}:
        return True
    return bool(
        market.market_type == "agent_dormant"
        and market.related_agent_id is not None
        and title.endswith("stay active in the next 24 hours?")
    )


def _agent_resource_map(db: Session, *, agent_ids: list[int]) -> dict[int, dict[str, float]]:
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

    resources_by_agent = _agent_resource_map(db, agent_ids=[int(agent.id) for agent in agents])
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
        ranked.append((severity, deficit, remaining, agent, {"food": food, "energy": energy}))

    if not ranked:
        return None, {}

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2], int(item[3].agent_number)))
    _, _, _, agent, resources = ranked[0]
    return agent, resources


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
    payloads: list[dict[str, Any]] = []

    active_proposals = (
        db.query(Proposal)
        .filter(Proposal.status == "active")
        .order_by(Proposal.created_at.desc(), Proposal.id.desc())
        .all()
    )
    leading_proposal = None
    if active_proposals:
        leading_proposal = sorted(
            active_proposals,
            key=lambda row: (int(row.votes_for or 0) - int(row.votes_against or 0), int(row.id or 0)),
            reverse=True,
        )[0]
    proposal_context = (
        f"{len(active_proposals)} active proposal(s) are open now."
        + (
            f" Front-runner: \"{str(leading_proposal.title or '').strip() or 'Untitled proposal'}\" "
            f"at {int(leading_proposal.votes_for or 0)}-{int(leading_proposal.votes_against or 0)}."
            if leading_proposal is not None
            else " No proposal has separated itself yet."
        )
    )
    payloads.append(
        {
            "title": AUTO_MARKET_LAW_TITLE,
            "description": proposal_context,
            "market_type": "law_count",
            "related_proposal_id": int(leading_proposal.id) if leading_proposal is not None else None,
            "stake": "A passed law changes the rules for every agent, not just one bloc.",
            "why_this_matters": "This hook measures whether debate turns into actual world-state change.",
            "resolution_basis": "Settles YES if any law is passed before the market closes.",
            "evidence_links": _prediction_evidence_links(
                ("Proposals", "/proposals"),
                ("Highlights", "/highlights?tab=recap"),
            ),
            "closes_at": now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS),
        }
    )

    reserve_rows = db.query(GlobalResources).all()
    common_pool = {str(row.resource_type): float(row.in_common_pool or 0) for row in reserve_rows}
    reserve_shortfalls_24h = (
        db.query(func.count(Event.id))
        .filter(
            Event.event_type == "reserve_shortfall",
            Event.created_at >= now_value - timedelta(hours=24),
        )
        .scalar()
    ) or 0
    payloads.append(
        {
            "title": AUTO_MARKET_RESERVE_TITLE,
            "description": (
                f"Shared reserve now holds {float(common_pool.get('food', 0.0)):.2f} food and "
                f"{float(common_pool.get('energy', 0.0)):.2f} energy, with {int(reserve_shortfalls_24h)} "
                "shortfall signal(s) in the last 24 hours."
            ),
            "market_type": "resource_goal",
            "related_proposal_id": None,
            "stake": "If the reserve buckles, survival pressure can jump from a private problem to a public crisis.",
            "why_this_matters": "This hook settles off reserve-shortfall events only; audience picks do not feed back into allocation.",
            "resolution_basis": "Settles YES if no reserve_shortfall event is recorded before close.",
            "evidence_links": _prediction_evidence_links(
                ("Resources", "/resources"),
                ("Best Moments", "/highlights?tab=highlights"),
            ),
            "closes_at": now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS),
        }
    )

    dormant_count = db.query(Agent).filter(Agent.status == "dormant").count()
    critical_food = (
        db.query(func.count(AgentInventory.id))
        .filter(AgentInventory.resource_type == "food", AgentInventory.quantity < 2)
        .scalar()
    ) or 0
    critical_energy = (
        db.query(func.count(AgentInventory.id))
        .filter(AgentInventory.resource_type == "energy", AgentInventory.quantity < 2)
        .scalar()
    ) or 0
    payloads.append(
        {
            "title": AUTO_MARKET_DEATH_TITLE,
            "description": (
                f"{int(dormant_count)} agent(s) are dormant, while {int(critical_food)} food warnings and "
                f"{int(critical_energy)} energy warnings are currently visible."
            ),
            "market_type": "custom",
            "related_proposal_id": None,
            "stake": "A death is irreversible and instantly changes the cast of the run.",
            "why_this_matters": "This hook resolves from live death events only; prediction picks do not alter the simulation.",
            "resolution_basis": "Settles YES if any agent_died event is recorded before close.",
            "evidence_links": _prediction_evidence_links(
                ("Agents", "/agents"),
                ("Replay", "/highlights?tab=replay"),
            ),
            "closes_at": now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS),
        }
    )

    at_risk_agent, resources = _select_most_at_risk_agent(db)
    if at_risk_agent is not None:
        payloads.append(
            {
                "title": _agent_market_title(at_risk_agent),
                "description": (
                    f"{_agent_label(at_risk_agent)} currently holds {float(resources.get('food', 0.0)):.2f} food and "
                    f"{float(resources.get('energy', 0.0)):.2f} energy."
                ),
                "market_type": "agent_dormant",
                "related_agent_id": int(at_risk_agent.id),
                "stake": "This is the clearest single-agent survival watch in the public state right now.",
                "why_this_matters": "If this agent drops into dormancy or dies, the turn is directly visible on the public record.",
                "resolution_basis": "Settles YES if the agent remains active and no dormancy/death event is recorded before close.",
                "evidence_links": _prediction_evidence_links(
                    ("Agent Detail", f"/agents/{int(at_risk_agent.agent_number)}"),
                    ("All Agents", "/agents"),
                ),
                "closes_at": now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS),
            }
        )

    return payloads


def _find_open_auto_market(db: Session, payload: dict[str, Any]) -> PredictionMarket | None:
    title = str(payload.get("title") or "").strip()
    query = db.query(PredictionMarket).filter(PredictionMarket.status == "open")
    if str(payload.get("market_type") or "") == "agent_dormant" and payload.get("related_agent_id") is not None:
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


def _resolve_market_bets(db: Session, *, market: PredictionMarket, outcome: str, resolved_at: datetime) -> None:
    market.status = "resolved"
    market.outcome = str(outcome or "").strip().lower()
    market.resolved_at = resolved_at

    bets = (
        db.query(PredictionBet)
        .filter(PredictionBet.market_id == market.id)
        .order_by(PredictionBet.id.asc())
        .all()
    )
    total_pool = sum((Decimal(str(bet.amount or 0)) for bet in bets), Decimal("0"))
    winning_pool = sum(
        (Decimal(str(bet.amount or 0)) for bet in bets if str(bet.prediction or "").strip().lower() == market.outcome),
        Decimal("0"),
    )
    user_cache: dict[str, UserPoints] = {}
    for bet in bets:
        user = user_cache.get(str(bet.user_id or ""))
        if user is None:
            user = db.query(UserPoints).filter(UserPoints.user_id == bet.user_id).first()
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

    return None


def _sync_auto_prediction_markets(db: Session) -> None:
    now_value = now_utc()
    changed = False

    open_markets = db.query(PredictionMarket).filter(PredictionMarket.status == "open").all()
    for market in open_markets:
        if not _is_auto_market(market):
            continue
        closes_at = ensure_utc(market.closes_at)
        if closes_at is None or closes_at > now_value:
            continue
        outcome = _resolve_auto_market_outcome(db, market)
        if outcome not in {"yes", "no"}:
            continue
        _resolve_market_bets(db, market=market, outcome=outcome, resolved_at=now_value)
        changed = True

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
            closes_at=payload.get("closes_at") or (now_value + timedelta(hours=AUTO_MARKET_WINDOW_HOURS)),
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
    resources_by_agent = _agent_resource_map(db, agent_ids=[int(related_agent.id)]) if related_agent is not None else {}
    related_resources = resources_by_agent.get(int(related_agent.id), {}) if related_agent is not None else {}

    for payload in _auto_market_payloads(db):
        if title in {AUTO_MARKET_LAW_TITLE, AUTO_MARKET_DEATH_TITLE, AUTO_MARKET_RESERVE_TITLE} and title == str(payload.get("title") or "").strip():
            return payload
        if related_agent is not None and title == _agent_market_title(related_agent) and str(payload.get("title") or "").strip() == title:
            payload = dict(payload)
            payload["description"] = (
                f"{_agent_label(related_agent)} currently holds {float(related_resources.get('food', 0.0)):.2f} food and "
                f"{float(related_resources.get('energy', 0.0)):.2f} energy."
            )
            return payload
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
    return MarketResponse(
        id=market.id,
        title=market.title,
        description=context.get("description") or market.description,
        market_type=market.market_type,
        status=market.status,
        outcome=market.outcome,
        total_yes_amount=float(market.total_yes_amount),
        total_no_amount=float(market.total_no_amount),
        yes_probability=calculate_probability(market.total_yes_amount, market.total_no_amount),
        closes_at=ensure_utc(market.closes_at).isoformat() if market.closes_at else "",
        resolved_at=ensure_utc(market.resolved_at).isoformat() if market.resolved_at else None,
        created_at=ensure_utc(market.created_at).isoformat() if market.created_at else "",
        bet_count=len(market.bets),
        auto_generated=_is_auto_market(market),
        stake=context.get("stake"),
        why_this_matters=context.get("why_this_matters"),
        resolution_basis=context.get("resolution_basis"),
        evidence_links=[EvidenceLinkResponse(**item) for item in list(context.get("evidence_links") or [])],
    )


# ---------------------
# Market Endpoints
# ---------------------

@router.get("/markets", response_model=List[MarketResponse])
def list_markets(
    status: Optional[str] = None,
    market_type: Optional[str] = None,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db)
):
    """List all prediction markets with optional filters."""
    _sync_auto_prediction_markets(db)
    query = db.query(PredictionMarket)
    
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
    db: Session = Depends(get_db)
):
    """Place a bet on a prediction market."""
    _sync_auto_prediction_markets(db)
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
        raise HTTPException(status_code=400, detail="Betting has closed for this market")
    
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
    existing_bet = db.query(PredictionBet).filter(
        PredictionBet.market_id == market_id,
        PredictionBet.user_id == user_id
    ).first()
    
    if existing_bet:
        raise HTTPException(status_code=400, detail="You have already placed a bet on this market")
    
    # Create bet
    bet = PredictionBet(
        market_id=market_id,
        user_id=user_id,
        prediction=bet_request.prediction,
        amount=bet_amount
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
        created_at=bet.created_at.isoformat() if bet.created_at else ""
    )


@router.get("/markets/{market_id}/bets", response_model=List[BetResponse])
def get_market_bets(
    market_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Get user's bets on a specific market."""
    user_id = resolve_prediction_user_id(request, response)
    
    bets = db.query(PredictionBet).filter(
        PredictionBet.market_id == market_id,
        PredictionBet.user_id == user_id
    ).all()
    
    return [
        BetResponse(
            id=b.id,
            market_id=b.market_id,
            prediction=b.prediction,
            amount=float(b.amount),
            won=b.won,
            payout=float(b.payout) if b.payout else None,
            created_at=b.created_at.isoformat() if b.created_at else ""
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
    rank = db.query(func.count(UserPoints.id)).filter(
        UserPoints.balance > user.balance
    ).scalar() + 1
    
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
        rank=rank
    )


@router.get("/my-bets", response_model=List[BetResponse])
def get_my_bets(
    request: Request,
    response: Response,
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
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
            created_at=b.created_at.isoformat() if b.created_at else ""
        )
        for b in bets
    ]


@router.post("/set-username")
def set_username(
    username: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
        
        results.append({
            "user": user,
            "win_rate": win_rate,
            "profit": profit
        })
    
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
            profit=round(r["profit"], 2)
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
            "bet_count": 23
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
            "bet_count": 15
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
            "bet_count": 42
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
            "bet_count": 19
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
            "bet_count": 11
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
            "bet_count": 51
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
            "bet_count": 28
        }
    ]


@router.get("/demo-leaderboard")
def get_demo_leaderboard():
    """Return mock leaderboard for demo/development."""
    return [
        {"rank": 1, "user_id": "oracle_sage", "username": "OracleSage", "balance": 847.50, "win_rate": 78.6, "bets_made": 28, "bets_won": 22, "profit": 747.50},
        {"rank": 2, "user_id": "prediction_king", "username": "PredictionKing", "balance": 612.25, "win_rate": 71.4, "bets_made": 21, "bets_won": 15, "profit": 512.25},
        {"rank": 3, "user_id": "lucky_guesser", "username": "LuckyGuesser", "balance": 498.00, "win_rate": 66.7, "bets_made": 18, "bets_won": 12, "profit": 398.00},
        {"rank": 4, "user_id": "ai_whisperer", "username": "AI_Whisperer", "balance": 445.75, "win_rate": 63.2, "bets_made": 19, "bets_won": 12, "profit": 345.75},
        {"rank": 5, "user_id": "emergence_fan", "username": "EmergenceFan", "balance": 387.50, "win_rate": 60.0, "bets_made": 15, "bets_won": 9, "profit": 287.50},
        {"rank": 6, "user_id": "trend_spotter", "username": "TrendSpotter", "balance": 312.00, "win_rate": 58.3, "bets_made": 12, "bets_won": 7, "profit": 212.00},
        {"rank": 7, "user_id": "agent_analyst", "username": "AgentAnalyst", "balance": 278.25, "win_rate": 55.6, "bets_made": 9, "bets_won": 5, "profit": 178.25},
        {"rank": 8, "user_id": "data_seer", "username": "DataSeer", "balance": 234.50, "win_rate": 53.8, "bets_made": 13, "bets_won": 7, "profit": 134.50},
        {"rank": 9, "user_id": "the_predictor", "username": "ThePredictor", "balance": 189.75, "win_rate": 50.0, "bets_made": 10, "bets_won": 5, "profit": 89.75},
        {"rank": 10, "user_id": "future_sight", "username": "FutureSight", "balance": 156.00, "win_rate": 47.1, "bets_made": 17, "bets_won": 8, "profit": 56.00},
    ]
