"""
Prediction Market Models for Emergence.
Users can bet fake currency (Emergence Points) on various outcomes.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DECIMAL, 
    ForeignKey, DateTime, JSON, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class PredictionMarket(Base):
    """A prediction market for betting on outcomes."""
    __tablename__ = "prediction_markets"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    market_type = Column(String(30), nullable=False)  # proposal_pass, agent_dormant, resource_goal, law_count, etc.
    
    # What this market is about
    related_proposal_id = Column(Integer, ForeignKey("proposals.id"), nullable=True)
    related_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    
    # Market state
    status = Column(String(20), nullable=False, default="open")  # open, closed, resolved
    outcome = Column(String(20), nullable=True)  # yes, no, null (for unresolved)
    
    # Total amounts bet
    total_yes_amount = Column(DECIMAL(15, 2), nullable=False, default=0)
    total_no_amount = Column(DECIMAL(15, 2), nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closes_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    bets = relationship("PredictionBet", back_populates="market", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint(
            "market_type IN ('proposal_pass', 'agent_dormant', 'resource_goal', 'law_count', 'custom')",
            name="valid_market_type"
        ),
        CheckConstraint(
            "status IN ('open', 'closed', 'resolved')",
            name="valid_market_status"
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('yes', 'no')",
            name="valid_market_outcome"
        ),
    )


class PredictionBet(Base):
    """A user's bet on a prediction market."""
    __tablename__ = "prediction_bets"
    
    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("prediction_markets.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(100), nullable=False)  # IP-based or session-based anonymous user ID
    
    prediction = Column(String(10), nullable=False)  # yes or no
    amount = Column(DECIMAL(15, 2), nullable=False)
    
    # Winnings calculation (filled after resolution)
    won = Column(Boolean, nullable=True)  # null until resolved
    payout = Column(DECIMAL(15, 2), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    market = relationship("PredictionMarket", back_populates="bets")
    
    __table_args__ = (
        CheckConstraint("prediction IN ('yes', 'no')", name="valid_bet_prediction"),
        CheckConstraint("amount > 0", name="positive_bet_amount"),
    )


class UserPoints(Base):
    """Track user's Emergence Points balance."""
    __tablename__ = "user_points"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), unique=True, nullable=False)
    username = Column(String(100), nullable=True)  # Optional display name
    
    # Points balance
    balance = Column(DECIMAL(15, 2), nullable=False, default=100)  # Start with 100 EP
    total_wagered = Column(DECIMAL(15, 2), nullable=False, default=0)
    total_won = Column(DECIMAL(15, 2), nullable=False, default=0)
    total_lost = Column(DECIMAL(15, 2), nullable=False, default=0)
    
    # Stats
    bets_made = Column(Integer, nullable=False, default=0)
    bets_won = Column(Integer, nullable=False, default=0)
    bets_lost = Column(Integer, nullable=False, default=0)
    
    # Streak tracking
    current_streak = Column(Integer, nullable=False, default=0)  # Positive = wins, negative = losses
    best_streak = Column(Integer, nullable=False, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        CheckConstraint("balance >= 0", name="non_negative_balance"),
    )
