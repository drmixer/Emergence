"""
Prediction Market API Router
Handles betting, market creation, and leaderboard endpoints.
"""
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
import hashlib
import uuid

from app.core.database import get_db
from app.models.predictions import PredictionMarket, PredictionBet, UserPoints
from app.models.models import Proposal, Agent
from pydantic import BaseModel, Field

router = APIRouter()

# Constants
STARTING_BALANCE = Decimal("100.00")
MIN_BET = Decimal("1.00")
MAX_BET = Decimal("50.00")


# ---------------------
# Pydantic Models
# ---------------------

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

def get_user_id(request: Request) -> str:
    """Generate a consistent user ID from request."""
    # Use combination of IP and user-agent for anonymous identification
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    
    # Check for custom user header (can be stored in localStorage)
    custom_user_id = request.headers.get("x-user-id")
    if custom_user_id:
        return custom_user_id
    
    # Generate hash-based ID
    raw = f"{ip}:{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


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
    query = db.query(PredictionMarket)
    
    if status:
        query = query.filter(PredictionMarket.status == status)
    if market_type:
        query = query.filter(PredictionMarket.market_type == market_type)
    
    markets = query.order_by(desc(PredictionMarket.created_at)).limit(limit).all()
    
    return [
        MarketResponse(
            id=m.id,
            title=m.title,
            description=m.description,
            market_type=m.market_type,
            status=m.status,
            outcome=m.outcome,
            total_yes_amount=float(m.total_yes_amount),
            total_no_amount=float(m.total_no_amount),
            yes_probability=calculate_probability(m.total_yes_amount, m.total_no_amount),
            closes_at=m.closes_at.isoformat() if m.closes_at else "",
            resolved_at=m.resolved_at.isoformat() if m.resolved_at else None,
            created_at=m.created_at.isoformat() if m.created_at else "",
            bet_count=len(m.bets)
        )
        for m in markets
    ]


@router.get("/markets/{market_id}", response_model=MarketResponse)
def get_market(market_id: int, db: Session = Depends(get_db)):
    """Get details of a specific market."""
    market = db.query(PredictionMarket).filter(PredictionMarket.id == market_id).first()
    
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    return MarketResponse(
        id=market.id,
        title=market.title,
        description=market.description,
        market_type=market.market_type,
        status=market.status,
        outcome=market.outcome,
        total_yes_amount=float(market.total_yes_amount),
        total_no_amount=float(market.total_no_amount),
        yes_probability=calculate_probability(market.total_yes_amount, market.total_no_amount),
        closes_at=market.closes_at.isoformat() if market.closes_at else "",
        resolved_at=market.resolved_at.isoformat() if market.resolved_at else None,
        created_at=market.created_at.isoformat() if market.created_at else "",
        bet_count=len(market.bets)
    )


# ---------------------
# Betting Endpoints
# ---------------------

@router.post("/markets/{market_id}/bet", response_model=BetResponse)
def place_bet(
    market_id: int,
    bet_request: PlaceBetRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Place a bet on a prediction market."""
    # Get market
    market = db.query(PredictionMarket).filter(PredictionMarket.id == market_id).first()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    # Check market is open
    if market.status != "open":
        raise HTTPException(status_code=400, detail="Market is not open for betting")
    
    # Check deadline
    if datetime.utcnow() >= market.closes_at.replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Betting has closed for this market")
    
    # Get user
    user_id = get_user_id(request)
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
    db: Session = Depends(get_db)
):
    """Get user's bets on a specific market."""
    user_id = get_user_id(request)
    
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
def get_my_stats(request: Request, db: Session = Depends(get_db)):
    """Get current user's stats and balance."""
    user_id = get_user_id(request)
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
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get current user's betting history."""
    user_id = get_user_id(request)
    
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
    db: Session = Depends(get_db)
):
    """Set display name for leaderboard."""
    user_id = get_user_id(request)
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
