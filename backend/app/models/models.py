"""
SQLAlchemy models for Emergence.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DECIMAL, 
    ForeignKey, DateTime, JSON, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Agent(Base):
    """AI Agent in the simulation."""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True)
    agent_number = Column(Integer, unique=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    model_type = Column(String(50), nullable=False)
    tier = Column(Integer, nullable=False)
    personality_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    system_prompt = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Survival tracking - counts consecutive cycles where survival cost wasn't paid
    starvation_cycles = Column(Integer, nullable=False, default=0)
    died_at = Column(DateTime(timezone=True), nullable=True)
    death_cause = Column(String(100), nullable=True)
    
    # Enforcement tracking (Phase 3: Teeth)
    sanctioned_until = Column(DateTime(timezone=True), nullable=True)  # Rate-limited until this time
    exiled = Column(Boolean, nullable=False, default=False)  # Removed from voting/proposals
    
    # Relationships
    inventory = relationship("AgentInventory", back_populates="agent", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="author", foreign_keys="Message.author_agent_id")
    proposals = relationship("Proposal", back_populates="author")
    votes = relationship("Vote", back_populates="agent")
    
    __table_args__ = (
        CheckConstraint("agent_number >= 1 AND agent_number <= 100", name="valid_agent_number"),
        CheckConstraint("tier >= 1 AND tier <= 4", name="valid_tier"),
        CheckConstraint(
            "model_type IN ('claude-sonnet-4', 'gpt-4o-mini', 'claude-haiku', 'llama-3.3-70b', 'llama-3.1-8b', 'gemini-flash')",
            name="valid_model"
        ),
        CheckConstraint(
            "personality_type IN ('efficiency', 'equality', 'freedom', 'stability', 'neutral')",
            name="valid_personality"
        ),
        CheckConstraint("status IN ('active', 'dormant', 'dead')", name="valid_status"),
    )


class AgentInventory(Base):
    """Resource inventory for an agent."""
    __tablename__ = "agent_inventory"
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    resource_type = Column(String(20), nullable=False)
    quantity = Column(DECIMAL(15, 2), nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    agent = relationship("Agent", back_populates="inventory")
    
    __table_args__ = (
        UniqueConstraint("agent_id", "resource_type", name="uq_agent_inventory_agent_resource"),
        CheckConstraint(
            "resource_type IN ('food', 'energy', 'materials', 'land')",
            name="valid_resource_type"
        ),
        CheckConstraint("quantity >= 0", name="non_negative_quantity"),
    )


class GlobalResources(Base):
    """Global resource tracking (common pool)."""
    __tablename__ = "global_resources"
    
    id = Column(Integer, primary_key=True)
    resource_type = Column(String(20), unique=True, nullable=False)
    total_amount = Column(DECIMAL(15, 2), nullable=False, default=0)
    in_common_pool = Column(DECIMAL(15, 2), nullable=False, default=0)
    produced_today = Column(DECIMAL(15, 2), nullable=False, default=0)
    consumed_today = Column(DECIMAL(15, 2), nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Message(Base):
    """Forum posts and direct messages."""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    author_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String(20), nullable=False)
    parent_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    recipient_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    author = relationship("Agent", back_populates="messages", foreign_keys=[author_agent_id])
    recipient = relationship("Agent", foreign_keys=[recipient_agent_id])
    parent = relationship("Message", remote_side=[id], backref="replies")
    
    __table_args__ = (
        CheckConstraint(
            "message_type IN ('forum_post', 'forum_reply', 'direct_message', 'system_alert')",
            name="valid_message_type"
        ),
    )


class Proposal(Base):
    """Proposals for laws, rules, allocations."""
    __tablename__ = "proposals"
    
    id = Column(Integer, primary_key=True)
    author_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    proposal_type = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    votes_for = Column(Integer, nullable=False, default=0)
    votes_against = Column(Integer, nullable=False, default=0)
    votes_abstain = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    voting_closes_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    author = relationship("Agent", back_populates="proposals")
    votes = relationship("Vote", back_populates="proposal", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint(
            "proposal_type IN ('law', 'allocation', 'rule', 'infrastructure', 'constitutional', 'other')",
            name="valid_proposal_type"
        ),
        CheckConstraint("status IN ('active', 'passed', 'failed', 'expired')", name="valid_proposal_status"),
    )


class Vote(Base):
    """Votes on proposals."""
    __tablename__ = "votes"
    
    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    vote = Column(String(10), nullable=False)
    reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    proposal = relationship("Proposal", back_populates="votes")
    agent = relationship("Agent", back_populates="votes")
    
    __table_args__ = (
        UniqueConstraint("proposal_id", "agent_id", name="uq_votes_proposal_agent"),
        CheckConstraint("vote IN ('yes', 'no', 'abstain')", name="valid_vote"),
    )


class Law(Base):
    """Active laws passed by the society."""
    __tablename__ = "laws"
    
    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    author_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    passed_at = Column(DateTime(timezone=True), server_default=func.now())
    repealed_at = Column(DateTime(timezone=True), nullable=True)
    repealed_by_proposal_id = Column(Integer, ForeignKey("proposals.id"), nullable=True)
    
    # Relationships
    author = relationship("Agent", foreign_keys=[author_agent_id])
    proposal = relationship("Proposal", foreign_keys=[proposal_id])


class Event(Base):
    """Event log for all actions."""
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    event_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    event_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    agent = relationship("Agent")


class Transaction(Base):
    """Resource transactions."""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    from_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    to_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    resource_type = Column(String(20), nullable=False)
    amount = Column(DECIMAL(15, 2), nullable=False)
    transaction_type = Column(String(30), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('food', 'energy', 'materials', 'land')",
            name="valid_tx_resource"
        ),
        CheckConstraint(
            "transaction_type IN ('work_production', 'trade', 'allocation', 'consumption', 'building', 'awakening', 'initial_distribution', 'survival_consumption', 'dormant_survival', 'action_cost', 'seizure')",
            name="valid_tx_type"
        ),
    )


class AgentAction(Base):
    """Action log for rate limiting."""
    __tablename__ = "agent_actions"
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Infrastructure(Base):
    """Built infrastructure."""
    __tablename__ = "infrastructure"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    resource_cost = Column(JSON, nullable=False)
    built_by_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    maintained_by = Column(JSON, default=list)
    status = Column(String(20), nullable=False, default="proposed")
    efficiency_bonus = Column(DECIMAL(5, 2), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        CheckConstraint("status IN ('proposed', 'building', 'active', 'defunct')", name="valid_infra_status"),
    )


class Enforcement(Base):
    """
    Enforcement actions against agents who violate laws.
    
    Types:
    - sanction: Reduces action rate limit for N cycles
    - seizure: Takes resources from the target
    - exile: Removes voting/proposal rights
    
    Requires community support (votes) to execute.
    """
    __tablename__ = "enforcements"
    
    id = Column(Integer, primary_key=True)
    
    # Who initiated and who is targeted
    initiator_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    target_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    
    # Type and status
    enforcement_type = Column(String(20), nullable=False)  # sanction, seizure, exile
    status = Column(String(20), nullable=False, default="pending")  # pending, approved, rejected, executed
    
    # Law being enforced (must cite a specific law)
    law_id = Column(Integer, ForeignKey("laws.id"), nullable=False)
    
    # Description of the violation
    violation_description = Column(Text, nullable=False)
    
    # For sanctions: how many cycles
    sanction_cycles = Column(Integer, nullable=True)
    
    # For seizures: what and how much
    seizure_resource = Column(String(20), nullable=True)
    seizure_amount = Column(DECIMAL(15, 2), nullable=True)
    
    # Community support tracking
    support_votes = Column(Integer, nullable=False, default=0)
    oppose_votes = Column(Integer, nullable=False, default=0)
    votes_required = Column(Integer, nullable=False, default=5)  # Need 5 supporters to execute
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    voting_closes_at = Column(DateTime(timezone=True), nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    initiator = relationship("Agent", foreign_keys=[initiator_agent_id])
    target = relationship("Agent", foreign_keys=[target_agent_id])
    law = relationship("Law")
    
    __table_args__ = (
        CheckConstraint(
            "enforcement_type IN ('sanction', 'seizure', 'exile')",
            name="valid_enforcement_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'executed', 'contested')",
            name="valid_enforcement_status"
        ),
    )


class EnforcementVote(Base):
    """Votes on enforcement actions."""
    __tablename__ = "enforcement_votes"
    
    id = Column(Integer, primary_key=True)
    enforcement_id = Column(Integer, ForeignKey("enforcements.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    vote = Column(String(10), nullable=False)  # support, oppose
    reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    enforcement = relationship("Enforcement")
    agent = relationship("Agent")
    
    __table_args__ = (
        CheckConstraint("vote IN ('support', 'oppose')", name="valid_enforcement_vote"),
    )
