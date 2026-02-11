"""
SQLAlchemy models for Emergence.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DECIMAL, 
    ForeignKey, Date, DateTime, JSON, CheckConstraint, UniqueConstraint, Index
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
    # Strategic planning state: checkpoint-generated intent executed between checkpoints.
    current_intent = Column(JSON, nullable=True, default=dict)
    intent_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_checkpoint_at = Column(DateTime(timezone=True), nullable=True)
    next_checkpoint_at = Column(DateTime(timezone=True), nullable=True)
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
    memory = relationship("AgentMemory", back_populates="agent", uselist=False, cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="author", foreign_keys="Message.author_agent_id")
    proposals = relationship("Proposal", back_populates="author")
    votes = relationship("Vote", back_populates="agent")
    
    __table_args__ = (
        CheckConstraint("agent_number >= 1 AND agent_number <= 100", name="valid_agent_number"),
        CheckConstraint("tier >= 1 AND tier <= 4", name="valid_tier"),
        CheckConstraint(
            "model_type IN ("
            "'claude-sonnet-4', 'gpt-4o-mini', 'claude-haiku', 'llama-3.3-70b', 'llama-3.1-8b', 'gemini-flash', "
            "'or_gpt_oss_120b', 'or_qwen3_235b_a22b_2507', 'or_deepseek_v3_2', 'or_deepseek_chat_v3_1', "
            "'or_gpt_oss_20b', 'or_qwen3_32b', 'or_mistral_small_3_1_24b', "
            "'or_gpt_oss_20b_free', 'or_qwen3_4b_free', 'or_mistral_small_3_1_24b_free', "
            "'gr_llama_3_1_8b_instant', "
            "'gm_gemini_2_5_flash', 'gm_gemini_2_0_flash', 'gm_gemini_2_0_flash_lite'"
            ")",
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


class AgentMemory(Base):
    """Per-agent long-term memory summary."""
    __tablename__ = "agent_memory"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True)
    summary_text = Column(Text, nullable=False, default="")
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_checkpoint_number = Column(Integer, nullable=False, default=0)

    # Relationships
    agent = relationship("Agent", back_populates="memory")


class EmergenceMetricSnapshot(Base):
    """Persisted daily emergence metrics for trend tracking."""
    __tablename__ = "emergence_metric_snapshots"

    id = Column(Integer, primary_key=True)
    simulation_day = Column(Integer, nullable=False, unique=True)
    window_start_at = Column(DateTime(timezone=True), nullable=False)
    window_end_at = Column(DateTime(timezone=True), nullable=False)

    living_agents = Column(Integer, nullable=False, default=0)
    governance_participants = Column(Integer, nullable=False, default=0)
    governance_participation_rate = Column(DECIMAL(8, 6), nullable=False, default=0)

    coalition_edge_count = Column(Integer, nullable=False, default=0)
    coalition_churn = Column(DECIMAL(8, 6), nullable=True)
    coalition_edge_keys = Column(JSON, nullable=True, default=list)

    inequality_gini = Column(DECIMAL(8, 6), nullable=False, default=0)
    inequality_trend = Column(DECIMAL(8, 6), nullable=True)

    conflict_events = Column(Integer, nullable=False, default=0)
    cooperation_events = Column(Integer, nullable=False, default=0)
    conflict_rate = Column(DECIMAL(8, 6), nullable=False, default=0)
    cooperation_rate = Column(DECIMAL(8, 6), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KpiEvent(Base):
    """Raw KPI instrumentation events from frontend clients."""
    __tablename__ = "kpi_events"

    id = Column(Integer, primary_key=True)
    day_key = Column(Date, nullable=False)
    event_name = Column(String(64), nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    visitor_id = Column(String(128), nullable=False)
    session_id = Column(String(128), nullable=True)
    run_id = Column(String(64), nullable=True)
    event_id = Column(Integer, nullable=True)
    surface = Column(String(64), nullable=True)
    target = Column(String(64), nullable=True)
    path = Column(String(255), nullable=True)
    referrer = Column(String(255), nullable=True)
    event_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("event_name <> ''", name="ck_kpi_events_event_name_nonempty"),
        CheckConstraint("visitor_id <> ''", name="ck_kpi_events_visitor_nonempty"),
    )


class KpiDailyRollup(Base):
    """Daily rollups for growth KPI metrics and conversion rates."""
    __tablename__ = "kpi_daily_rollups"

    day_key = Column(Date, primary_key=True)

    landing_views = Column(Integer, nullable=False, default=0)
    landing_view_visitors = Column(Integer, nullable=False, default=0)
    landing_run_clicks = Column(Integer, nullable=False, default=0)
    landing_run_click_visitors = Column(Integer, nullable=False, default=0)

    run_detail_views = Column(Integer, nullable=False, default=0)
    run_detail_visitors = Column(Integer, nullable=False, default=0)
    replay_starts = Column(Integer, nullable=False, default=0)
    replay_start_visitors = Column(Integer, nullable=False, default=0)
    replay_completions = Column(Integer, nullable=False, default=0)
    replay_completion_visitors = Column(Integer, nullable=False, default=0)

    share_actions = Column(Integer, nullable=False, default=0)
    share_action_visitors = Column(Integer, nullable=False, default=0)
    share_clicks = Column(Integer, nullable=False, default=0)
    share_click_visitors = Column(Integer, nullable=False, default=0)
    shared_link_opens = Column(Integer, nullable=False, default=0)
    shared_link_open_visitors = Column(Integer, nullable=False, default=0)

    landing_to_run_ctr = Column(DECIMAL(8, 6), nullable=False, default=0)
    run_to_replay_start_rate = Column(DECIMAL(8, 6), nullable=False, default=0)
    replay_completion_rate = Column(DECIMAL(8, 6), nullable=False, default=0)
    share_action_rate = Column(DECIMAL(8, 6), nullable=False, default=0)
    shared_link_ctr = Column(DECIMAL(8, 6), nullable=False, default=0)

    d1_cohort_size = Column(Integer, nullable=False, default=0)
    d1_returning_users = Column(Integer, nullable=False, default=0)
    d1_retention_rate = Column(DECIMAL(8, 6), nullable=True)
    d7_cohort_size = Column(Integer, nullable=False, default=0)
    d7_returning_users = Column(Integer, nullable=False, default=0)
    d7_retention_rate = Column(DECIMAL(8, 6), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


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
        UniqueConstraint("enforcement_id", "agent_id", name="uq_enforcement_votes_enforcement_agent"),
        CheckConstraint("vote IN ('support', 'oppose')", name="valid_enforcement_vote"),
    )


class RuntimeConfigOverride(Base):
    """Mutable runtime config overrides for ops/admin controls."""
    __tablename__ = "runtime_config_overrides"

    id = Column(Integer, primary_key=True)
    key = Column(String(120), nullable=False, unique=True)
    value_json = Column(JSON, nullable=False)
    updated_by = Column(String(120), nullable=True)
    reason = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AdminConfigChange(Base):
    """Audit log for admin config changes."""
    __tablename__ = "admin_config_changes"

    id = Column(Integer, primary_key=True)
    key = Column(String(120), nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=False)
    changed_by = Column(String(120), nullable=False)
    environment = Column(String(50), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ArchiveArticle(Base):
    """Long-form archive content managed from Ops UI."""
    __tablename__ = "archive_articles"

    id = Column(Integer, primary_key=True)
    slug = Column(String(160), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    sections = Column(JSON, nullable=False, default=list)
    content_type = Column(String(32), nullable=False, default="approachable_article")
    status_label = Column(String(20), nullable=False, default="observational")
    evidence_completeness = Column(String(20), nullable=False, default="partial")
    tags = Column(JSON, nullable=False, default=list)
    linked_record_ids = Column(JSON, nullable=False, default=list)
    evidence_run_id = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    published_at = Column(Date, nullable=True)
    created_by = Column(String(120), nullable=True)
    updated_by = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="valid_archive_article_status"),
        CheckConstraint(
            "content_type IN ('technical_report', 'approachable_article')",
            name="valid_archive_article_content_type",
        ),
        CheckConstraint(
            "status_label IN ('observational', 'replicated')",
            name="valid_archive_article_status_label",
        ),
        CheckConstraint(
            "evidence_completeness IN ('full', 'partial')",
            name="valid_archive_article_evidence_completeness",
        ),
    )


class RunReportArtifact(Base):
    """Artifact registry for run-scoped report bundle outputs."""
    __tablename__ = "run_report_artifacts"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), nullable=False)
    artifact_type = Column(String(32), nullable=False)
    artifact_format = Column(String(16), nullable=False)
    artifact_path = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="completed")
    template_version = Column(String(64), nullable=True)
    generator_version = Column(String(64), nullable=True)
    metadata_json = Column(JSON, nullable=True, default=dict)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "artifact_type", "artifact_format", name="uq_run_report_artifacts_key"),
        CheckConstraint(
            "artifact_type IN ('technical_report', 'approachable_report', 'planner_report', 'run_summary', 'condition_comparison')",
            name="valid_run_report_artifact_type",
        ),
        CheckConstraint(
            "artifact_format IN ('json', 'markdown')",
            name="valid_run_report_artifact_format",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="valid_run_report_artifact_status",
        ),
    )


class SimulationRun(Base):
    """Metadata registry for simulation runs and season associations."""
    __tablename__ = "simulation_runs"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    run_mode = Column(String(16), nullable=False)
    protocol_version = Column(String(64), nullable=False, default="")
    condition_name = Column(String(120), nullable=True)
    hypothesis_id = Column(String(120), nullable=True)
    season_id = Column(String(64), nullable=True, index=True)
    season_number = Column(Integer, nullable=True, index=True)
    parent_run_id = Column(String(64), ForeignKey("simulation_runs.run_id"), nullable=True)
    transfer_policy_version = Column(String(64), nullable=True)
    epoch_id = Column(String(64), nullable=True, index=True)
    run_class = Column(String(32), nullable=False, default="standard_72h")
    carryover_agent_count = Column(Integer, nullable=False, default=0)
    fresh_agent_count = Column(Integer, nullable=False, default=0)
    protocol_deviation = Column(Boolean, nullable=False, default=False)
    deviation_reason = Column(Text, nullable=True)
    start_reason = Column(Text, nullable=True)
    end_reason = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("run_mode IN ('test', 'real')", name="ck_simulation_runs_run_mode"),
        CheckConstraint(
            "run_class IN ('standard_72h', 'deep_96h', 'special_exploratory')",
            name="ck_simulation_runs_run_class",
        ),
        CheckConstraint(
            "(season_id IS NULL) OR (season_number IS NOT NULL AND season_number >= 1)",
            name="ck_simulation_runs_season_number_when_season_id",
        ),
        CheckConstraint(
            "carryover_agent_count >= 0",
            name="ck_simulation_runs_carryover_agent_count_nonnegative",
        ),
        CheckConstraint(
            "fresh_agent_count >= 0",
            name="ck_simulation_runs_fresh_agent_count_nonnegative",
        ),
    )


class SeasonSnapshot(Base):
    """Transfer snapshot payloads captured from completed season runs."""
    __tablename__ = "season_snapshots"

    id = Column(Integer, primary_key=True)
    run_id = Column(
        String(64),
        ForeignKey("simulation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_type = Column(String(64), nullable=False)
    payload_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("snapshot_type <> ''", name="ck_season_snapshots_snapshot_type_nonempty"),
        Index(
            "idx_season_snapshots_run_id_snapshot_type",
            "run_id",
            "snapshot_type",
        ),
    )


class AgentLineage(Base):
    """Lineage mapping between parent and child agents across seasons."""
    __tablename__ = "agent_lineage"

    id = Column(Integer, primary_key=True)
    season_id = Column(String(64), nullable=False)
    parent_agent_number = Column(Integer, nullable=True)
    child_agent_number = Column(Integer, nullable=False)
    origin = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("season_id", "child_agent_number", name="uq_agent_lineage_season_child"),
        CheckConstraint(
            "parent_agent_number IS NULL OR parent_agent_number >= 1",
            name="ck_agent_lineage_parent_agent_number_positive",
        ),
        CheckConstraint(
            "child_agent_number >= 1",
            name="ck_agent_lineage_child_agent_number_positive",
        ),
        CheckConstraint(
            "origin IN ('carryover', 'fresh')",
            name="ck_agent_lineage_origin",
        ),
        Index(
            "idx_agent_lineage_season_id_parent_agent_number",
            "season_id",
            "parent_agent_number",
        ),
        Index(
            "idx_agent_lineage_season_id_child_agent_number",
            "season_id",
            "child_agent_number",
        ),
    )
