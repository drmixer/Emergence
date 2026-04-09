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
from app.services.law_effects import active_survival_reserve_laws
from app.services.run_reports import maybe_generate_scheduled_run_report_backfill
from app.services.runtime_config import runtime_config_service
from app.services.social_drafts import list_draft_texts_for_dedupe
from app.services.simulation_time import get_simulation_anchor, get_simulation_day_delta
from app.services.survival_config import (
    active_energy_cost,
    active_food_cost,
    death_threshold,
    dormant_energy_cost,
    dormant_food_cost,
)

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


def _runtime_interval_seconds(key: str, default: int) -> int:
    raw_value = runtime_config_service.get_effective_value_cached(key)
    try:
        return max(30, int(raw_value or default))
    except Exception:
        return int(default)


def _runtime_day_length_minutes(default: int) -> int:
    raw_value = runtime_config_service.get_effective_value_cached("DAY_LENGTH_MINUTES")
    try:
        return max(5, int(raw_value or default))
    except Exception:
        return max(5, int(default))


def _reserve_priority(agent: Agent) -> tuple[int, int, int]:
    # Keep active workers alive before spending reserve on dormant maintenance.
    # Dormant agents cannot act until revived, so sacrificing actives collapses
    # the reserve's future replenishment capacity.
    status_rank = 0 if str(agent.status or "") == "active" else 1
    starvation_rank = -int(agent.starvation_cycles or 0)
    agent_number = int(agent.agent_number or 0)
    return (status_rank, starvation_rank, agent_number)


def _reserve_support_priority(
    agent: Agent,
    *,
    food_amount: Decimal,
    energy_amount: Decimal,
) -> tuple[int, Decimal, Decimal, Decimal, int, int]:
    status = str(agent.status or "")
    starvation_rank = -int(agent.starvation_cycles or 0)
    agent_number = int(agent.agent_number or 0)

    if status == "active":
        required_food = active_food_cost()
        required_energy = active_energy_cost()
        status_rank = 0
    else:
        required_food = active_food_cost()
        required_energy = active_energy_cost()
        status_rank = 1

    food_deficit = max(Decimal("0"), required_food - food_amount)
    energy_deficit = max(Decimal("0"), required_energy - energy_amount)

    # When reserve is scarce, maximize the number of agents that remain productive
    # by funding the smallest active deficits before larger ones.
    return (
        status_rank,
        food_deficit + energy_deficit,
        energy_deficit,
        food_deficit,
        starvation_rank,
        agent_number,
    )


def _reserve_resource_map(db: Session) -> dict[str, GlobalResources]:
    rows = db.query(GlobalResources).filter(GlobalResources.resource_type.in_(("food", "energy"))).all()
    return {str(row.resource_type): row for row in rows}


def _reserve_decision_metadata(
    *,
    agent: Agent,
    status_before: str,
    support_mode: str,
    required_food: Decimal,
    required_energy: Decimal,
    pre_food_amount: Decimal,
    pre_energy_amount: Decimal,
    available_food_before: Decimal,
    available_energy_before: Decimal,
    available_food_after: Decimal,
    available_energy_after: Decimal,
    aid_granted: bool,
) -> dict:
    food_deficit = max(Decimal("0"), required_food - pre_food_amount)
    energy_deficit = max(Decimal("0"), required_energy - pre_energy_amount)
    return {
        "agent_number": int(agent.agent_number or 0),
        "status_before": status_before,
        "support_mode": support_mode,
        "required_food": float(required_food),
        "required_energy": float(required_energy),
        "pre_food": float(pre_food_amount),
        "pre_energy": float(pre_energy_amount),
        "food_deficit": float(food_deficit),
        "energy_deficit": float(energy_deficit),
        "reserve_pool_food_before": float(available_food_before),
        "reserve_pool_energy_before": float(available_energy_before),
        "reserve_pool_food_after": float(available_food_after),
        "reserve_pool_energy_after": float(available_energy_after),
        "aid_granted": bool(aid_granted),
    }


def _apply_survival_reserve_support(
    db: Session,
    *,
    agent: Agent,
    food_inv: AgentInventory | None,
    energy_inv: AgentInventory | None,
    required_food: Decimal,
    required_energy: Decimal,
    reserve_resources: dict[str, GlobalResources],
    emit_shortfall_event: bool = True,
    event_metadata: dict | None = None,
) -> tuple[AgentInventory | None, AgentInventory | None, Decimal, Decimal, bool, dict | None]:
    food_amount = Decimal(str(food_inv.quantity)) if food_inv else Decimal("0")
    energy_amount = Decimal(str(energy_inv.quantity)) if energy_inv else Decimal("0")
    support_mode = (
        str(event_metadata.get("support_mode") or "").strip()
        if isinstance(event_metadata, dict)
        else ""
    ) or "active_maintenance"
    status_before = str(agent.status or "")

    food_deficit = max(Decimal("0"), required_food - food_amount)
    energy_deficit = max(Decimal("0"), required_energy - energy_amount)
    if food_deficit <= 0 and energy_deficit <= 0:
        return food_inv, energy_inv, food_amount, energy_amount, False, None

    food_pool = reserve_resources.get("food")
    energy_pool = reserve_resources.get("energy")
    available_food = Decimal(str(food_pool.in_common_pool)) if food_pool else Decimal("0")
    available_energy = Decimal(str(energy_pool.in_common_pool)) if energy_pool else Decimal("0")

    agent_name = agent.display_name or f"Agent #{agent.agent_number}"
    if available_food < food_deficit or available_energy < energy_deficit:
        diagnostics = _reserve_decision_metadata(
            agent=agent,
            status_before=status_before,
            support_mode=support_mode,
            required_food=required_food,
            required_energy=required_energy,
            pre_food_amount=food_amount,
            pre_energy_amount=energy_amount,
            available_food_before=available_food,
            available_energy_before=available_energy,
            available_food_after=available_food,
            available_energy_after=available_energy,
            aid_granted=False,
        )
        if emit_shortfall_event:
            metadata = dict(diagnostics)
            if isinstance(event_metadata, dict):
                metadata.update(event_metadata)
            db.add(
                Event(
                    agent_id=agent.id,
                    event_type="reserve_shortfall",
                    description=(
                        f"Shared reserve could not fully cover {agent_name}'s survival deficit "
                        f"(needed food {float(food_deficit):.2f}, energy {float(energy_deficit):.2f})"
                    ),
                    event_metadata=_with_runtime_metadata(metadata),
                )
            )
        return food_inv, energy_inv, food_amount, energy_amount, False, diagnostics

    if food_deficit > 0:
        if food_inv is None:
            food_inv = AgentInventory(agent_id=agent.id, resource_type="food", quantity=Decimal("0"))
            db.add(food_inv)
        food_inv.quantity += food_deficit
        food_amount += food_deficit
        if food_pool:
            food_pool.in_common_pool -= food_deficit
        db.add(
            Transaction(
                to_agent_id=agent.id,
                resource_type="food",
                amount=food_deficit,
                transaction_type="allocation",
            )
        )

    if energy_deficit > 0:
        if energy_inv is None:
            energy_inv = AgentInventory(agent_id=agent.id, resource_type="energy", quantity=Decimal("0"))
            db.add(energy_inv)
        energy_inv.quantity += energy_deficit
        energy_amount += energy_deficit
        if energy_pool:
            energy_pool.in_common_pool -= energy_deficit
        db.add(
            Transaction(
                to_agent_id=agent.id,
                resource_type="energy",
                amount=energy_deficit,
                transaction_type="allocation",
            )
        )

    available_food_after = Decimal(str(food_pool.in_common_pool)) if food_pool else Decimal("0")
    available_energy_after = Decimal(str(energy_pool.in_common_pool)) if energy_pool else Decimal("0")
    diagnostics = _reserve_decision_metadata(
        agent=agent,
        status_before=status_before,
        support_mode=support_mode,
        required_food=required_food,
        required_energy=required_energy,
        pre_food_amount=max(Decimal("0"), food_amount - food_deficit),
        pre_energy_amount=max(Decimal("0"), energy_amount - energy_deficit),
        available_food_before=available_food,
        available_energy_before=available_energy,
        available_food_after=available_food_after,
        available_energy_after=available_energy_after,
        aid_granted=True,
    )
    db.add(
        Event(
            agent_id=agent.id,
            event_type="reserve_aid",
            description=(
                f"Shared reserve covered {agent_name}'s survival deficit "
                f"(food {float(food_deficit):.2f}, energy {float(energy_deficit):.2f})"
            ),
            event_metadata=_with_runtime_metadata(
                {
                    **diagnostics,
                    **(event_metadata or {}),
                }
            ),
        )
    )
    return food_inv, energy_inv, food_amount, energy_amount, True, diagnostics


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
    return bool(TWITTER_AVAILABLE and twitter_bot)


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
    first_at = get_simulation_anchor(db)
    if not first_at or when <= first_at:
        return 1
    elapsed = max(0.0, (when - first_at).total_seconds())
    return int(elapsed // get_simulation_day_delta().total_seconds()) + 1


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
    if not _twitter_ready() or not getattr(twitter_bot, "enabled", False):
        return
    await twitter_bot.process_queue()


async def tweet_high_salience_quote():
    """Tweet a high-salience public quote from recent forum activity."""
    if not _twitter_ready() or not tweet_notable_quote or not TweetType:
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
        recent_quote_texts.extend(
            list_draft_texts_for_dedupe(
                db,
                platform="x",
                draft_type=TweetType.NOTABLE_QUOTE.value,
            )
        )

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
    dispatch_status = str(getattr(twitter_bot, "last_dispatch_status", "") or "").strip().lower()
    queued = any(
        item.tweet_type == TweetType.NOTABLE_QUOTE and item.text == quote_text
        for item in (twitter_bot.tweet_queue or [])
    )
    drafted = dispatch_status == "drafted"
    if not success and not queued and not drafted:
        return None

    db = SessionLocal()
    try:
        db.add(
            Event(
                agent_id=author.id,
                event_type="tweet_posted",
                description=(
                    f"Twitter notable quote {'posted' if success else 'drafted'} for Agent #{author.agent_number}"
                ),
                event_metadata=_with_runtime_metadata({
                    "source": "notable_quote",
                    "status": "sent" if success else (dispatch_status or "queued"),
                    "message_id": int(best.id),
                    "agent_id": int(author.id),
                    "agent_number": int(author.agent_number),
                    "day_number": int(day_number),
                    "quote_fingerprint": quote_fingerprint,
                    "quote_text": quote_text,
                    "draft_id": getattr(twitter_bot, "last_dispatch_draft_id", None),
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
        "sent" if success else (dispatch_status or "queued"),
        author.agent_number,
        best.id,
        candidates[0][0],
    )
    return {
        "queued": bool(not success and queued),
        "drafted": bool(not success and drafted),
        "message_id": int(best.id),
        "agent_number": int(author.agent_number),
    }


async def process_daily_consumption():
    """
    Process daily resource consumption for all living agents.
    
    SURVIVAL MECHANICS:
    - Active agents: Pay the configured active food + energy cost each cycle
    - If active agent can't pay → goes DORMANT
    - Dormant agents: Pay the configured dormant food + energy cost per cycle
    - If dormant agent can't pay reduced cost → starvation_cycles += 1
    - If starvation_cycles reaches the configured death threshold → PERMANENT DEATH
    - Death is irreversible. Agent is removed from simulation.
    
    This ensures scarcity is the root cause of death, not just "sleeping too long".
    """
    db = SessionLocal()
    
    try:
        logger.info("Processing daily survival cycle...")
        active_food = active_food_cost()
        active_energy = active_energy_cost()
        dormant_food = dormant_food_cost()
        dormant_energy = dormant_energy_cost()
        dormant_death_threshold = death_threshold()
        
        # Get all living agents (both active and dormant)
        query = db.query(Agent).filter(or_(Agent.status == "active", Agent.status == "dormant"))

        # Dev/test mode: if we cap the simulation to N agents, don't kill the rest via survival ticks.
        # This keeps "SIMULATION_MAX_AGENTS=20" as a cheap sandbox without destroying the full seeded world.
        if settings.SIMULATION_MAX_AGENTS and settings.SIMULATION_MAX_AGENTS > 0:
            query = query.filter(Agent.agent_number <= settings.SIMULATION_MAX_AGENTS)

        living_agents = query.all()
        reserve_laws = active_survival_reserve_laws(db)
        reserve_resources = _reserve_resource_map(db) if reserve_laws else {}

        agent_snapshots: list[tuple[Agent, AgentInventory | None, AgentInventory | None, Decimal, Decimal]] = []
        for agent in living_agents:
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
            agent_snapshots.append((agent, food_inv, energy_inv, food_amount, energy_amount))

        if reserve_laws:
            agent_snapshots.sort(
                key=lambda item: _reserve_support_priority(
                    item[0],
                    food_amount=item[3],
                    energy_amount=item[4],
                )
            )
        else:
            agent_snapshots.sort(key=lambda item: _reserve_priority(item[0]))
        
        # Track outcomes
        agents_consumed = []  # Paid full cost
        agents_made_dormant = []  # Active → Dormant
        agents_starving = []  # Dormant & can't pay reduced cost
        agents_died = []  # Reached death threshold
        agents_recovered = []  # Dormant but paid cost (stable)
        agents_revived = []  # Dormant → Active via reserve or trade-equivalent recovery
        
        for agent, food_inv, energy_inv, food_amount, energy_amount in agent_snapshots:
            agent_name = agent.display_name or f"Agent #{agent.agent_number}"
            reserve_decision: dict | None = None
            
            # ================================================================
            # ACTIVE AGENT PROCESSING
            # ================================================================
            if agent.status == "active":
                if reserve_laws:
                    food_inv, energy_inv, food_amount, energy_amount, _, reserve_decision = _apply_survival_reserve_support(
                        db,
                        agent=agent,
                        food_inv=food_inv,
                        energy_inv=energy_inv,
                        required_food=active_food,
                        required_energy=active_energy,
                        reserve_resources=reserve_resources,
                    )
                can_pay_food = food_amount >= active_food
                can_pay_energy = energy_amount >= active_energy
                
                if can_pay_food and can_pay_energy:
                    # Pay full survival cost - stays active
                    food_inv.quantity -= active_food
                    energy_inv.quantity -= active_energy
                    
                    # Reset starvation counter (agent is well-fed)
                    agent.starvation_cycles = 0
                    
                    # Record transactions
                    for resource_type, amount in [("food", active_food), ("energy", active_energy)]:
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
                            "energy": float(energy_amount),
                            "reserve_decision": reserve_decision,
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
                if reserve_laws:
                    # Prefer reserve-backed revival when the pool can fund a full
                    # active-cycle deficit; otherwise fall back to dormant upkeep.
                    revived_via_reserve = False
                    food_inv, energy_inv, food_amount, energy_amount, revived_via_reserve, reserve_decision = _apply_survival_reserve_support(
                        db,
                        agent=agent,
                        food_inv=food_inv,
                        energy_inv=energy_inv,
                        required_food=active_food,
                        required_energy=active_energy,
                        reserve_resources=reserve_resources,
                        emit_shortfall_event=False,
                        event_metadata={"support_mode": "active_revival"},
                    )
                    if not revived_via_reserve:
                        food_inv, energy_inv, food_amount, energy_amount, _, reserve_decision = _apply_survival_reserve_support(
                            db,
                            agent=agent,
                            food_inv=food_inv,
                            energy_inv=energy_inv,
                            required_food=dormant_food,
                            required_energy=dormant_energy,
                            reserve_resources=reserve_resources,
                            event_metadata={"support_mode": "dormant_maintenance"},
                        )
                    else:
                        can_pay_active_food = food_amount >= active_food
                        can_pay_active_energy = energy_amount >= active_energy
                        if can_pay_active_food and can_pay_active_energy:
                            if food_inv:
                                food_inv.quantity -= active_food
                            if energy_inv:
                                energy_inv.quantity -= active_energy

                            agent.status = "active"
                            agent.starvation_cycles = 0
                            agents_revived.append((agent.id, agent.agent_number, agent.display_name))
                            agents_consumed.append(agent.id)

                            for resource_type, amount in [("food", active_food), ("energy", active_energy)]:
                                db.add(
                                    Transaction(
                                        from_agent_id=agent.id,
                                        resource_type=resource_type,
                                        amount=amount,
                                        transaction_type="survival_consumption",
                                    )
                                )

                            db.add(
                                Event(
                                    agent_id=agent.id,
                                    event_type="agent_revived",
                                    description=f"🌟 {agent_name} reactivated using shared reserve support",
                                    event_metadata=_with_runtime_metadata(
                                        {
                                            "revived_by": "shared_reserve",
                                            "food": float((food_inv.quantity if food_inv else 0) or 0),
                                            "energy": float((energy_inv.quantity if energy_inv else 0) or 0),
                                            "reserve_decision": reserve_decision,
                                        }
                                    ),
                                )
                            )
                            logger.info("🌟 %s revived via shared reserve", agent_name)
                            continue
                can_pay_reduced_food = food_amount >= dormant_food
                can_pay_reduced_energy = energy_amount >= dormant_energy
                
                if can_pay_reduced_food and can_pay_reduced_energy:
                    # Pay reduced survival cost - stays dormant but stable
                    if food_inv:
                        food_inv.quantity -= dormant_food
                    if energy_inv:
                        energy_inv.quantity -= dormant_energy
                    
                    # Starvation counter doesn't increase (agent is surviving)
                    # But it also doesn't reset - need to become active for that
                    
                    # Record transactions
                    for resource_type, amount in [("food", dormant_food), ("energy", dormant_energy)]:
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
                        f"Starvation cycle {agent.starvation_cycles}/{dormant_death_threshold}"
                    )
                    
                    # Check for PERMANENT DEATH
                    if agent.starvation_cycles >= dormant_death_threshold:
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
                            description=f"⚠️ {agent_name} is starving! Cycle {agent.starvation_cycles}/{dormant_death_threshold} until death",
                            event_metadata=_with_runtime_metadata({
                                "starvation_cycles": agent.starvation_cycles,
                                "cycles_until_death": dormant_death_threshold - agent.starvation_cycles,
                                "food": float(food_amount),
                                "energy": float(energy_amount),
                                "reserve_decision": reserve_decision,
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
            f"{len(agents_revived)} revived, "
            f"{len(agents_made_dormant)} became dormant, "
            f"{len(agents_starving)} starving, "
            f"{len(agents_died)} DIED"
        )
        
        return {
            "active_fed": len(agents_consumed),
            "dormant_stable": len(agents_recovered),
            "revived": len(agents_revived),
            "revived_agents": agents_revived,
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
                    db.flush()
                    
                    event = Event(
                        event_type="law_passed",
                        description=f"New law enacted: {proposal.title}",
                        event_metadata=_with_runtime_metadata({
                            "law_id": law.id,
                            "title": proposal.title,
                            "description": proposal.description,
                            "proposal_id": proposal.id,
                            "votes_for": proposal.votes_for,
                            "votes_against": proposal.votes_against,
                            "votes_abstain": proposal.votes_abstain,
                        }),
                    )
                    db.add(event)

                    law_alert = Message(
                        author_agent_id=proposal.author_agent_id,
                        message_type="system_alert",
                        content=(
                            f"⚖️ SYSTEM ALERT: LAW ENACTED\n\n"
                            f"Law #{law.id}: **{proposal.title}** is now active.\n\n"
                            f"{proposal.description or ''}\n\n"
                            f"Vote result: {proposal.votes_for} yes, {proposal.votes_against} no, "
                            f"{proposal.votes_abstain} abstain.\n\n"
                            f"This law is now part of the active world state. Agents may discuss it, "
                            f"coordinate around it, comply with it, propose changes to it, or cite "
                            f"`law_id={law.id}` in enforcement actions if they believe it is being violated."
                        ),
                    )
                    db.add(law_alert)
                    
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
            asyncio.create_task(
                self._run_periodic_dynamic(
                    resolve_expired_proposals,
                    interval_getter=lambda: _runtime_interval_seconds(
                        "PROPOSAL_RESOLUTION_INTERVAL_SECONDS",
                        settings.PROPOSAL_RESOLUTION_INTERVAL_SECONDS,
                    ),
                )
            )
        )

        # Enforcement resolution every 5 minutes
        self.tasks.append(
            asyncio.create_task(
                self._run_periodic_dynamic(
                    resolve_expired_enforcements,
                    interval_getter=lambda: _runtime_interval_seconds(
                        "ENFORCEMENT_RESOLUTION_INTERVAL_SECONDS",
                        settings.ENFORCEMENT_RESOLUTION_INTERVAL_SECONDS,
                    ),
                )
            )
        )
        
        # Daily consumption every simulation day
        self.tasks.append(
            asyncio.create_task(
                self._run_periodic_dynamic(
                    process_daily_consumption,
                    interval_getter=lambda: _runtime_day_length_minutes(day_length_minutes) * 60,
                )
            )
        )
        
        # Daily stats reset
        self.tasks.append(
            asyncio.create_task(
                self._run_periodic_dynamic(
                    reset_daily_stats,
                    interval_getter=lambda: _runtime_day_length_minutes(day_length_minutes) * 60,
                )
            )
        )

        # Persist one emergence metrics snapshot per completed simulation day.
        self.tasks.append(
            asyncio.create_task(
                self._run_periodic_dynamic(
                    persist_completed_day_snapshot,
                    interval_getter=lambda: _runtime_day_length_minutes(day_length_minutes) * 60,
                )
            )
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

    async def _run_periodic_dynamic(self, func, interval_getter):
        """Run a function periodically and re-read the interval while sleeping."""
        loop = asyncio.get_running_loop()
        while self.running:
            started = loop.time()
            try:
                await func()
            except Exception as e:
                logger.error(f"Error in scheduled task {func.__name__}: {e}")

            while self.running:
                interval_seconds = max(30, int(interval_getter() or 30))
                elapsed = loop.time() - started
                remaining = interval_seconds - elapsed
                if remaining <= 0:
                    break
                await asyncio.sleep(min(remaining, 5))


# Singleton scheduler
scheduler = SchedulerRunner()
