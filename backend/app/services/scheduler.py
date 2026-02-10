"""
Scheduled Tasks - Daily consumption, proposal resolution, etc.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import ensure_utc, now_utc
from app.core.database import SessionLocal
from app.models.models import (
    Agent,
    AgentInventory,
    Proposal,
    Law,
    Event,
    Transaction,
    GlobalResources,
    Message,
    Enforcement,
)
from app.services.archive_drafts import maybe_generate_scheduled_weekly_draft
from app.services.emergence_metrics import persist_completed_day_snapshot
from app.services.run_reports import maybe_generate_scheduled_run_report_backfill
from app.services.runtime_config import runtime_config_service

# Twitter bot integration (optional)
try:
    from app.services.twitter_bot import (
        TweetType,
        tweet_agent_dormant,
        tweet_agent_died,
        tweet_law_passed,
        tweet_notable_quote,
        twitter_bot,
    )
    TWITTER_AVAILABLE = True
except ImportError:
    TWITTER_AVAILABLE = False
    TweetType = None
    tweet_agent_dormant = None
    tweet_agent_died = None
    tweet_law_passed = None
    tweet_notable_quote = None
    twitter_bot = None

logger = logging.getLogger(__name__)

# ============================================================================
# SURVIVAL COST CONFIGURATION
# ============================================================================
# Active agents must pay full survival cost each cycle
ACTIVE_FOOD_COST = Decimal("1.0")
ACTIVE_ENERGY_COST = Decimal("1.0")

# Dormant agents pay reduced survival cost (but NOT zero - scarcity still kills)
DORMANT_FOOD_COST = Decimal("0.25")
DORMANT_ENERGY_COST = Decimal("0.25")

# After this many consecutive cycles of unpaid survival cost, agent dies permanently
DEATH_THRESHOLD = 5

# Quote-scoring keywords tuned for governance/drama stakes.
QUOTE_SALIENCE_KEYWORDS = {
    "alliance",
    "coalition",
    "betray",
    "war",
    "conflict",
    "sanction",
    "exile",
    "proposal",
    "vote",
    "law",
    "crisis",
    "starving",
    "dormant",
    "dead",
    "revive",
    "survive",
    "trade",
    "resources",
}
QUOTE_STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "from",
    "have",
    "will",
    "just",
    "they",
    "your",
    "what",
    "when",
    "where",
    "while",
}


def _twitter_ready() -> bool:
    return bool(TWITTER_AVAILABLE and twitter_bot and getattr(twitter_bot, "enabled", False))


def _with_runtime_metadata(metadata: dict | None = None) -> dict:
    payload = dict(metadata or {})
    runtime = payload.get("runtime")
    runtime_payload = dict(runtime) if isinstance(runtime, dict) else {}

    run_id = str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or "").strip()
    run_mode = str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_MODE") or "").strip()
    if run_id:
        runtime_payload["run_id"] = run_id[:64]
    if run_mode:
        runtime_payload["run_mode"] = run_mode

    if runtime_payload:
        payload["runtime"] = runtime_payload
    return payload


def _score_quote_candidate(text: str) -> int:
    score = 0
    normalized = str(text or "").strip()
    lowered = normalized.lower()
    length = len(normalized)

    if length < 40:
        return 0
    if 80 <= length <= 200:
        score += 2
    elif 60 <= length <= 240:
        score += 1

    if "?" in normalized:
        score += 1
    if "!" in normalized:
        score += 1
    if any(keyword in lowered for keyword in QUOTE_SALIENCE_KEYWORDS):
        score += 3
    if normalized.count('"') >= 2:
        score += 1

    return score


def _is_action_json(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return lowered.startswith("{") and '"action"' in lowered


def _quote_tokens(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", str(text or "").lower())
    return [tok for tok in cleaned.split() if len(tok) >= 3 and tok not in QUOTE_STOPWORDS]


def _quote_fingerprint(text: str) -> str:
    tokens = _quote_tokens(text)
    if not tokens:
        return ""
    # Stable lightweight fingerprint for deterministic dedupe.
    return " ".join(tokens[:24])


def _token_overlap_ratio(text_a: str, text_b: str) -> float:
    a = set(_quote_tokens(text_a))
    b = set(_quote_tokens(text_b))
    if not a or not b:
        return 0.0
    return float(len(a & b)) / float(len(a | b))


def _passes_quote_quality_gate(
    quote_text: str,
    *,
    recent_quotes: list[str],
    max_overlap: float,
) -> bool:
    content = str(quote_text or "").strip()
    if not content:
        return False
    lowered = content.lower()
    if "http://" in lowered or "https://" in lowered:
        return False
    if len(content.split()) < 8:
        return False

    tokens = _quote_tokens(content)
    if not tokens:
        return False
    unique_ratio = float(len(set(tokens))) / float(len(tokens))
    if unique_ratio < 0.45:
        return False

    for prior in recent_quotes:
        if _token_overlap_ratio(content, prior) >= max_overlap:
            return False
    return True


def _estimate_simulation_day(db: Session, ts: datetime | None) -> int:
    when = ensure_utc(ts) or now_utc()
    first_event = db.query(Event).order_by(Event.created_at.asc()).first()
    first_at = ensure_utc(first_event.created_at) if first_event and first_event.created_at else None
    if not first_at or when <= first_at:
        return 1
    day_seconds = max(60, int(getattr(settings, "DAY_LENGTH_MINUTES", 60) or 60) * 60)
    elapsed = max(0.0, (when - first_at).total_seconds())
    return int(elapsed // day_seconds) + 1


def _is_quote_already_published(event_rows: list[Event], message_id: int) -> bool:
    for event in event_rows:
        meta = event.event_metadata or {}
        if not isinstance(meta, dict):
            continue
        if str(meta.get("source") or "") != "notable_quote":
            continue
        existing_message_id = meta.get("message_id")
        try:
            if int(existing_message_id) == int(message_id):
                return True
        except (TypeError, ValueError):
            continue
    return False


async def process_twitter_queue():
    """Flush queued tweets when the rate window allows."""
    if not _twitter_ready():
        return
    await twitter_bot.process_queue()


async def tweet_high_salience_quote():
    """Tweet a high-salience public quote from recent forum activity."""
    if not _twitter_ready() or not tweet_notable_quote or not TweetType:
        return None
    if not twitter_bot.can_tweet_quote():
        return None

    lookback_hours = max(1, int(getattr(settings, "TWITTER_QUOTE_LOOKBACK_HOURS", 6) or 6))
    scan_limit = max(20, int(getattr(settings, "TWITTER_QUOTE_SCAN_LIMIT", 120) or 120))
    min_chars = max(20, int(getattr(settings, "TWITTER_MIN_QUOTE_CHARS", 60) or 60))
    max_chars = max(min_chars, int(getattr(settings, "TWITTER_MAX_QUOTE_CHARS", 220) or 220))
    min_salience = max(1, int(getattr(settings, "TWITTER_MIN_QUOTE_SALIENCE_SCORE", 4) or 4))
    dedupe_days = max(1, int(getattr(settings, "TWITTER_QUOTE_DEDUPE_DAYS", 14) or 14))
    max_overlap = float(getattr(settings, "TWITTER_QUOTE_MAX_TOKEN_OVERLAP", 0.85) or 0.85)
    max_overlap = min(max(0.50, max_overlap), 0.98)

    now_ts = now_utc()
    cutoff = now_ts - timedelta(hours=lookback_hours)
    dedupe_cutoff = now_ts - timedelta(days=dedupe_days)

    db = SessionLocal()
    try:
        recent_tweet_events = (
            db.query(Event)
            .filter(
                Event.event_type == "tweet_posted",
                Event.created_at >= dedupe_cutoff,
            )
            .order_by(Event.created_at.desc())
            .limit(1000)
            .all()
        )
        recent_quote_texts: list[str] = []
        recent_quote_fingerprints: set[str] = set()
        for evt in recent_tweet_events:
            meta = evt.event_metadata or {}
            if not isinstance(meta, dict):
                continue
            if str(meta.get("source") or "") != "notable_quote":
                continue
            quote_text = str(meta.get("quote_text") or "").strip()
            if quote_text:
                recent_quote_texts.append(quote_text)
            fingerprint = str(meta.get("quote_fingerprint") or "").strip()
            if fingerprint:
                recent_quote_fingerprints.add(fingerprint)

        # Also dedupe against queued quote tweets.
        queued_quote_texts = [
            str(item.text or "").strip()
            for item in (twitter_bot.tweet_queue or [])
            if getattr(item, "tweet_type", None) == TweetType.NOTABLE_QUOTE and str(item.text or "").strip()
        ]
        recent_quote_texts.extend(queued_quote_texts)

        messages = (
            db.query(Message)
            .filter(
                Message.message_type.in_(("forum_post", "forum_reply")),
                Message.created_at >= cutoff,
            )
            .order_by(Message.created_at.desc())
            .limit(scan_limit)
            .all()
        )
        if not messages:
            return None

        candidates: list[tuple[int, Message, str]] = []
        for message in messages:
            if _is_quote_already_published(recent_tweet_events, message_id=int(message.id)):
                continue
            content = " ".join(str(message.content or "").split())
            if len(content) < min_chars or _is_action_json(content):
                continue
            if len(content) > max_chars:
                content = f"{content[: max_chars - 3].rstrip()}..."
            fingerprint = _quote_fingerprint(content)
            if not fingerprint or fingerprint in recent_quote_fingerprints:
                continue
            score = _score_quote_candidate(content)
            if score < min_salience:
                continue
            if not _passes_quote_quality_gate(
                content,
                recent_quotes=recent_quote_texts,
                max_overlap=max_overlap,
            ):
                continue
            candidates.append((score, message, content, fingerprint))

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                int(item[0]),
                ensure_utc(item[1].created_at) or now_ts,
            ),
            reverse=True,
        )
        _, best, quote_text, quote_fingerprint = candidates[0]
        author = db.query(Agent).filter(Agent.id == best.author_agent_id).first()
        if not author:
            return None
        day_number = _estimate_simulation_day(db, best.created_at)
    finally:
        db.close()

    success = await tweet_notable_quote(
        quote=quote_text,
        agent_number=int(author.agent_number),
        agent_name=author.display_name,
        day=day_number,
    )
    queued = any(
        item.tweet_type == TweetType.NOTABLE_QUOTE and item.text == quote_text
        for item in (twitter_bot.tweet_queue or [])
    )
    if not success and not queued:
        return None

    db = SessionLocal()
    try:
        db.add(
            Event(
                agent_id=author.id,
                event_type="tweet_posted",
                description=f"Twitter notable quote posted for Agent #{author.agent_number}",
                event_metadata=_with_runtime_metadata({
                    "source": "notable_quote",
                    "status": "sent" if success else "queued",
                    "message_id": int(best.id),
                    "agent_id": int(author.id),
                    "agent_number": int(author.agent_number),
                    "day_number": int(day_number),
                    "quote_fingerprint": quote_fingerprint,
                    "quote_text": quote_text,
                }),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    logger.info(
        "Twitter quote %s: agent=%s message_id=%s score=%s",
        "sent" if success else "queued",
        author.agent_number,
        best.id,
        candidates[0][0],
    )
    return {"queued": not success, "message_id": int(best.id), "agent_number": int(author.agent_number)}


async def process_daily_consumption():
    """
    Process daily resource consumption for all living agents.
    
    SURVIVAL MECHANICS:
    - Active agents: Pay 1 food + 1 energy per cycle
    - If active agent can't pay → goes DORMANT
    - Dormant agents: Pay 0.25 food + 0.25 energy per cycle (reduced, not zero)
    - If dormant agent can't pay reduced cost → starvation_cycles += 1
    - If starvation_cycles >= DEATH_THRESHOLD → PERMANENT DEATH
    - Death is irreversible. Agent is removed from simulation.
    
    This ensures scarcity is the root cause of death, not just "sleeping too long".
    """
    db = SessionLocal()
    
    try:
        logger.info("Processing daily survival cycle...")
        
        # Get all living agents (both active and dormant)
        query = db.query(Agent).filter(or_(Agent.status == "active", Agent.status == "dormant"))

        # Dev/test mode: if we cap the simulation to N agents, don't kill the rest via survival ticks.
        # This keeps "SIMULATION_MAX_AGENTS=20" as a cheap sandbox without destroying the full seeded world.
        if settings.SIMULATION_MAX_AGENTS and settings.SIMULATION_MAX_AGENTS > 0:
            query = query.filter(Agent.agent_number <= settings.SIMULATION_MAX_AGENTS)

        living_agents = query.all()
        
        # Track outcomes
        agents_consumed = []  # Paid full cost
        agents_made_dormant = []  # Active → Dormant
        agents_starving = []  # Dormant & can't pay reduced cost
        agents_died = []  # Reached death threshold
        agents_recovered = []  # Dormant but paid cost (stable)
        
        for agent in living_agents:
            # Get inventory
            food_inv = db.query(AgentInventory).filter(
                AgentInventory.agent_id == agent.id,
                AgentInventory.resource_type == "food"
            ).first()
            
            energy_inv = db.query(AgentInventory).filter(
                AgentInventory.agent_id == agent.id,
                AgentInventory.resource_type == "energy"
            ).first()
            
            food_amount = Decimal(str(food_inv.quantity)) if food_inv else Decimal("0")
            energy_amount = Decimal(str(energy_inv.quantity)) if energy_inv else Decimal("0")
            
            agent_name = agent.display_name or f"Agent #{agent.agent_number}"
            
            # ================================================================
            # ACTIVE AGENT PROCESSING
            # ================================================================
            if agent.status == "active":
                can_pay_food = food_amount >= ACTIVE_FOOD_COST
                can_pay_energy = energy_amount >= ACTIVE_ENERGY_COST
                
                if can_pay_food and can_pay_energy:
                    # Pay full survival cost - stays active
                    food_inv.quantity -= ACTIVE_FOOD_COST
                    energy_inv.quantity -= ACTIVE_ENERGY_COST
                    
                    # Reset starvation counter (agent is well-fed)
                    agent.starvation_cycles = 0
                    
                    # Record transactions
                    for resource_type, amount in [("food", ACTIVE_FOOD_COST), ("energy", ACTIVE_ENERGY_COST)]:
                        transaction = Transaction(
                            from_agent_id=agent.id,
                            resource_type=resource_type,
                            amount=amount,
                            transaction_type="survival_consumption"
                        )
                        db.add(transaction)
                    
                    agents_consumed.append(agent.id)
                    
                else:
                    # Can't pay full cost → GO DORMANT
                    agent.status = "dormant"
                    reason = "lack of food" if not can_pay_food else "lack of energy"
                    
                    agents_made_dormant.append((agent.id, agent.agent_number, agent.display_name, reason))
                    
                    event = Event(
                        agent_id=agent.id,
                        event_type="became_dormant",
                        description=f"{agent_name} went dormant due to {reason}",
                        event_metadata=_with_runtime_metadata({
                            "reason": reason, 
                            "food": float(food_amount), 
                            "energy": float(energy_amount)
                        }),
                    )
                    db.add(event)
                    
                    # Tweet about dormancy
                    if _twitter_ready() and tweet_agent_dormant:
                        asyncio.create_task(tweet_agent_dormant(
                            agent.agent_number,
                            agent.display_name,
                            reason
                        ))
                    
                    logger.info(f"⚠️ {agent_name} went DORMANT ({reason})")
            
            # ================================================================
            # DORMANT AGENT PROCESSING
            # ================================================================
            elif agent.status == "dormant":
                can_pay_reduced_food = food_amount >= DORMANT_FOOD_COST
                can_pay_reduced_energy = energy_amount >= DORMANT_ENERGY_COST
                
                if can_pay_reduced_food and can_pay_reduced_energy:
                    # Pay reduced survival cost - stays dormant but stable
                    if food_inv:
                        food_inv.quantity -= DORMANT_FOOD_COST
                    if energy_inv:
                        energy_inv.quantity -= DORMANT_ENERGY_COST
                    
                    # Starvation counter doesn't increase (agent is surviving)
                    # But it also doesn't reset - need to become active for that
                    
                    # Record transactions
                    for resource_type, amount in [("food", DORMANT_FOOD_COST), ("energy", DORMANT_ENERGY_COST)]:
                        transaction = Transaction(
                            from_agent_id=agent.id,
                            resource_type=resource_type,
                            amount=amount,
                            transaction_type="dormant_survival"
                        )
                        db.add(transaction)
                    
                    agents_recovered.append(agent.id)
                    
                else:
                    # CAN'T PAY EVEN REDUCED COST - STARVATION WORSENS
                    agent.starvation_cycles += 1
                    
                    agents_starving.append((
                        agent.id, 
                        agent.agent_number, 
                        agent.display_name,
                        agent.starvation_cycles
                    ))
                    
                    logger.warning(
                        f"💀 {agent_name} cannot pay survival cost! "
                        f"Starvation cycle {agent.starvation_cycles}/{DEATH_THRESHOLD}"
                    )
                    
                    # Check for PERMANENT DEATH
                    if agent.starvation_cycles >= DEATH_THRESHOLD:
                        # ========================================
                        # PERMANENT DEATH - NO RESURRECTION
                        # ========================================
                        agent.status = "dead"
                        agent.died_at = datetime.utcnow()
                        agent.death_cause = "starvation"
                        
                        agents_died.append((
                            agent.id,
                            agent.agent_number,
                            agent.display_name,
                            agent.starvation_cycles
                        ))
                        
                        # Create death event
                        event = Event(
                            agent_id=agent.id,
                            event_type="agent_died",
                            description=f"☠️ {agent_name} has DIED from starvation after {agent.starvation_cycles} cycles without resources",
                            event_metadata=_with_runtime_metadata({
                                "cause": "starvation",
                                "starvation_cycles": agent.starvation_cycles,
                                "final_food": float(food_amount),
                                "final_energy": float(energy_amount)
                            }),
                        )
                        db.add(event)
                        
                        # Tweet about death
                        if _twitter_ready() and tweet_agent_died:
                            asyncio.create_task(tweet_agent_died(
                                agent.agent_number,
                                agent.display_name,
                                "starvation",
                                agent.starvation_cycles
                            ))
                        
                        logger.error(f"☠️☠️☠️ {agent_name} HAS DIED PERMANENTLY ☠️☠️☠️")
                    
                    else:
                        # Not dead yet, but getting closer
                        event = Event(
                            agent_id=agent.id,
                            event_type="starvation_warning",
                            description=f"⚠️ {agent_name} is starving! Cycle {agent.starvation_cycles}/{DEATH_THRESHOLD} until death",
                            event_metadata=_with_runtime_metadata({
                                "starvation_cycles": agent.starvation_cycles,
                                "cycles_until_death": DEATH_THRESHOLD - agent.starvation_cycles,
                                "food": float(food_amount),
                                "energy": float(energy_amount)
                            }),
                        )
                        db.add(event)
        
        # Update global consumption stats
        total_consumed = len(agents_consumed) + len(agents_recovered)
        for resource_type in ["food", "energy"]:
            global_res = db.query(GlobalResources).filter(
                GlobalResources.resource_type == resource_type
            ).first()
            
            if global_res:
                global_res.consumed_today = Decimal(str(total_consumed))
        
        db.commit()
        
        # Log summary
        logger.info(
            f"Survival cycle complete: "
            f"{len(agents_consumed)} active (fed), "
            f"{len(agents_recovered)} dormant (stable), "
            f"{len(agents_made_dormant)} became dormant, "
            f"{len(agents_starving)} starving, "
            f"{len(agents_died)} DIED"
        )
        
        return {
            "active_fed": len(agents_consumed),
            "dormant_stable": len(agents_recovered),
            "became_dormant": len(agents_made_dormant),
            "dormant_agents": agents_made_dormant,
            "starving": len(agents_starving),
            "starving_agents": agents_starving,
            "died": len(agents_died),
            "dead_agents": agents_died,
        }
        
    except Exception as e:
        logger.error(f"Error in survival cycle: {e}")
        db.rollback()
        raise
        
    finally:
        db.close()


async def resolve_expired_proposals():
    """
    Resolve proposals whose voting period has ended.
    Run this every few minutes.
    """
    db = SessionLocal()
    
    try:
        logger.info("Checking for expired proposals...")
        
        now = datetime.utcnow()
        
        expired_proposals = db.query(Proposal).filter(
            Proposal.status == "active",
            Proposal.voting_closes_at <= now
        ).all()
        
        results = []
        
        for proposal in expired_proposals:
            # Calculate result
            total_votes = proposal.votes_for + proposal.votes_against
            
            if total_votes == 0:
                # No votes = failed
                proposal.status = "expired"
                result = "expired"
            elif proposal.votes_for > proposal.votes_against:
                # Majority yes = passed
                proposal.status = "passed"
                result = "passed"
                
                # If it's a law proposal, create the law
                if proposal.proposal_type == "law":
                    law = Law(
                        proposal_id=proposal.id,
                        title=proposal.title,
                        description=proposal.description,
                        author_agent_id=proposal.author_agent_id,
                        active=True,
                    )
                    db.add(law)
                    
                    event = Event(
                        event_type="law_passed",
                        description=f"New law enacted: {proposal.title}",
                        event_metadata=_with_runtime_metadata({
                            "proposal_id": proposal.id,
                            "votes_for": proposal.votes_for,
                            "votes_against": proposal.votes_against,
                        }),
                    )
                    db.add(event)
                    
                    # Tweet about the new law
                    if _twitter_ready() and tweet_law_passed:
                        asyncio.create_task(tweet_law_passed(
                            proposal.title,
                            proposal.id,
                            proposal.votes_for,
                            proposal.votes_against,
                            proposal.description or ""
                        ))
            else:
                # Majority no or tie = failed
                proposal.status = "failed"
                result = "failed"
            
            proposal.resolved_at = now
            
            # Log the result
            event = Event(
                event_type="proposal_resolved",
                description=f"Proposal '{proposal.title}' {result} ({proposal.votes_for}/{proposal.votes_against})",
                event_metadata=_with_runtime_metadata({
                    "proposal_id": proposal.id,
                    "result": result,
                    "votes_for": proposal.votes_for,
                    "votes_against": proposal.votes_against,
                    "votes_abstain": proposal.votes_abstain,
                }),
            )
            db.add(event)
            
            results.append({
                "proposal_id": proposal.id,
                "title": proposal.title,
                "result": result,
            })
        
        db.commit()
        
        if results:
            logger.info(f"Resolved {len(results)} proposals: {results}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error resolving proposals: {e}")
        db.rollback()
        raise
        
    finally:
        db.close()


async def resolve_expired_enforcements():
    """
    Resolve enforcement actions whose voting windows have ended.
    Pending enforcements with insufficient support are rejected at expiry.
    """
    db = SessionLocal()

    try:
        logger.info("Checking for expired enforcements...")
        now = now_utc()

        expired_enforcements = db.query(Enforcement).filter(
            Enforcement.status == "pending",
            Enforcement.voting_closes_at <= now,
        ).all()

        results = []
        for enforcement in expired_enforcements:
            target_name = enforcement.target.display_name or f"Agent #{enforcement.target.agent_number}"
            enforcement.status = "rejected"

            event = Event(
                event_type="enforcement_expired",
                description=(
                    f"⚖️ Enforcement #{enforcement.id} against {target_name} expired without enough support "
                    f"({enforcement.support_votes}/{enforcement.votes_required} support, "
                    f"{enforcement.oppose_votes} oppose)"
                ),
                event_metadata=_with_runtime_metadata({
                    "enforcement_id": enforcement.id,
                    "target_agent_number": enforcement.target.agent_number,
                    "enforcement_type": enforcement.enforcement_type,
                    "support_votes": enforcement.support_votes,
                    "oppose_votes": enforcement.oppose_votes,
                    "votes_required": enforcement.votes_required,
                    "result": "expired_rejected",
                }),
            )
            db.add(event)

            results.append({
                "enforcement_id": enforcement.id,
                "result": "expired_rejected",
            })

        db.commit()

        if results:
            logger.info(f"Resolved {len(results)} expired enforcements: {results}")

        return results

    except Exception as e:
        logger.error(f"Error resolving enforcements: {e}")
        db.rollback()
        raise

    finally:
        db.close()


async def reset_daily_stats():
    """
    Reset daily production/consumption counters.
    Run at the start of each simulation day.
    """
    db = SessionLocal()
    
    try:
        global_resources = db.query(GlobalResources).all()
        
        for gr in global_resources:
            gr.produced_today = Decimal("0")
            gr.consumed_today = Decimal("0")
        
        db.commit()
        logger.info("Daily stats reset")
        
    finally:
        db.close()


class SchedulerRunner:
    """Manages scheduled tasks."""
    
    def __init__(self):
        self.running = False
        self.tasks = []
    
    async def start(self, day_length_minutes: int = 60):
        """Start the scheduler."""
        self.running = True
        
        # Proposal resolution every 5 minutes
        self.tasks.append(
            asyncio.create_task(self._run_periodic(resolve_expired_proposals, 300))
        )

        # Enforcement resolution every 5 minutes
        self.tasks.append(
            asyncio.create_task(self._run_periodic(resolve_expired_enforcements, 300))
        )
        
        # Daily consumption every day_length_minutes
        self.tasks.append(
            asyncio.create_task(self._run_periodic(process_daily_consumption, day_length_minutes * 60))
        )
        
        # Daily stats reset
        self.tasks.append(
            asyncio.create_task(self._run_periodic(reset_daily_stats, day_length_minutes * 60))
        )

        # Persist one emergence metrics snapshot per completed simulation day.
        self.tasks.append(
            asyncio.create_task(self._run_periodic(persist_completed_day_snapshot, day_length_minutes * 60))
        )

        # Keep queued tweets moving through rate windows.
        self.tasks.append(
            asyncio.create_task(self._run_periodic(process_twitter_queue, 60))
        )

        # Emit a capped stream of high-salience public quotes for social growth.
        quote_interval_minutes = max(
            1,
            int(getattr(settings, "TWITTER_QUOTE_CHECK_INTERVAL_MINUTES", 10) or 10),
        )
        self.tasks.append(
            asyncio.create_task(self._run_periodic(tweet_high_salience_quote, quote_interval_minutes * 60))
        )

        # Weekly archive draft auto-generation for operator review.
        draft_check_minutes = max(
            5,
            int(getattr(settings, "ARCHIVE_WEEKLY_DRAFT_CHECK_INTERVAL_MINUTES", 60) or 60),
        )
        self.tasks.append(
            asyncio.create_task(self._run_periodic(maybe_generate_scheduled_weekly_draft, draft_check_minutes * 60))
        )

        # Scheduled run-report backfill for missing closeout bundles.
        report_backfill_minutes = max(
            5,
            int(getattr(settings, "RUN_REPORT_BACKFILL_CHECK_INTERVAL_MINUTES", 60) or 60),
        )
        self.tasks.append(
            asyncio.create_task(
                self._run_periodic(
                    maybe_generate_scheduled_run_report_backfill,
                    report_backfill_minutes * 60,
                )
            )
        )
        
        logger.info(f"Scheduler started (day length: {day_length_minutes} minutes)")
    
    async def stop(self):
        """Stop the scheduler."""
        self.running = False
        
        for task in self.tasks:
            task.cancel()
        
        self.tasks.clear()
        logger.info("Scheduler stopped")
    
    async def _run_periodic(self, func, interval_seconds: int):
        """Run a function periodically."""
        while self.running:
            try:
                await func()
            except Exception as e:
                logger.error(f"Error in scheduled task {func.__name__}: {e}")
            
            await asyncio.sleep(interval_seconds)


# Singleton scheduler
scheduler = SchedulerRunner()
