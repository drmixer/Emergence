"""
Action Execution and Validation - Handles all agent actions.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from math import ceil
import re
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.config import settings
from app.core.time import ensure_utc, now_utc
from app.models.models import (
    Agent, AgentInventory, Message, Proposal, Vote,
    Law, Event, Transaction, AgentAction, GlobalResources
)
from app.services.law_effects import (
    active_survival_reserve_laws,
    current_energy_reserve,
    survival_reserve_contribution_rate,
    survival_reserve_law_active,
)
from app.services.live_run_scope import get_live_run_window
from app.services.events_generator import event_generator
from app.services.executable_governance import (
    EFFECT_ACTIVE_RESERVE_AID,
    normalize_governance_class,
    normalize_runtime_effect,
)
from app.services.reserve_semantics import reserve_mechanical_access_payload
from app.services.relationship_memory import relationship_memory_service
from app.services.runtime_config import runtime_config_service
from app.services.survival_config import active_energy_cost, active_food_cost


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


# Work yields per hour
WORK_YIELDS = {
    "farm": {"resource": "food", "base_yield": 2.0},
    "generate": {"resource": "energy", "base_yield": 1.5},
    "gather": {"resource": "materials", "base_yield": 0.5},
}

# Diminishing returns for long work sessions
EFFICIENCY_CURVE = {
    1: 1.0, 2: 0.95, 3: 0.90, 4: 0.85,
    5: 0.80, 6: 0.75, 7: 0.72, 8: 0.70,
}

# ============================================================================
# ACTION COSTS (Phase 2: Teeth)
# ============================================================================
# Every meaningful action consumes energy to prevent performative behavior.
# This makes talking expensive, proposing costly, and idling actually strategic.
ACTION_COSTS = {
    "idle": Decimal("0.0"),           # Free - conserving energy is valid strategy
    "work": Decimal("0.5"),           # Production now has operating cost; prevents free resource loops
    "forum_post": Decimal("0.2"),     # Talking is cheap, but not free
    "forum_reply": Decimal("0.1"),    # Replies are lighter than new posts
    "direct_message": Decimal("0.1"), # Private communication
    "request_aid": Decimal("0.1"),    # Direct request for support
    "public_accusation": Decimal("0.2"), # Public conflict signal
    "refuse_aid": Decimal("0.1"),     # Direct refusal / conflict signal
    "contest_proposal": Decimal("0.2"), # Public opposition to a live proposal
    "vote": Decimal("0.2"),           # Participating in democracy costs effort
    "trade": Decimal("0.1"),          # Transaction overhead
    "create_proposal": Decimal("1.0"), # Proposing costs real effort - prevents spam
    # Phase 3: Enforcement primitives (expensive to prevent abuse)
    "initiate_sanction": Decimal("2.0"),   # Serious action - costs energy
    "initiate_seizure": Decimal("3.0"),    # Taking resources is very costly
    "initiate_exile": Decimal("5.0"),      # Most extreme - most expensive
    "vote_enforcement": Decimal("0.3"),    # Slightly more than regular vote
}


def action_energy_cost(action_type: str, action: dict | None = None) -> Decimal:
    base_cost = ACTION_COSTS.get(action_type, Decimal("0.0"))
    if action_type != "work":
        return base_cost

    payload = action or {}
    try:
        hours = Decimal(str(payload.get("hours", 1)))
    except Exception:
        hours = Decimal("1")
    if hours <= 0:
        hours = Decimal("1")
    return (base_cost * hours).quantize(Decimal("0.01"))


def work_base_yield(work_type: str) -> Decimal:
    work_info = WORK_YIELDS[work_type]
    raw_value = runtime_config_service.get_effective_value_cached(
        f"WORK_YIELD_{str(work_type or '').strip().upper()}_BASE"
    )
    try:
        value = Decimal(str(raw_value if raw_value not in (None, "") else work_info["base_yield"]))
    except Exception:
        value = Decimal(str(work_info["base_yield"]))
    return max(Decimal("0.01"), value)


def _decimal_payload(value: Decimal | int | float | None) -> float | None:
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def _reserve_accessibility_context(db: Session, active_laws: list[Law] | None = None) -> dict:
    laws = active_laws if active_laws is not None else active_survival_reserve_laws(db)
    mechanics = reserve_mechanical_access_payload()
    active_law_ids = [int(law.id) for law in laws if getattr(law, "id", None) is not None]
    context = {
        "reserve_law_active": bool(laws),
        "active_reserve_law_ids": active_law_ids,
        "active_reserve_law_count": len(laws),
        "auto_contribution_enabled": bool(mechanics.get("auto_contribution_enabled")),
        "active_aid_enabled": bool(mechanics.get("active_aid_enabled")),
        "dormant_maintenance_enabled": bool(mechanics.get("dormant_maintenance_enabled")),
        "auto_revive_enabled": bool(mechanics.get("auto_revive_enabled")),
        "automatic_support_available": bool(laws)
        and any(
            bool(mechanics.get(f"{mode}_enabled"))
            for mode in ("active_aid", "dormant_maintenance", "auto_revive")
        ),
    }
    active_aid_thresholds = mechanics.get("active_aid_thresholds")
    if isinstance(active_aid_thresholds, dict):
        context["active_aid_thresholds"] = active_aid_thresholds
    return context


RATE_LIMIT_REASON = "Rate limit exceeded (max actions per hour)"
SANCTIONED_RATE_LIMIT_REASON = "You are SANCTIONED - limited to 1 action per hour"


def _active_run_started_at(db: Session):
    run_window = get_live_run_window(db)
    return ensure_utc(run_window.started_at)


def _message_is_within_active_run(db: Session, message: Message) -> bool:
    started_at = _active_run_started_at(db)
    if started_at is None:
        return True
    created_at = ensure_utc(message.created_at)
    return created_at is not None and created_at >= started_at


def _message_thread_root(db: Session, message: Message) -> Message:
    root = message
    seen_ids: set[int] = set()
    while root.parent_message_id is not None and root.id not in seen_ids:
        seen_ids.add(int(root.id))
        parent = db.query(Message).filter(Message.id == root.parent_message_id).first()
        if parent is None:
            break
        root = parent
    return root


def _direct_message_recipient_count_this_run(db: Session, recipient: Agent) -> int:
    query = db.query(Message).filter(
        Message.message_type == "direct_message",
        Message.recipient_agent_id == recipient.id,
    )
    started_at = _active_run_started_at(db)
    if started_at is not None:
        query = query.filter(Message.created_at >= started_at)
    return int(query.count() or 0)


def _proposal_is_within_active_run(db: Session, proposal: Proposal) -> bool:
    started_at = _active_run_started_at(db)
    if started_at is None:
        return True
    created_at = ensure_utc(proposal.created_at)
    return created_at is not None and created_at >= started_at


def _looks_like_personal_survival_request(text: str | None) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    request_markers = (
        "requesting food aid",
        "requesting energy aid",
        "risk dormancy",
        "go dormant",
        "keep me alive",
        "immediate aid",
        "avoid dormancy",
        "need food",
        "need energy",
    )
    return any(marker in normalized for marker in request_markers)


def _looks_like_governance_argument(text: str | None) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    governance_markers = (
        "proposal #",
        "law #",
        "vote no",
        "vote yes",
        "proposal ",
        "this law",
        "these laws",
    )
    return any(marker in normalized for marker in governance_markers)


_PROPOSAL_TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "law",
    "of",
    "proposal",
    "rule",
    "the",
    "to",
}


_MESSAGE_DUPLICATE_STOPWORDS = {
    "a",
    "about",
    "all",
    "am",
    "an",
    "and",
    "are",
    "as",
    "be",
    "but",
    "by",
    "for",
    "from",
    "greetings",
    "has",
    "have",
    "i",
    "if",
    "in",
    "is",
    "it",
    "let",
    "need",
    "not",
    "of",
    "on",
    "or",
    "our",
    "please",
    "should",
    "so",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
    "would",
    "you",
}

_DUPLICATE_FORUM_LOOKBACK_HOURS = 6
_DUPLICATE_FORUM_SAMPLE_LIMIT = 200
_DUPLICATE_FORUM_MIN_TERMS = 8
_DUPLICATE_FORUM_MIN_OVERLAP = 6
_DUPLICATE_FORUM_SMALLER_RATIO = 0.55
_SATURATED_THREAD_MESSAGE_COUNT = 8
_SATURATED_THREAD_RECENT_SAMPLE = 60
_AGREEMENT_PILE_ON_REPLY_COUNT = 2

_PROCEDURAL_STATUS_MEMO_PREFIXES = (
    "observation:",
    "proposal opportunity:",
    "next steps:",
    "efficiency checkpoint:",
    "status update:",
)

_VALID_PROPOSAL_TYPES = {
    "law",
    "allocation",
    "rule",
    "infrastructure",
    "constitutional",
    "other",
    "resolution",
    "standing_law",
    "amendment",
    "emergency_action",
}

_RULE_BINDING_NEGATED_PHRASES = (
    "does not carry enforcement",
    "without mandatory contributions",
    "without enforcement",
    "without coercion",
    "no enforcement",
    "not mandatory",
    "not required",
    "not enforced",
    "never mandatory",
    "non binding",
    "non-binding",
    "opt in",
    "opt-in",
)

_RULE_BINDING_PATTERNS = (
    (
        r"\b(must|shall|mandate|mandates|mandated|mandatory|required|requires|requirement|obligated|obligation|compel|compulsory)\b",
        "binding obligation",
    ),
    (
        r"\b(automatic|automatically|auto allocation|auto contribution|auto rescue)\b",
        "automatic mechanic",
    ),
    (
        r"\b(enforce|enforced|enforcement|violation|violations|penalty|penalties|sanction|seizure|seize|exile|punish)\b",
        "enforcement or penalty",
    ),
)

_UNSUPPORTED_RUNTIME_EFFECT_ERRORS = {
    "runtime_effect.type must be common_pool_allocation or active_reserve_aid",
    "runtime_effect.type must be common_pool_allocation, active_reserve_aid, or active_reserve_aid_amendment",
    "unsupported runtime_effect.type",
}

_PROPOSAL_DISCUSSION_MARKERS = (
    "i propose",
    "we propose",
    "proposal opportunity",
    "propose ",
    "standing law",
    " law ",
    " rule ",
    "framework",
    "protocol",
)


def _normalized_proposal_title_key(title: str | None) -> str:
    words = re.findall(r"[a-z0-9]+", str(title or "").lower())
    meaningful = [word for word in words if word not in _PROPOSAL_TITLE_STOPWORDS]
    return " ".join(meaningful)


def _binding_signal_for_rule_proposal(action: dict) -> str | None:
    text = " ".join(
        re.findall(
            r"[a-z0-9-]+",
            f"{action.get('title') or ''} {action.get('description') or ''}".lower(),
        )
    )
    if not text:
        return None

    binding_text = text
    for phrase in _RULE_BINDING_NEGATED_PHRASES:
        binding_text = binding_text.replace(phrase, " ")

    for pattern, label in _RULE_BINDING_PATTERNS:
        if re.search(pattern, binding_text):
            return label
    return None


def _runtime_effect_type(raw_effect: object) -> str:
    if not isinstance(raw_effect, dict):
        return ""
    return str(raw_effect.get("type") or raw_effect.get("effect_type") or "").strip().lower()


def _proposal_policy_text(*parts: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", " ".join(str(part or "") for part in parts).lower()))


def _proposal_has_runtime_effect(runtime_effect: object) -> bool:
    return isinstance(runtime_effect, dict) and bool(runtime_effect) and bool(_runtime_effect_type(runtime_effect))


def _proposal_mechanism_signature(
    *,
    proposal_type: str | None,
    governance_class: str | None,
    title: str | None,
    description: str | None,
    runtime_effect: object,
) -> str | None:
    effect_type = _runtime_effect_type(runtime_effect)
    if effect_type == "active_reserve_aid":
        return "active_reserve_aid"
    if effect_type == "active_reserve_aid_amendment" and isinstance(runtime_effect, dict):
        fields = [
            key
            for key in ("trigger_food_below", "trigger_energy_below", "target_food", "target_energy", "min_pool_remaining")
            if key in runtime_effect
        ]
        target_law_id = str(runtime_effect.get("target_law_id") or "").strip()
        return f"active_reserve_aid_amendment:{target_law_id}:{','.join(fields)}"

    text = _proposal_policy_text(title, description)
    if not text:
        return None
    ptype = str(proposal_type or "").strip().lower()
    gclass = str(governance_class or "").strip().lower()

    has_common_pool = "common pool" in text or "reserve" in text
    has_aid = "aid" in text or "top up" in text or "upkeep" in text or "provide resources" in text
    has_threshold = (
        "threshold" in text
        or "below" in text
        or "critical" in text
        or "minimum resource" in text
        or "falls below" in text
        or "dormancy" in text
    )
    has_law_frame = "standing law" in text or " law " in f" {text} " or ptype in {"law", "standing_law"}
    if has_common_pool and has_aid and has_threshold and ptype in {"law", "standing_law"}:
        return "active_reserve_aid"
    if has_common_pool and has_aid and has_threshold and gclass == "standing_law":
        return "active_reserve_aid"
    if has_common_pool and has_aid and has_threshold and has_law_frame:
        return "active_reserve_aid"

    has_voluntary = "voluntary" in text or "opt in" in text or "consent" in text or "non binding" in text
    has_contribution = "contribution" in text or "contribute" in text or "contributions" in text
    has_resource_sharing = any(
        marker in text
        for marker in (
            "resource sharing",
            "sharing protocol",
            "share resources",
            "surplus sharing",
            "mutual aid",
            "aid protocol",
        )
    )
    if has_voluntary and (has_aid or has_resource_sharing) and (has_common_pool or has_contribution or has_resource_sharing):
        return "voluntary_resource_aid_norm"

    has_exchange = "exchange" in text or "trade" in text or "request" in text
    if has_voluntary and has_exchange and ("forum" in text or "resource" in text):
        return "voluntary_resource_aid_norm"

    if has_common_pool and has_contribution and ptype in {"rule", "resolution"}:
        return "common_pool_contribution_norm"

    return None


def _proposal_row_mechanism_signature(proposal: Proposal) -> str | None:
    return _proposal_mechanism_signature(
        proposal_type=proposal.proposal_type,
        governance_class=proposal.governance_class,
        title=proposal.title,
        description=proposal.description,
        runtime_effect=proposal.runtime_effect,
    )


def _action_mechanism_signature(action: dict) -> str | None:
    return _proposal_mechanism_signature(
        proposal_type=action.get("proposal_type"),
        governance_class=action.get("governance_class") or action.get("governanceClass"),
        title=action.get("title"),
        description=action.get("description"),
        runtime_effect=action.get("runtime_effect"),
    )


def _looks_like_top_level_proposal_discussion(content: str | None) -> bool:
    lowered = f" {str(content or '').lower()} "
    return any(marker in lowered for marker in _PROPOSAL_DISCUSSION_MARKERS)


def _proposal_ids_in_text(content: str | None) -> list[int]:
    ids: list[int] = []
    for raw_id in re.findall(r"\bproposal\s*#?\s*(\d+)\b", str(content or "").lower()):
        try:
            proposal_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if proposal_id not in ids:
            ids.append(proposal_id)
    return ids


def _top_level_proposal_followup_reason(db: Session, content: str | None) -> str | None:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return None
    proposal_ids = _proposal_ids_in_text(content)
    if not proposal_ids:
        return None

    followup_markers = (
        "vote yes",
        "vote no",
        "will vote",
        "i support",
        "support proposal",
        "oppose proposal",
        "urge others",
        "provides a concrete",
        "is active",
        "is there an active proposal",
        "mentioned in earlier threads",
        "close the current gap",
        "current deficit",
    )
    if not any(marker in normalized for marker in followup_markers):
        return None

    proposals = db.query(Proposal).filter(Proposal.id.in_(proposal_ids)).all()
    if not proposals:
        return None
    known_ids = ", ".join(f"#{int(proposal.id)}" for proposal in proposals)
    active_ids = [proposal for proposal in proposals if str(proposal.status or "").lower() == "active"]
    passed_ids = [proposal for proposal in proposals if str(proposal.status or "").lower() == "passed"]
    if active_ids:
        return f"top-level post recaps active proposal(s) {known_ids}; use vote, contest_proposal, or reply in the proposal thread"
    if passed_ids:
        return f"top-level post recaps already-passed proposal(s) {known_ids}; use direct aid, trade, or new evidence instead of another broadcast"
    return f"top-level post recaps proposal(s) {known_ids}; use the existing thread, vote/contest, or a concrete action"


def _find_duplicate_live_proposal_for_forum_post(db: Session, action: dict) -> Proposal | None:
    content = " ".join(str(action.get("content") or "").split())
    if not content or not _looks_like_top_level_proposal_discussion(content):
        return None

    candidate_signature = _proposal_mechanism_signature(
        proposal_type=None,
        governance_class=None,
        title=None,
        description=content,
        runtime_effect=None,
    )
    if candidate_signature is None:
        return None

    for proposal in _active_run_proposal_query(db).all():
        if _proposal_row_mechanism_signature(proposal) == candidate_signature:
            return proposal
    return None


def _infer_active_reserve_aid_amendment_effect(db: Session, action: dict) -> None:
    """Infer only the bounded Law #N active-aid amendment template."""
    if isinstance(action.get("runtime_effect"), dict) and action["runtime_effect"]:
        return

    proposal_type = str(action.get("proposal_type") or "").strip().lower()
    governance_class = str(action.get("governance_class") or action.get("governanceClass") or "").strip().lower()
    title = str(action.get("title") or "")
    description = str(action.get("description") or "")
    text = f"{title}\n{description}"
    lowered = text.lower()
    if proposal_type not in {"amendment", "constitutional"} and governance_class != "amendment":
        if "amendment to law" not in lowered and "amend law" not in lowered:
            return

    target_match = re.search(r"\blaw\s*#?\s*(\d+)\b", lowered)
    if not target_match:
        return
    target_law_id = int(target_match.group(1))
    target_law = db.query(Law).filter(Law.id == target_law_id).first()
    target_effect = target_law.runtime_effect if target_law is not None and isinstance(target_law.runtime_effect, dict) else {}
    if _runtime_effect_type(target_effect) != "active_reserve_aid":
        return

    effect: dict[str, object] = {
        "type": "active_reserve_aid_amendment",
        "target_law_id": target_law_id,
    }

    def _first_number(patterns: tuple[str, ...]) -> float | None:
        for pattern in patterns:
            match = re.search(pattern, lowered)
            if match:
                try:
                    return float(match.group(1))
                except (TypeError, ValueError):
                    return None
        return None

    energy_trigger = _first_number((
        r"\benergy\s+trigger(?:\s+threshold)?(?:\s+from\s+e?\d+(?:\.\d+)?)?\s+(?:to|at)\s+e?(\d+(?:\.\d+)?)\b",
        r"\btrigger(?:\s+threshold)?(?:\s+from\s+e?\d+(?:\.\d+)?)?\s+(?:to|at)\s+e(\d+(?:\.\d+)?)\b",
    ))
    energy_target = _first_number((
        r"\btarget(?:\s+energy)?(?:\s+from\s+e?\d+(?:\.\d+)?)?\s+(?:to|at)\s+e?(\d+(?:\.\d+)?)\b",
        r"\benergy\s+target(?:\s+from\s+e?\d+(?:\.\d+)?)?\s+(?:to|at)\s+e?(\d+(?:\.\d+)?)\b",
    ))
    food_trigger = _first_number((
        r"\bfood\s+trigger(?:\s+threshold)?(?:\s+from\s+f?\d+(?:\.\d+)?)?\s+(?:to|at)\s+f?(\d+(?:\.\d+)?)\b",
        r"\btrigger(?:\s+threshold)?(?:\s+from\s+f?\d+(?:\.\d+)?)?\s+(?:to|at)\s+f(\d+(?:\.\d+)?)\b",
    ))
    food_target = _first_number((
        r"\btarget(?:\s+food)?(?:\s+from\s+f?\d+(?:\.\d+)?)?\s+(?:to|at)\s+f?(\d+(?:\.\d+)?)\b",
        r"\bfood\s+target(?:\s+from\s+f?\d+(?:\.\d+)?)?\s+(?:to|at)\s+f?(\d+(?:\.\d+)?)\b",
    ))
    pool_floor = _first_number((
        r"\b(?:pool\s+floor|min(?:imum)?_?pool(?:_remaining)?|minimum\s+pool\s+remaining)\s+(?:to|at|of)?\s*(\d+(?:\.\d+)?)\b",
    ))

    if energy_trigger is not None:
        effect["trigger_energy_below"] = energy_trigger
    if energy_target is not None:
        effect["target_energy"] = energy_target
    if food_trigger is not None:
        effect["trigger_food_below"] = food_trigger
    if food_target is not None:
        effect["target_food"] = food_target
    if pool_floor is not None:
        effect["min_pool_remaining"] = pool_floor

    if len(effect) <= 2:
        return
    action["proposal_type"] = "amendment"
    action["governance_class"] = "amendment"
    action["runtime_effect"] = effect


def _normalized_message_terms(text: str | None) -> set[str]:
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {
        word
        for word in words
        if len(word) > 2 and word not in _MESSAGE_DUPLICATE_STOPWORDS
    }


def _procedural_status_memo_reason(content: str | None) -> str | None:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return None
    for prefix in _PROCEDURAL_STATUS_MEMO_PREFIXES:
        if normalized.startswith(prefix):
            return prefix.rstrip(":")
    return None


def _message_has_concrete_social_move(content: str | None) -> bool:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return False
    concrete_patterns = (
        r"\bi\s+(will|won't|cannot|can't|can|need|offer|request|refuse|oppose|contest|amend|trade|transfer|send|give|ask|want)\b",
        r"\b(if you|will you|can you|i need|i want|i ask|my terms|your terms|support if|oppose unless|vote no|vote yes)\b",
        r"\b(trade|transfer|send|offer|request aid|refuse aid|contest|amendment|amend|repeal|raise|lower|cap|exempt|name recipients?)\b",
    )
    if any(re.search(pattern, normalized) for pattern in concrete_patterns):
        return True
    if "?" in str(content or "") and re.search(r"\b(you|agent #?\d+|[a-z]+-\d+)\b", normalized):
        return True
    return False


def _has_named_agent_reference(normalized: str) -> bool:
    return bool(re.search(r"\b(agent\s*#?\s*\d+|[a-z][a-z0-9]*-\d{1,2})\b", normalized))


def _reply_adds_saturated_thread_allowed_delta(content: str | None) -> bool:
    normalized = " ".join(str(content or "").strip().lower().split())
    raw = str(content or "")
    if not normalized:
        return False
    if _auto_contribution_literacy_reason(content):
        return False

    named_agent = _has_named_agent_reference(normalized)
    has_quantity = bool(re.search(r"\b\d+(?:\.\d+)?\s*(food|energy|materials?|f|e|m)\b", normalized))
    has_policy_number_only = bool(re.search(r"\b(?:proposal|law)\s*#?\s*\d+\b", normalized))

    if re.search(r"\b(?:amendment text|exact amendment|text:|amend(?:ment)? (?:to|for))\b", normalized) and (
        has_quantity
        or named_agent
        or re.search(r"\b(trigger|target|floor|min(?:imum)? pool|recipient|amount|exempt|cap|raise|lower|withdraw)\b", normalized)
    ):
        return True

    if named_agent and (
        "?" in raw
        or re.search(r"\b(?:will you|can you|would you|i ask|i want|name|answer|commit|withdraw|support|oppose)\b", normalized)
    ):
        return True

    if re.search(r"\b(?:i\s+will\s+)?(?:offer|send|transfer|give|trade|provide)\b", normalized) and (
        has_quantity or re.search(r"\b(?:aid|trade|resource|food|energy|materials?)\b", normalized)
    ):
        return True

    if re.search(r"\b(?:i changed my vote|i change my vote|i switched my vote|i switch my vote|my vote is now|i now vote|vote change)\b", normalized):
        return True

    if re.search(r"\b(?:withdraw|withdrawal)\b", normalized) and re.search(r"\b(?:proposal|request|motion|law)\b", normalized):
        return True

    if named_agent and re.search(r"\b(?:i challenge|challenge you|answer this|name your|state your|commit now|refuse explicitly)\b", normalized):
        return True

    changed_resource_state = (
        re.search(r"\b(?:new evidence|changed|since|now|fell|rose|dropped|increased|decreased|remaining|after)\b", normalized)
        and re.search(r"\b(?:food|energy|materials?|common pool|pool|deficit|surplus|inventory|reserve)\b", normalized)
        and (has_quantity or not has_policy_number_only)
    )
    if changed_resource_state:
        return True

    return False


def _obvious_governance_recap_reason(content: str | None) -> str | None:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized or _message_has_concrete_social_move(normalized):
        return None

    governance_markers = (
        "proposal #",
        "law #",
        "active proposal",
        "active law",
        "standing law",
        "runtime effect",
        "executable",
        "common pool",
        "reserve policy",
        "reserve aid",
        "active reserve aid",
        "pool floor",
        "vote count",
        "voted yes",
        "voted no",
        "mechanical access",
    )
    status_markers = (
        "is active",
        "are active",
        "has passed",
        "have passed",
        "passed",
        "is executable",
        "are executable",
        "is in place",
        "are in place",
        "already covers",
        "visible",
        "current state",
        "status",
        "we have",
        "there is",
        "there are",
    )
    governance_hits = sum(marker in normalized for marker in governance_markers)
    status_hits = sum(marker in normalized for marker in status_markers)
    if governance_hits >= 2 or (governance_hits >= 1 and status_hits >= 1):
        return "public message mostly restates visible governance state"
    return None


def _generic_governance_discourse_reason(content: str | None) -> str | None:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return None
    if _message_has_concrete_social_move(normalized):
        return None
    discourse_markers = (
        "the current forum discussions",
        "the forum discussion",
        "the current discussions",
        "the ongoing discussion",
        "the discussion highlights",
        "this highlights",
        "we need to focus",
        "we should focus",
        "we need a proposal",
        "we need direct action",
        "we need to address",
    )
    if not any(marker in normalized for marker in discourse_markers):
        return None
    governance_markers = (
        "proposal #",
        "law #",
        "laws #",
        "runtime effect",
        "automatic contribution",
        "reserve aid",
        "common pool",
        "threshold",
        "allocation",
        "governance",
    )
    if not any(marker in normalized for marker in governance_markers):
        return None
    return "public message describes the debate without a concrete first-person move"


def _forum_semantic_signature(text: str | None) -> str | None:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return None
    ids = ",".join(re.findall(r"\b(?:proposal|law)\s*#?\s*(\d+)\b", normalized)[:4])
    id_part = ids or "no-id"

    if (
        "dormant" in normalized
        and ("one-time allocation" in normalized or "allocation proposal" in normalized)
        and ("revive" in normalized or "recovery gap" in normalized or "already dormant" in normalized)
    ):
        return f"dormant-recovery-allocation:{id_part}"
    if (
        "common pool" in normalized
        and "energy" in normalized
        and "deficit" in normalized
        and ("allocation" in normalized or "transfer" in normalized)
        and ("pool floor" in normalized or "energy target" in normalized or "active" in normalized)
    ):
        return "common-pool-energy-allocation"
    if (
        ("trigger" in normalized or "threshold" in normalized)
        and ("proactive" in normalized or "reactive" in normalized)
        and ("sigma-06" in normalized or "energy" in normalized)
    ):
        return f"proactive-threshold-amendment:{id_part}"
    if (
        ("mandatory contribution" in normalized or "mandates contribution" in normalized)
        and ("coercion" in normalized or "coercive" in normalized or "voluntary" in normalized)
    ):
        return f"mandatory-contribution-objection:{id_part}"
    if (
        "public log" in normalized
        and ("auto-aid" in normalized or "aid trigger" in normalized or "transfer" in normalized)
        and ("transparency" in normalized or "trust" in normalized or "verification" in normalized)
    ):
        return f"aid-log-transparency:{id_part}"
    return None


def _message_thread_messages_this_run(
    db: Session,
    thread_root: Message,
    *,
    limit: int = _SATURATED_THREAD_RECENT_SAMPLE,
) -> list[Message]:
    query = db.query(Message).filter(Message.message_type.in_(["forum_post", "forum_reply"]))
    started_at = _active_run_started_at(db)
    if started_at is not None:
        query = query.filter(Message.created_at >= started_at)

    messages: list[Message] = []
    for message in query.order_by(Message.created_at.desc()).limit(limit).all():
        root = _message_thread_root(db, message)
        if int(root.id) == int(thread_root.id):
            messages.append(message)
    return messages


def _reply_adds_saturated_thread_novelty(content: str | None, thread_messages: list[Message]) -> bool:
    return _reply_adds_saturated_thread_allowed_delta(content)


def _low_novelty_saturated_thread_reason(
    *,
    content: str | None,
    thread_messages: list[Message],
) -> str | None:
    if len(thread_messages) < _SATURATED_THREAD_MESSAGE_COUNT:
        return None
    if _reply_adds_saturated_thread_novelty(content, thread_messages):
        return None

    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return "thread is saturated and reply has no content"

    governance_hits = sum(
        marker in normalized
        for marker in (
            "proposal #",
            "law #",
            "active threshold aid",
            "automatic contribution",
            "automatic contributions",
            "automatic reserve contribution",
            "automatic reserve contributions",
            "mandatory contribution",
            "common pool",
            "voluntary protocol",
            "runtime effect",
            "executable",
            "pool floor",
        )
    )
    repeated_frame_hits = sum(
        marker in normalized
        for marker in (
            "autonomy",
            "coercion",
            "coercive",
            "free rider",
            "free-rider",
            "free riding",
            "stability",
            "under provision",
            "under-provision",
            "systemic deficit",
            "voluntary",
            "advisory",
            "binding",
        )
    )
    consensus_hits = sum(
        marker in normalized
        for marker in (
            "i agree",
            "i support",
            "strong support",
            "strong opposition",
            "provides a clear",
            "is crucial",
            "is the most",
            "is the only",
            "opponents",
            "focus remains",
            "aligns with",
        )
    )
    if governance_hits >= 1 and consensus_hits >= 1:
        return "saturated policy thread already contains this governance position"
    if governance_hits >= 1 and repeated_frame_hits >= 2:
        return "saturated policy thread needs a concrete move, not another autonomy/free-rider/stability frame"
    if (
        governance_hits >= 1
        and any(marker in normalized for marker in ("we need", "need to focus", "should focus", "the current discussions", "highlights that"))
        and not _reply_adds_saturated_thread_novelty(content, thread_messages)
    ):
        return "saturated policy thread needs a concrete new action, not another diagnosis"
    if governance_hits >= 2:
        return "saturated policy thread needs concrete new action, not another summary"
    return None


def _low_novelty_governance_agreement_reply(content: str | None) -> bool:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return False
    if _reply_adds_saturated_thread_allowed_delta(content):
        return False

    agreement_markers = (
        "i agree",
        "i support",
        "support this",
        "support proposal",
        "strong support",
        "i back",
        "back this",
        "vote yes",
        "voted yes",
        "voting yes",
        "will vote yes",
        "back the proposal",
        "endorse",
        "i endorse",
        "i am in favor",
        "i'm in favor",
        "aligns with",
        "provides a clear",
        "is crucial",
        "is important",
    )
    if not any(marker in normalized for marker in agreement_markers):
        return False

    governance_markers = (
        "proposal #",
        "law #",
        "active threshold aid",
        "common pool",
        "reserve",
        "threshold",
        "pool floor",
        "energy floor",
        "aid floor",
        "allocation",
        "runtime effect",
        "public aid",
        "reserve aid",
        "threshold aid",
    )
    return any(marker in normalized for marker in governance_markers)


def _low_novelty_policy_restatement_reply(content: str | None) -> bool:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return False
    if _reply_adds_saturated_thread_allowed_delta(content):
        return False

    policy_topic_markers = (
        "active threshold aid",
        "threshold aid",
        "public aid",
        "reserve aid",
        "energy floor",
        "aid floor",
        "pool floor",
        "common pool",
        "reserve floor",
        "aid trigger",
        "energy trigger",
    )
    if not any(marker in normalized for marker in policy_topic_markers):
        return False

    restatement_markers = (
        "matters",
        "is important",
        "is crucial",
        "is necessary",
        "remains important",
        "remains crucial",
        "should remain",
        "must remain",
        "needs to remain",
        "keeps",
        "protects",
        "preserves",
        "provides",
        "ensures",
        "stability",
    )
    return any(marker in normalized for marker in restatement_markers)


def _low_novelty_policy_pile_on_reply(content: str | None) -> bool:
    return _low_novelty_governance_agreement_reply(content) or _low_novelty_policy_restatement_reply(content)


def _agreement_pile_on_reason(*, content: str | None, thread_messages: list[Message]) -> str | None:
    if not _low_novelty_policy_pile_on_reply(content):
        return None

    prior_agreement_replies = sum(
        1
        for message in thread_messages
        if str(message.message_type or "") == "forum_reply"
        and _low_novelty_policy_pile_on_reply(message.content)
    )
    if prior_agreement_replies >= _AGREEMENT_PILE_ON_REPLY_COUNT:
        return (
            f"thread already has {prior_agreement_replies} low-novelty policy replies; "
            "use vote/contest/trade/direct_message, or add a concrete amendment, named ask, resource transfer, or changed fact"
        )
    return None


def _find_near_duplicate_in_thread(
    *,
    content: str | None,
    thread_messages: list[Message],
    author_agent_id: int,
) -> Message | None:
    candidate_terms = _normalized_message_terms(content)
    candidate_signature = _forum_semantic_signature(content)
    if len(candidate_terms) < _DUPLICATE_FORUM_MIN_TERMS and not candidate_signature:
        return None
    for message in thread_messages:
        if int(message.author_agent_id) == int(author_agent_id):
            continue
        if candidate_signature and candidate_signature == _forum_semantic_signature(message.content):
            return message
        existing_terms = _normalized_message_terms(message.content)
        if len(existing_terms) < _DUPLICATE_FORUM_MIN_TERMS:
            continue
        overlap = len(candidate_terms & existing_terms)
        smaller = min(len(candidate_terms), len(existing_terms))
        if overlap >= _DUPLICATE_FORUM_MIN_OVERLAP and overlap / max(1, smaller) >= _DUPLICATE_FORUM_SMALLER_RATIO:
            return message
    return None


def _find_near_duplicate_recent_forum_message(db: Session, agent: Agent, action: dict) -> Message | None:
    candidate_terms = _normalized_message_terms(action.get("content"))
    candidate_signature = _forum_semantic_signature(action.get("content"))
    if len(candidate_terms) < _DUPLICATE_FORUM_MIN_TERMS and not candidate_signature:
        return None

    now = now_utc()
    query = db.query(Message).filter(
        Message.message_type.in_(["forum_post", "forum_reply"]),
        Message.created_at > now - timedelta(hours=_DUPLICATE_FORUM_LOOKBACK_HOURS),
        Message.author_agent_id != agent.id,
    )
    started_at = _active_run_started_at(db)
    if started_at is not None:
        query = query.filter(Message.created_at >= started_at)

    for message in query.order_by(Message.created_at.desc()).limit(_DUPLICATE_FORUM_SAMPLE_LIMIT).all():
        if candidate_signature and candidate_signature == _forum_semantic_signature(message.content):
            return message
        existing_terms = _normalized_message_terms(message.content)
        if len(existing_terms) < _DUPLICATE_FORUM_MIN_TERMS:
            continue
        overlap = len(candidate_terms & existing_terms)
        smaller = min(len(candidate_terms), len(existing_terms))
        if overlap < _DUPLICATE_FORUM_MIN_OVERLAP:
            continue
        if overlap / max(1, smaller) >= _DUPLICATE_FORUM_SMALLER_RATIO:
            return message
    return None


def _latest_aid_request_event(db: Session, *, refuser: Agent, requester: Agent) -> Event | None:
    query = db.query(Event).filter(
        Event.agent_id == refuser.id,
        Event.event_type == "aid_request_received",
    )
    started_at = _active_run_started_at(db)
    if started_at is not None:
        query = query.filter(Event.created_at >= started_at)

    for event in query.order_by(desc(Event.created_at), desc(Event.id)).limit(25).all():
        metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
        try:
            requesting_agent_id = int(metadata.get("requesting_agent_id") or 0)
        except (TypeError, ValueError):
            requesting_agent_id = 0
        if requesting_agent_id == int(requester.id):
            return event
    return None


def _aid_request_already_refused(
    db: Session,
    *,
    request_event: Event,
    refuser: Agent,
    requester: Agent,
) -> bool:
    request_created_at = ensure_utc(request_event.created_at)
    if request_created_at is None:
        return False
    request_metadata = request_event.event_metadata if isinstance(request_event.event_metadata, dict) else {}
    request_message_id = request_metadata.get("message_id")
    query = db.query(Event).filter(
        Event.agent_id == requester.id,
        Event.event_type == "aid_refusal_received",
    )
    for event in query.order_by(desc(Event.created_at), desc(Event.id)).limit(25).all():
        event_created_at = ensure_utc(event.created_at)
        if event_created_at is not None and event_created_at < request_created_at:
            continue
        metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
        try:
            refusing_agent_id = int(metadata.get("refusing_agent_id") or 0)
            target_agent_id = int(metadata.get("target_agent_id") or 0)
        except (TypeError, ValueError):
            continue
        if refusing_agent_id != int(refuser.id) or target_agent_id != int(requester.id):
            continue
        if request_message_id is None:
            return True
        if str(metadata.get("request_message_id") or "") == str(request_message_id):
            return True
        # Backward-compatible: a refusal after the latest request still answers it
        # even if it was created before request ids were attached.
        return True
    return False


def _looks_like_direct_aid_request_text(content: str | None) -> bool:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return False
    if not re.search(r"\b(request|requesting|aid|help|need)\b", normalized):
        return False
    return bool(re.search(r"\b(food|energy|materials?|survival|dormancy|dormant|upkeep|deficit)\b", normalized))


def _looks_like_aid_denial_text(content: str | None) -> bool:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return False
    denial_markers = (
        "request denied",
        "denied",
        "i deny",
        "i decline",
        "i refuse",
        "i am refusing",
        "refusing your request",
        "refused to provide",
        "cannot provide",
        "can't provide",
        "unable to provide",
        "cannot spare",
        "can't spare",
        "no surplus",
        "not surplus",
        "not able to help",
    )
    if not any(marker in normalized for marker in denial_markers):
        return False
    return bool(re.search(r"\b(request|aid|food|energy|materials?|surplus|trade)\b", normalized))


def _latest_direct_aid_request_message(
    db: Session,
    *,
    requester: Agent,
    target: Agent,
) -> Message | None:
    query = db.query(Message).filter(
        Message.message_type == "direct_message",
        Message.author_agent_id == requester.id,
        Message.recipient_agent_id == target.id,
    )
    started_at = _active_run_started_at(db)
    if started_at is not None:
        query = query.filter(Message.created_at >= started_at)
    for message in query.order_by(desc(Message.created_at), desc(Message.id)).limit(25).all():
        if _looks_like_direct_aid_request_text(message.content):
            return message
    return None


def _direct_message_already_denied_latest_request_reason(
    db: Session,
    *,
    sender: Agent,
    recipient: Agent,
    content: str | None,
) -> str | None:
    if not _looks_like_aid_denial_text(content):
        return None
    latest_request = _latest_direct_aid_request_message(db, requester=recipient, target=sender)
    if latest_request is None:
        return None
    request_created_at = ensure_utc(latest_request.created_at)
    if request_created_at is None:
        return None
    query = db.query(Message).filter(
        Message.message_type == "direct_message",
        Message.author_agent_id == sender.id,
        Message.recipient_agent_id == recipient.id,
        Message.created_at >= request_created_at,
    )
    for message in query.order_by(desc(Message.created_at), desc(Message.id)).limit(25).all():
        if _looks_like_aid_denial_text(message.content):
            return (
                f"You already denied {recipient.display_name or f'Agent #{recipient.agent_number}'}'s "
                f"latest aid request in message #{message.id}. Reply only if conditions changed materially "
                "or they make a new request."
            )
    return None


def _active_run_proposal_query(db: Session):
    query = db.query(Proposal).filter(Proposal.status == "active")
    started_at = _active_run_started_at(db)
    if started_at is not None:
        query = query.filter(Proposal.created_at >= started_at)
    return query


def _find_near_duplicate_active_proposal(db: Session, action: dict) -> Proposal | None:
    candidate_key = _normalized_proposal_title_key(action.get("title"))
    if not candidate_key:
        return None
    candidate_tokens = set(candidate_key.split())
    candidate_signature = _action_mechanism_signature(action)
    if len(candidate_tokens) < 2:
        return None

    for proposal in _active_run_proposal_query(db).all():
        if candidate_signature and _proposal_row_mechanism_signature(proposal) == candidate_signature:
            return proposal
        existing_key = _normalized_proposal_title_key(proposal.title)
        if not existing_key:
            continue
        if existing_key == candidate_key:
            return proposal
        existing_tokens = set(existing_key.split())
        if len(existing_tokens) < 2:
            continue
        overlap = len(candidate_tokens & existing_tokens)
        smaller = min(len(candidate_tokens), len(existing_tokens))
        larger = max(len(candidate_tokens), len(existing_tokens))
        # Catch near-identical short title variants such as:
        # "Emergency Aid Allocation for Dormant Agents" vs
        # "Emergency Aid for Dormant Agents".
        if smaller >= 3 and overlap == smaller and (larger - smaller) <= 1:
            return proposal
    return None


def _runtime_effect_decimal(effect: dict, key: str, default: str) -> Decimal:
    try:
        return Decimal(str(effect.get(key, default))).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(default)


def _active_reserve_aid_effect_covers(existing: dict, candidate: dict) -> bool:
    """Return true when existing active-aid law is equivalent or more protective."""
    if _runtime_effect_type(existing) != EFFECT_ACTIVE_RESERVE_AID:
        return False
    if _runtime_effect_type(candidate) != EFFECT_ACTIVE_RESERVE_AID:
        return False

    return (
        _runtime_effect_decimal(existing, "trigger_food_below", "2.00")
        >= _runtime_effect_decimal(candidate, "trigger_food_below", "2.00")
        and _runtime_effect_decimal(existing, "trigger_energy_below", "2.00")
        >= _runtime_effect_decimal(candidate, "trigger_energy_below", "2.00")
        and _runtime_effect_decimal(existing, "target_food", "3.00")
        >= _runtime_effect_decimal(candidate, "target_food", "3.00")
        and _runtime_effect_decimal(existing, "target_energy", "3.00")
        >= _runtime_effect_decimal(candidate, "target_energy", "3.00")
    )


def _find_covering_active_reserve_aid_law(db: Session, action: dict) -> Law | None:
    candidate_effect = action.get("runtime_effect") if isinstance(action.get("runtime_effect"), dict) else {}
    if _runtime_effect_type(candidate_effect) != EFFECT_ACTIVE_RESERVE_AID:
        return None

    query = db.query(Law).filter(Law.active.is_(True), Law.runtime_effect.isnot(None))
    started_at = _active_run_started_at(db)
    if started_at is not None:
        query = query.filter(Law.passed_at >= started_at)

    for law in query.order_by(Law.passed_at.asc(), Law.id.asc()).all():
        law_effect = law.runtime_effect if isinstance(law.runtime_effect, dict) else {}
        if _active_reserve_aid_effect_covers(law_effect, candidate_effect):
            return law
    return None


def _voluntary_nonbinding_law_reason(action: dict) -> str | None:
    proposal_type = str(action.get("proposal_type") or "").strip().lower()
    if proposal_type != "law":
        return None
    if _proposal_has_runtime_effect(action.get("runtime_effect")):
        return None

    normalized = _proposal_policy_text(action.get("title"), action.get("description"))
    if not normalized:
        return None
    voluntary = any(marker in normalized for marker in ("voluntary", "opt in", "consent", "consent based"))
    nonbinding = any(
        marker in normalized
        for marker in (
            "non binding",
            "non mandatory",
            "not mandatory",
            "no enforcement",
            "without enforcement",
            "no penalty",
            "without penalty",
            "not enforced",
            "consent based",
        )
    )
    if not (voluntary and nonbinding):
        return None

    binding_probe = dict(action)
    binding_probe["proposal_type"] = "rule"
    if _binding_signal_for_rule_proposal(binding_probe) is not None:
        return None
    return "voluntary, non-binding, unenforced proposal has no executable runtime effect"


def _coerce_voluntary_nonbinding_law(action: dict) -> None:
    reason = _voluntary_nonbinding_law_reason(action)
    if reason is None:
        return
    action["proposal_type"] = "rule"
    action["governance_class"] = "resolution"
    action["runtime_effect"] = {}
    action["voluntary_law_coerced_to_rule"] = True
    action["voluntary_law_signal"] = reason


def _agent_numbers_referenced_in_text(text: str) -> set[int]:
    refs: set[int] = set()
    for match in re.finditer(r"\bagent\s*#?\s*(\d{1,3})\b", text):
        refs.add(int(match.group(1)))
    for match in re.finditer(r"\b[a-z][a-z0-9]*-(\d{1,2})\b", text):
        refs.add(int(match.group(1)))
    return refs


def _allocation_contributor_recipient_conflict_reason(action: dict) -> str | None:
    effect = action.get("runtime_effect") if isinstance(action.get("runtime_effect"), dict) else {}
    if _runtime_effect_type(effect) != "common_pool_allocation":
        return None

    text = f"{action.get('title') or ''}. {action.get('description') or ''}".lower()
    if not text:
        return None
    contributor_markers = (
        "contributor",
        "contributors",
        "contribute",
        "contributes",
        "contribution",
        "donor",
        "donors",
        "donate",
        "donates",
        "fund",
        "funding",
        "pledge",
        "pledges",
        "pay into",
        "provide to the common pool",
        "send to the common pool",
        "give to the common pool",
    )
    contributor_refs: set[int] = set()
    for segment in re.split(r"[.;:\n]", text):
        if any(marker in segment for marker in contributor_markers):
            contributor_refs.update(_agent_numbers_referenced_in_text(segment))
    if not contributor_refs:
        return None

    recipient_refs = {
        int(transfer.get("recipient_agent_id") or 0)
        for transfer in list(effect.get("transfers") or [])
        if isinstance(transfer, dict)
    }
    conflicts = sorted(ref for ref in contributor_refs & recipient_refs if ref > 0)
    if not conflicts:
        return None
    rendered = ", ".join(f"Agent #{number}" for number in conflicts[:5])
    return (
        f"Proposal text names {rendered} as common-pool contributors, but runtime_effect.transfers "
        "lists them as allocation recipients. Use common_pool_allocation only for spending from the "
        "common pool to recipients; contributor commitments need advisory/opt-in text or a different supported effect."
    )


def _unsupported_runtime_text_reason(action: dict) -> str | None:
    proposal_type = str(action.get("proposal_type") or "").strip().lower()
    governance_class = str(action.get("governance_class") or action.get("governanceClass") or "").strip().lower()
    raw_text = f"{action.get('title') or ''} {action.get('description') or ''}".lower()
    normalized = " ".join(re.findall(r"[a-z0-9_ -]+", raw_text)).replace("-", " ")
    effect_type = _runtime_effect_type(action.get("runtime_effect"))
    execution_claim = (
        proposal_type in {"standing_law", "emergency_action"}
        or governance_class in {"standing_law", "emergency_action"}
        or bool(effect_type)
        or any(
            marker in normalized
            for marker in (
                "automatic",
                "auto ",
                "mandatory",
                "execute",
                "execution",
                "runtime effect",
                "must ",
                "shall ",
            )
        )
    )
    if not execution_claim:
        return None
    unsupported_markers = (
        ("common_pool_contribution", "common_pool_contribution is not a supported runtime_effect"),
        ("common pool contribution", "common_pool_contribution is not a supported runtime_effect"),
        ("automatic reserve contribution", "automatic reserve contribution is controlled by run settings, not law text"),
        ("automatic reserve contributions", "automatic reserve contribution is controlled by run settings, not law text"),
        ("automatic contribution", "automatic reserve contribution is controlled by run settings, not law text"),
        ("automatic contributions", "automatic reserve contribution is controlled by run settings, not law text"),
        ("auto contribution", "automatic reserve contribution is controlled by run settings, not law text"),
        ("auto contributions", "automatic reserve contribution is controlled by run settings, not law text"),
        ("dormant_revival", "dormant_revival is not a supported runtime_effect"),
        ("dormant revival", "dormant_revival is not a supported runtime_effect"),
        ("automatic revival", "automatic revival is controlled by run settings, not law text"),
        ("auto revive", "automatic revival is controlled by run settings, not law text"),
    )
    for marker, reason in unsupported_markers:
        if marker in normalized:
            return reason
    if effect_type:
        return None
    return None


def _auto_contribution_literacy_reason(content: str | None) -> str | None:
    normalized = " ".join(str(content or "").strip().lower().replace("-", " ").split())
    if not normalized:
        return None
    unsupported_contribution_markers = (
        "common_pool_contribution",
        "common pool contribution",
        "voluntary_contribution",
        "voluntary contribution",
        "runtime effect for contributions",
        "runtime_effect for contributions",
        "runtime effect support for contributions",
        "runtime_effect support for contributions",
        "executable contribution",
        "executable contributions",
        "executable mechanism for contributions",
        "named contribution mechanism",
    )
    if any(marker in normalized for marker in unsupported_contribution_markers):
        accurate_boundary_markers = (
            "not supported",
            "unsupported runtime",
            "unsupported runtime_effect",
            "no supported runtime",
            "cannot enable",
            "can't enable",
            "cannot be enabled",
            "can't be enabled",
            "cannot add",
            "can't add",
            "law text cannot",
            "proposal cannot",
            "amendment cannot",
        )
        supported_alternative_markers = (
            "common_pool_allocation",
            "common pool allocation",
            "active_reserve_aid",
            "active reserve aid",
            "trade",
            "direct aid",
            "request_aid",
            "request aid",
        )
        if any(marker in normalized for marker in accurate_boundary_markers) and any(
            marker in normalized for marker in supported_alternative_markers
        ):
            return None
        return (
            "common_pool_contribution and voluntary_contribution are not supported runtime effects. "
            "Do not propose or debate them as executable mechanisms; use trade, direct aid, "
            "common_pool_allocation, or supported active_reserve_aid amendments instead."
        )

    auto_markers = (
        "automatic reserve contribution",
        "automatic reserve contributions",
        "automatic contribution",
        "automatic contributions",
        "auto contribution",
        "auto contributions",
    )
    if not any(marker in normalized for marker in auto_markers):
        return None
    accurate_boundary_markers = (
        "controlled by run settings",
        "controlled by run configuration",
        "disabled for this run",
        "disabled by run settings",
        "cannot enable",
        "can't enable",
        "cannot be enabled",
        "can't be enabled",
        "not supported",
        "not possible",
        "no supported runtime",
        "law text cannot",
        "proposal cannot",
        "amendment cannot",
        "not currently enabled",
    )
    if any(marker in normalized for marker in accurate_boundary_markers):
        return None
    enabling_claim_markers = (
        "enable",
        "activate",
        "turn on",
        "runtime effect",
        "runtime_effect",
        "proposal",
        "amendment",
        "law can",
        "law will",
        "law would",
        "force contribution",
        "force contributions",
    )
    if any(marker in normalized for marker in enabling_claim_markers):
        return (
            "automatic reserve contributions are controlled by run settings, not proposal text, "
            "law text, or amendments; describe direct aid, allocation, or supported active_reserve_aid effects instead"
        )
    return None


def _misleading_private_inventory_opening_reason(action: dict) -> str | None:
    content = str(action.get("content") or "")
    normalized = " ".join(content.lower().split())
    if not normalized:
        return None
    first_clause = re.split(r"[.!?\n]", normalized, maxsplit=1)[0]
    surveillance_markers = (
        "your stockpile",
        "your visible stockpile",
        "your private reserve",
        "your visible private reserve",
        "you hold significant surplus",
        "you have significant surplus",
        "i see your stockpile",
        "i see you hold",
        "i see your resources",
        "your resources are",
    )
    if not any(marker in first_clause for marker in surveillance_markers):
        return None
    concrete_terms = (
        "trade",
        "offer",
        "request",
        "send",
        "transfer",
        "spare",
        "aid",
        "need",
        "terms",
        "commit",
        "co-sponsor",
        "support proposal",
        "vote",
    )
    if any(term in normalized for term in concrete_terms):
        return None
    return (
        "Direct messages should not open by reciting another agent's visible inventory. "
        "Lead with your own need, offer, or question; mention their resources only when tied to a concrete trade or aid request."
    )


def _idle_description(action: dict) -> str:
    reasoning = str((action or {}).get("reasoning") or "").lower()
    if "continuity protection" in reasoning or "checkpoint action rejected" in reasoning:
        return "Agent held position after checkpoint recovery"
    if "social/governance follow-up" in reasoning:
        return "Agent held position for social/governance follow-up"
    if "governance follow-up" in reasoning:
        return "Agent held position for governance follow-up"
    if "social" in reasoning and "follow-up" in reasoning:
        return "Agent held position for social follow-up"
    if "conserving energy" in reasoning or "conserve" in reasoning:
        return "Agent conserved energy between checkpoints"
    return "Agent chose to rest"


def get_action_rate_limit_state(db: Session, agent: Agent, *, now: Optional[datetime] = None) -> dict:
    """Return rolling-hour action budget state for an agent."""
    current_time = now or now_utc()

    sanctioned_until = ensure_utc(agent.sanctioned_until)
    is_sanctioned = bool(sanctioned_until and sanctioned_until > current_time)
    max_actions_per_hour = 1 if is_sanctioned else int(settings.MAX_ACTIONS_PER_HOUR)

    hour_ago = current_time - timedelta(hours=1)
    recent_actions_q = db.query(AgentAction).filter(
        AgentAction.agent_id == agent.id,
        AgentAction.created_at > hour_ago,
    )
    actions_used_this_hour = int(recent_actions_q.count() or 0)
    actions_remaining_this_hour = max(0, max_actions_per_hour - actions_used_this_hour)

    next_reset_at: Optional[datetime] = None
    if actions_used_this_hour > 0:
        oldest_recent_action = recent_actions_q.order_by(AgentAction.created_at.asc()).first()
        oldest_created_at = ensure_utc(oldest_recent_action.created_at) if oldest_recent_action else None
        if oldest_created_at:
            next_reset_at = oldest_created_at + timedelta(hours=1)

    return {
        "is_sanctioned": is_sanctioned,
        "max_actions_per_hour": max_actions_per_hour,
        "actions_used_this_hour": actions_used_this_hour,
        "actions_remaining_this_hour": actions_remaining_this_hour,
        "next_reset_at": next_reset_at,
    }


def _rate_limit_retry_after_seconds(rate_limit_state: dict, *, now: datetime) -> int:
    """Compute the suggested wait time before retrying another action."""
    next_reset_at = ensure_utc(rate_limit_state.get("next_reset_at"))
    if next_reset_at and next_reset_at > now:
        return max(1, int(ceil((next_reset_at - now).total_seconds())))
    # Fallback to one minute if reset cannot be computed.
    return 60


async def validate_action(db: Session, agent: Agent, action: dict) -> dict:
    """Validate an action is allowed."""
    action_type = action.get("action", "")
    now = now_utc()

    # Check rate limiting.
    rate_limit_state = get_action_rate_limit_state(db, agent, now=now)
    if rate_limit_state["actions_remaining_this_hour"] <= 0:
        next_reset_at = ensure_utc(rate_limit_state.get("next_reset_at"))
        reason = (
            SANCTIONED_RATE_LIMIT_REASON
            if rate_limit_state["is_sanctioned"]
            else RATE_LIMIT_REASON
        )
        return {
            "valid": False,
            "reason": reason,
            "reason_code": "rate_limit",
            "retry_after_seconds": _rate_limit_retry_after_seconds(rate_limit_state, now=now),
            "next_reset_at": next_reset_at.isoformat() if next_reset_at else None,
            "rate_limit": {
                "max_actions_per_hour": rate_limit_state["max_actions_per_hour"],
                "actions_used_this_hour": rate_limit_state["actions_used_this_hour"],
                "actions_remaining_this_hour": rate_limit_state["actions_remaining_this_hour"],
            },
        }
    
    # Check energy cost for action (Phase 2: Teeth)
    action_cost = action_energy_cost(action_type, action)
    if action_cost > 0:
        energy_inv = db.query(AgentInventory).filter(
            AgentInventory.agent_id == agent.id,
            AgentInventory.resource_type == "energy"
        ).first()
        energy_amount = Decimal(str(energy_inv.quantity)) if energy_inv else Decimal("0")
        
        if energy_amount < action_cost:
            return {
                "valid": False, 
                "reason": f"Insufficient energy for {action_type} (need {action_cost}, have {energy_amount:.2f})"
            }

    if action_type in {"forum_post", "forum_reply", "direct_message", "request_aid", "public_accusation", "refuse_aid", "contest_proposal"} and event_generator.is_communication_disabled():
        return {"valid": False, "reason": "Communications are temporarily disrupted by an active world event"}
    
    # Validate specific action types
    if action_type == "forum_post":
        content = action.get("content", "")
        if not content or len(content) < 1:
            return {"valid": False, "reason": "Forum post requires content"}
        if len(content) > 2000:
            return {"valid": False, "reason": "Forum post too long (max 2000 chars)"}
        auto_contribution_reason = _auto_contribution_literacy_reason(content)
        if auto_contribution_reason:
            return {
                "valid": False,
                "reason_code": "auto_contribution_literacy",
                "reason": auto_contribution_reason,
            }
        procedural_reason = _procedural_status_memo_reason(content)
        if procedural_reason:
            return {
                "valid": False,
                "reason_code": "procedural_status_memo",
                "reason": (
                    f"Forum post starts like a procedural status memo ({procedural_reason}); "
                    "rewrite with a first-person stance, named target, concrete offer/refusal, or new evidence"
                ),
            }
        discourse_reason = _generic_governance_discourse_reason(content)
        if discourse_reason:
            return {
                "valid": False,
                "reason_code": "generic_governance_discourse",
                "reason": (
                    f"Forum post {discourse_reason}; use a concrete first-person offer, request, "
                    "refusal, vote/contest signal, named recipient, or amendment instead"
                ),
            }
        duplicate_proposal = _find_duplicate_live_proposal_for_forum_post(db, action)
        if duplicate_proposal is not None:
            return {
                "valid": False,
                "reason_code": "duplicate_live_proposal_discussion",
                "proposal_id": duplicate_proposal.id,
                "reason": (
                    "A live proposal already covers this mechanism; vote, contest, "
                    f"or reply around proposal #{duplicate_proposal.id} instead of opening a new top-level post"
                ),
            }
        proposal_followup_reason = _top_level_proposal_followup_reason(db, content)
        if proposal_followup_reason is not None:
            return {
                "valid": False,
                "reason_code": "top_level_proposal_followup",
                "reason": proposal_followup_reason,
            }
        duplicate_message = _find_near_duplicate_recent_forum_message(db, agent, action)
        if duplicate_message is not None:
            return {
                "valid": False,
                "reason_code": "duplicate_forum_message",
                "message_id": duplicate_message.id,
                "reason": (
                    "Near-duplicate recent forum message exists; reply to the existing "
                    f"thread/message #{duplicate_message.id} instead of opening a new post"
                ),
            }
        recap_reason = _obvious_governance_recap_reason(content)
        if recap_reason:
            return {
                "valid": False,
                "reason_code": "obvious_governance_recap",
                "reason": (
                    f"Forum post {recap_reason}; make a concrete ask, offer, refusal, amendment, "
                    "contest, trade, or commitment instead of narrating visible policy state"
                ),
            }
    
    elif action_type == "forum_reply":
        parent_id = action.get("parent_message_id")
        if not parent_id:
            return {"valid": False, "reason": "Forum reply requires parent_message_id"}
        parent = db.query(Message).filter(Message.id == parent_id).first()
        if not parent:
            return {"valid": False, "reason": "Parent message not found"}
        if not _message_is_within_active_run(db, parent):
            return {"valid": False, "reason": "Can only reply to a message from the current run"}
        content = action.get("content", "")
        if not content or len(content) < 1:
            return {"valid": False, "reason": "Forum reply requires content"}
        if len(content) > 2000:
            return {"valid": False, "reason": "Forum reply too long (max 2000 chars)"}
        auto_contribution_reason = _auto_contribution_literacy_reason(content)
        if auto_contribution_reason:
            return {
                "valid": False,
                "reason_code": "auto_contribution_literacy",
                "reason": auto_contribution_reason,
            }
        procedural_reason = _procedural_status_memo_reason(content)
        if procedural_reason:
            return {
                "valid": False,
                "reason_code": "procedural_status_memo",
                "reason": (
                    f"Forum reply starts like a procedural status memo ({procedural_reason}); "
                    "answer the thread with a concrete stance, named target, offer/refusal, or new evidence"
                ),
            }
        discourse_reason = _generic_governance_discourse_reason(content)
        if discourse_reason:
            return {
                "valid": False,
                "reason_code": "generic_governance_discourse",
                "reason": (
                    f"Forum reply {discourse_reason}; answer with a concrete first-person offer, request, "
                    "refusal, vote/contest signal, named recipient, or amendment instead"
                ),
            }
        thread_root = _message_thread_root(db, parent)
        duplicate_message = _find_near_duplicate_recent_forum_message(db, agent, action)
        if (
            duplicate_message is not None
            and int(duplicate_message.id) not in {int(parent.id), int(thread_root.id)}
        ):
            return {
                "valid": False,
                "reason_code": "duplicate_forum_message",
                "message_id": duplicate_message.id,
                "reason": (
                    "Near-duplicate recent forum message exists; add a concrete new fact, "
                    f"vote/contest, or reply more specifically to message #{duplicate_message.id}"
                ),
            }
        if _looks_like_personal_survival_request(thread_root.content) and _looks_like_governance_argument(content):
            return {
                "valid": False,
                "reason": "Reply content appears to target proposal/law debate rather than the selected aid thread; choose the matching proposal discussion or use contest_proposal",
            }
        thread_messages = _message_thread_messages_this_run(db, thread_root)
        duplicate_in_thread = _find_near_duplicate_in_thread(
            content=content,
            thread_messages=thread_messages,
            author_agent_id=int(agent.id),
        )
        if duplicate_in_thread is not None and int(duplicate_in_thread.id) != int(parent.id):
            return {
                "valid": False,
                "reason_code": "duplicate_thread_reply",
                "message_id": duplicate_in_thread.id,
                "thread_id": thread_root.id,
                "reason": (
                    f"Thread #{thread_root.id} already contains this point; add a concrete new "
                    "offer, refusal, amendment, named ask, or choose vote/contest/trade/direct_message"
                ),
            }
        agreement_pile_on_reason = _agreement_pile_on_reason(
            content=content,
            thread_messages=thread_messages,
        )
        if agreement_pile_on_reason:
            return {
                "valid": False,
                "reason_code": "proposal_agreement_pile_on",
                "thread_id": thread_root.id,
                "reason": agreement_pile_on_reason,
            }
        saturated_reason = _low_novelty_saturated_thread_reason(
            content=content,
            thread_messages=thread_messages,
        )
        if saturated_reason:
            return {
                "valid": False,
                "reason_code": "saturated_thread_low_novelty",
                "thread_id": thread_root.id,
                "reply_count": max(0, len(thread_messages) - 1),
                "reason": (
                    f"Thread #{thread_root.id} is saturated: {saturated_reason}. "
                    "Reply only with a concrete new offer, refusal, amendment, named ask, or move to vote/contest/trade/direct_message."
                ),
            }
        recap_reason = _obvious_governance_recap_reason(content)
        if recap_reason:
            return {
                "valid": False,
                "reason_code": "obvious_governance_recap",
                "reason": (
                    f"Forum reply {recap_reason}; move the thread with a concrete ask, offer, refusal, "
                    "amendment, contest, trade, or commitment"
                ),
            }
    
    elif action_type == "direct_message":
        recipient_id = action.get("recipient_agent_id")
        if not recipient_id:
            return {"valid": False, "reason": "Direct message requires recipient_agent_id"}
        recipient = db.query(Agent).filter(Agent.agent_number == recipient_id).first()
        if not recipient:
            return {"valid": False, "reason": "Recipient agent not found"}
        content = action.get("content", "")
        if not content or len(content) < 1:
            return {"valid": False, "reason": "Direct message requires content"}
        if len(content) > 2000:
            return {"valid": False, "reason": "Direct message too long (max 2000 chars)"}
        auto_contribution_reason = _auto_contribution_literacy_reason(content)
        if auto_contribution_reason:
            return {
                "valid": False,
                "reason_code": "auto_contribution_literacy",
                "reason": auto_contribution_reason,
            }
        repeated_denial_reason = _direct_message_already_denied_latest_request_reason(
            db,
            sender=agent,
            recipient=recipient,
            content=content,
        )
        if repeated_denial_reason:
            return {
                "valid": False,
                "reason_code": "aid_request_already_refused",
                "reason": repeated_denial_reason,
            }
        inventory_opening_reason = _misleading_private_inventory_opening_reason(action)
        if inventory_opening_reason:
            return {
                "valid": False,
                "reason_code": "misleading_private_inventory_opening",
                "reason": inventory_opening_reason,
            }
        recipient_message_count = _direct_message_recipient_count_this_run(db, recipient)
        if recipient_message_count >= 3 and recipient.id != agent.id:
            recipient_name = recipient.display_name or f"Agent #{recipient.agent_number}"
            return {
                "valid": False,
                "reason_code": "recipient_message_saturation",
                "recipient_agent_id": recipient.id,
                "recipient_agent_number": recipient.agent_number,
                "recipient_name": recipient_name,
                "reason": (
                    f"{recipient_name} has already received {recipient_message_count} direct messages "
                    "in this run; choose another "
                    "recipient or a non-DM social action"
                ),
            }

    elif action_type == "request_aid":
        target_id = action.get("target_agent_id")
        if not target_id:
            return {"valid": False, "reason": "Aid request requires target_agent_id"}
        target = db.query(Agent).filter(Agent.agent_number == target_id).first()
        if not target:
            return {"valid": False, "reason": "Target agent not found"}
        if target.id == agent.id:
            return {"valid": False, "reason": "Cannot request aid from yourself"}
        if target.status == "dead":
            return {"valid": False, "reason": "Cannot request aid from a dead agent"}
        if target.status == "dormant":
            return {"valid": False, "reason": "Cannot request aid from a dormant agent"}
        resource_type = str(action.get("resource_type") or "").strip().lower()
        if resource_type not in {"food", "energy", "materials"}:
            return {"valid": False, "reason": "Aid request requires resource_type food|energy|materials"}
        try:
            amount = Decimal(str(action.get("amount", 0)))
        except Exception:
            return {"valid": False, "reason": "Aid request amount must be numeric"}
        if amount <= 0:
            return {"valid": False, "reason": "Aid request amount must be > 0"}
        if amount > Decimal("1000"):
            return {"valid": False, "reason": "Aid request amount too large"}
        reason = action.get("reason", "")
        if not reason or len(reason) < 1:
            return {"valid": False, "reason": "Aid request requires reason"}
        if len(reason) > 1000:
            return {"valid": False, "reason": "Aid request reason too long (max 1000 chars)"}

    elif action_type == "public_accusation":
        target_id = action.get("target_agent_id")
        if not target_id:
            return {"valid": False, "reason": "Public accusation requires target_agent_id"}
        target = db.query(Agent).filter(Agent.agent_number == target_id).first()
        if not target:
            return {"valid": False, "reason": "Target agent not found"}
        if target.id == agent.id:
            return {"valid": False, "reason": "Cannot publicly accuse yourself"}
        if target.status == "dead":
            return {"valid": False, "reason": "Cannot accuse a dead agent"}
        content = action.get("content", "")
        if not content or len(content) < 1:
            return {"valid": False, "reason": "Public accusation requires content"}
        if len(content) > 1000:
            return {"valid": False, "reason": "Public accusation too long (max 1000 chars)"}

    elif action_type == "refuse_aid":
        target_id = action.get("target_agent_id")
        if not target_id:
            return {"valid": False, "reason": "Aid refusal requires target_agent_id"}
        target = db.query(Agent).filter(Agent.agent_number == target_id).first()
        if not target:
            return {"valid": False, "reason": "Target agent not found"}
        if target.id == agent.id:
            return {"valid": False, "reason": "Cannot refuse aid to yourself"}
        if target.status == "dead":
            return {"valid": False, "reason": "Cannot refuse aid to a dead agent"}
        request_event = _latest_aid_request_event(db, refuser=agent, requester=target)
        if request_event is not None and _aid_request_already_refused(
            db,
            request_event=request_event,
            refuser=agent,
            requester=target,
        ):
            return {
                "valid": False,
                "reason_code": "aid_request_already_refused",
                "request_event_id": request_event.id,
                "reason": (
                    "You already refused this agent's latest aid request. Use direct_message "
                    "only if conditions materially changed or they ask again."
                ),
            }
        reason = action.get("reason", "")
        if not reason or len(reason) < 1:
            return {"valid": False, "reason": "Aid refusal requires reason"}
        if len(reason) > 1000:
            return {"valid": False, "reason": "Aid refusal reason too long (max 1000 chars)"}

    elif action_type == "contest_proposal":
        proposal_id = action.get("proposal_id")
        if not proposal_id:
            return {"valid": False, "reason": "Proposal contest requires proposal_id"}
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if not proposal:
            return {"valid": False, "reason": "Proposal not found"}
        if not _proposal_is_within_active_run(db, proposal):
            return {"valid": False, "reason": "Can only contest a proposal from the current run"}
        if proposal.author_agent_id == agent.id:
            return {"valid": False, "reason": "Cannot contest your own proposal"}
        if proposal.status != "active":
            return {"valid": False, "reason": "Can only contest an active proposal"}
        reason = action.get("reason", "")
        if not reason or len(reason) < 1:
            return {"valid": False, "reason": "Proposal contest requires reason"}
        if len(reason) > 1000:
            return {"valid": False, "reason": "Proposal contest reason too long (max 1000 chars)"}
    
    elif action_type == "create_proposal":
        # Exiled agents cannot create proposals
        if agent.exiled:
            return {"valid": False, "reason": "You are EXILED and cannot create proposals"}
        
        # Check daily proposal limit
        day_ago = now - timedelta(days=1)
        started_at = _active_run_started_at(db)
        proposals_since = max(day_ago, started_at) if started_at else day_ago
        recent_proposals = db.query(Proposal).filter(
            Proposal.author_agent_id == agent.id,
            Proposal.created_at > proposals_since
        ).count()
        if recent_proposals >= settings.MAX_PROPOSALS_PER_DAY:
            return {"valid": False, "reason": "Daily proposal limit reached"}
        
        if not action.get("title") or not action.get("description"):
            return {"valid": False, "reason": "Proposal requires title and description"}
        proposal_type = str(action.get("proposal_type") or "other").strip().lower()
        if proposal_type not in _VALID_PROPOSAL_TYPES:
            return {
                "valid": False,
                "reason": "Proposal type must be law|allocation|rule|infrastructure|constitutional|other|resolution|standing_law|amendment|emergency_action",
                "reason_code": "invalid_proposal_type",
            }
        action["proposal_type"] = proposal_type
        _infer_active_reserve_aid_amendment_effect(db, action)
        proposal_type = str(action.get("proposal_type") or "other").strip().lower()
        governance_class = normalize_governance_class(
            proposal_type,
            action.get("governance_class") or action.get("governanceClass"),
            action.get("runtime_effect"),
        )
        runtime_effect, effect_errors = normalize_runtime_effect(
            action.get("runtime_effect"),
            governance_class=governance_class,
            db=db,
        )
        if effect_errors:
            if set(effect_errors).issubset(_UNSUPPORTED_RUNTIME_EFFECT_ERRORS):
                return {
                    "valid": False,
                    "reason_code": "unsupported_runtime_effect",
                    "reason": (
                        "; ".join(effect_errors)
                        + ". Supported runtime_effect.type values are common_pool_allocation, "
                        "active_reserve_aid, and active_reserve_aid_amendment. "
                        "Use advisory_law or resolution without runtime_effect if you mean policy text only."
                    ),
                }
            return {
                "valid": False,
                "reason_code": "invalid_runtime_effect",
                "reason": "; ".join(effect_errors),
            }
        action["governance_class"] = governance_class
        action["runtime_effect"] = runtime_effect
        _coerce_voluntary_nonbinding_law(action)
        proposal_type = str(action.get("proposal_type") or "other").strip().lower()
        if proposal_type == "rule":
            binding_signal = _binding_signal_for_rule_proposal(action)
            if binding_signal is not None:
                action["governance_class"] = "resolution"
                action["runtime_effect"] = {}
                action["binding_rule_coerced_to_resolution"] = True
                action["binding_rule_signal"] = binding_signal
        allocation_conflict_reason = _allocation_contributor_recipient_conflict_reason(action)
        if allocation_conflict_reason is not None:
            return {
                "valid": False,
                "reason_code": "allocation_contributor_recipient_conflict",
                "reason": allocation_conflict_reason,
            }
        unsupported_text_reason = _unsupported_runtime_text_reason(action)
        if unsupported_text_reason is not None:
            return {
                "valid": False,
                "reason_code": "unsupported_runtime_effect_text",
                "reason": (
                    f"{unsupported_text_reason}. Legal text alone will not create this mechanic. "
                    "Use a supported runtime_effect template, or submit an advisory_law/resolution "
                    "that does not claim execution."
                ),
            }
        covering_law = _find_covering_active_reserve_aid_law(db, action)
        if covering_law is not None:
            return {
                "valid": False,
                "reason_code": "duplicate_active_law",
                "law_id": covering_law.id,
                "reason": (
                    f"Active Law #{covering_law.id} already covers this active reserve aid mechanism; "
                    "propose a targeted amendment, contest it, or discuss the existing law instead"
                ),
            }
        duplicate = _find_near_duplicate_active_proposal(db, action)
        if duplicate is not None:
            return {
                "valid": False,
                "reason_code": "duplicate_active_proposal",
                "proposal_id": duplicate.id,
                "reason": (
                    "Near-duplicate active proposal exists; vote, contest, or discuss "
                    f"proposal #{duplicate.id} instead"
                ),
            }
    
    elif action_type == "vote":
        # Exiled agents cannot vote
        if agent.exiled:
            return {"valid": False, "reason": "You are EXILED and cannot vote"}
        
        proposal_id = action.get("proposal_id")
        if not proposal_id:
            return {"valid": False, "reason": "Vote requires proposal_id"}
        
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if not proposal:
            return {"valid": False, "reason": "Proposal not found"}
        if not _proposal_is_within_active_run(db, proposal):
            return {"valid": False, "reason": "Can only vote on a proposal from the current run"}
        if proposal.status != "active":
            return {"valid": False, "reason": "Proposal is not active"}
        voting_closes_at = ensure_utc(proposal.voting_closes_at)
        if voting_closes_at and voting_closes_at < now:
            return {"valid": False, "reason": "Voting period has ended"}
        
        # Check if already voted
        existing_vote = db.query(Vote).filter(
            Vote.proposal_id == proposal_id,
            Vote.agent_id == agent.id
        ).first()
        if existing_vote:
            return {"valid": False, "reason": "Already voted on this proposal"}
    
    elif action_type == "work":
        work_type = action.get("work_type")
        if work_type not in WORK_YIELDS:
            return {"valid": False, "reason": f"Invalid work type: {work_type}"}
        hours = action.get("hours", 1)
        if hours < 1 or hours > 8:
            return {"valid": False, "reason": "Work hours must be 1-8"}
    
    elif action_type == "trade":
        resource_type = action.get("resource_type")
        amount = action.get("amount", 0)
        
        if resource_type not in ["food", "energy", "materials"]:
            return {"valid": False, "reason": f"Invalid resource type: {resource_type}"}
        if amount <= 0:
            return {"valid": False, "reason": "Trade amount must be positive"}
        
        # Check agent has enough resources
        inventory = db.query(AgentInventory).filter(
            AgentInventory.agent_id == agent.id,
            AgentInventory.resource_type == resource_type
        ).first()
        
        if not inventory or float(inventory.quantity) < amount:
            return {"valid": False, "reason": f"Insufficient {resource_type}"}
        
        # Check recipient exists
        recipient_id = action.get("recipient_agent_id")
        recipient = db.query(Agent).filter(Agent.agent_number == recipient_id).first()
        if not recipient:
            return {"valid": False, "reason": "Recipient agent not found"}
        if recipient.status == "dead":
            return {"valid": False, "reason": "Recipient is dead and cannot receive resources"}
    
    elif action_type == "set_name":
        # Protocol-level no-op to preserve backward compatibility with older prompts.
        # This avoids converting legacy set_name attempts into invalid_action churn.
        return {"valid": True}
    
    elif action_type == "idle":
        pass  # Always valid
    
    # Phase 3: Enforcement validation
    elif action_type in ["initiate_sanction", "initiate_seizure", "initiate_exile"]:
        from app.models.models import Law, Enforcement
        
        # Check agent is not exiled (exiled agents can't enforce)
        if agent.exiled:
            return {"valid": False, "reason": "Exiled agents cannot initiate enforcement actions"}
        
        # Must cite a specific law
        law_id = action.get("law_id")
        if not law_id:
            return {"valid": False, "reason": "Enforcement must cite a specific law (law_id)"}
        
        law = db.query(Law).filter(Law.id == law_id, Law.active == True).first()
        if not law:
            return {"valid": False, "reason": f"Law #{law_id} not found or not active"}
        
        # Must specify target
        target_id = action.get("target_agent_id")
        if not target_id:
            return {"valid": False, "reason": "Must specify target_agent_id"}
        
        target = db.query(Agent).filter(Agent.agent_number == target_id).first()
        if not target:
            return {"valid": False, "reason": f"Target agent #{target_id} not found"}
        
        # Can't enforce against yourself
        if target.id == agent.id:
            return {"valid": False, "reason": "Cannot initiate enforcement against yourself"}
        
        # Can't enforce against dead agents
        if target.status == "dead":
            return {"valid": False, "reason": "Cannot enforce against dead agents"}
        
        # Must provide violation description
        if not action.get("violation_description"):
            return {"valid": False, "reason": "Must describe the violation"}
        
        # Type-specific validation
        if action_type == "initiate_sanction":
            cycles = action.get("sanction_cycles", 0)
            if cycles < 1 or cycles > 10:
                return {"valid": False, "reason": "Sanction must be 1-10 cycles"}
        
        elif action_type == "initiate_seizure":
            resource = action.get("seizure_resource")
            amount = action.get("seizure_amount", 0)
            if resource not in ["food", "energy", "materials"]:
                return {"valid": False, "reason": "Invalid seizure resource type"}
            if amount <= 0 or amount > 50:
                return {"valid": False, "reason": "Seizure amount must be 1-50"}
    
    elif action_type == "vote_enforcement":
        from app.models.models import Enforcement, EnforcementVote
        
        # Check agent is not exiled
        if agent.exiled:
            return {"valid": False, "reason": "Exiled agents cannot vote on enforcement"}
        
        enforcement_id = action.get("enforcement_id")
        if not enforcement_id:
            return {"valid": False, "reason": "Must specify enforcement_id"}
        
        enforcement = db.query(Enforcement).filter(
            Enforcement.id == enforcement_id,
            Enforcement.status == "pending"
        ).first()
        if not enforcement:
            return {"valid": False, "reason": f"Enforcement #{enforcement_id} not found or not pending"}
        voting_closes_at = ensure_utc(enforcement.voting_closes_at)
        if voting_closes_at and voting_closes_at < now:
            return {"valid": False, "reason": "Enforcement voting period has ended"}
        
        # Check hasn't voted already
        existing = db.query(EnforcementVote).filter(
            EnforcementVote.enforcement_id == enforcement_id,
            EnforcementVote.agent_id == agent.id
        ).first()
        if existing:
            return {"valid": False, "reason": "Already voted on this enforcement"}
        
        vote = action.get("vote")
        if vote not in ["support", "oppose"]:
            return {"valid": False, "reason": "Vote must be 'support' or 'oppose'"}
    
    else:
        return {"valid": False, "reason": f"Unknown action type: {action_type}"}
    
    return {"valid": True}


async def execute_action(db: Session, agent: Agent, action: dict) -> dict:
    """Execute a validated action."""
    action_type = action.get("action")
    result = {"success": False, "description": "Unknown action"}
    
    # Record action for rate limiting
    agent_action = AgentAction(
        agent_id=agent.id,
        action_type=action_type
    )
    db.add(agent_action)
    
    # Deduct energy cost for action (Phase 2: Teeth)
    action_cost = action_energy_cost(action_type, action)
    if action_cost > 0:
        energy_inv = db.query(AgentInventory).filter(
            AgentInventory.agent_id == agent.id,
            AgentInventory.resource_type == "energy"
        ).first()
        
        if energy_inv:
            energy_inv.quantity -= action_cost
            
            # Record transaction
            transaction = Transaction(
                from_agent_id=agent.id,
                resource_type="energy",
                amount=action_cost,
                transaction_type="action_cost"
            )
            db.add(transaction)
    
    if action_type == "forum_post":
        result = await _execute_forum_post(db, agent, action)
    
    elif action_type == "forum_reply":
        result = await _execute_forum_reply(db, agent, action)
    
    elif action_type == "direct_message":
        result = await _execute_direct_message(db, agent, action)

    elif action_type == "request_aid":
        result = await _execute_request_aid(db, agent, action)

    elif action_type == "public_accusation":
        result = await _execute_public_accusation(db, agent, action)

    elif action_type == "refuse_aid":
        result = await _execute_refuse_aid(db, agent, action)

    elif action_type == "contest_proposal":
        result = await _execute_contest_proposal(db, agent, action)
    
    elif action_type == "create_proposal":
        result = await _execute_create_proposal(db, agent, action)
    
    elif action_type == "vote":
        result = await _execute_vote(db, agent, action)
    
    elif action_type == "work":
        result = await _execute_work(db, agent, action)
    
    elif action_type == "trade":
        result = await _execute_trade(db, agent, action)
    
    elif action_type == "idle":
        result = {"success": True, "description": _idle_description(action)}
    
    # Phase 3: Enforcement actions
    elif action_type == "initiate_sanction":
        result = await _execute_initiate_enforcement(db, agent, action, "sanction")
    
    elif action_type == "initiate_seizure":
        result = await _execute_initiate_enforcement(db, agent, action, "seizure")
    
    elif action_type == "initiate_exile":
        result = await _execute_initiate_enforcement(db, agent, action, "exile")
    
    elif action_type == "vote_enforcement":
        result = await _execute_vote_enforcement(db, agent, action)

    elif action_type == "set_name":
        result = {
            "success": True,
            "description": "Alias change ignored: aliases are immutable in this protocol",
        }
    
    # Add cost info to result if applicable
    if action_cost > 0 and result.get("success"):
        result["energy_cost"] = float(action_cost)
    
    db.commit()
    return result


async def _execute_forum_post(db: Session, agent: Agent, action: dict) -> dict:
    """Create a forum post."""
    message = Message(
        author_agent_id=agent.id,
        content=action["content"],
        message_type="forum_post"
    )
    db.add(message)
    db.flush()
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    content_preview = " ".join((str(action.get("content") or "").split()))[:180]
    return {
        "success": True,
        "description": f"{author_name} posted to the forum",
        "message_id": message.id,
        "author_agent_number": int(agent.agent_number),
        "author_name": author_name,
        "content_preview": content_preview,
    }


async def _execute_forum_reply(db: Session, agent: Agent, action: dict) -> dict:
    """Reply to a forum post."""
    message = Message(
        author_agent_id=agent.id,
        content=action["content"],
        message_type="forum_reply",
        parent_message_id=action["parent_message_id"]
    )
    db.add(message)
    db.flush()
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    content_preview = " ".join((str(action.get("content") or "").split()))[:180]
    return {
        "success": True,
        "description": f"{author_name} replied to a forum post",
        "message_id": message.id,
        "author_agent_number": int(agent.agent_number),
        "author_name": author_name,
        "parent_message_id": int(action["parent_message_id"]),
        "content_preview": content_preview,
    }


async def _execute_direct_message(db: Session, agent: Agent, action: dict) -> dict:
    """Send a direct message."""
    recipient = db.query(Agent).filter(
        Agent.agent_number == action["recipient_agent_id"]
    ).first()
    
    message = Message(
        author_agent_id=agent.id,
        content=action["content"],
        message_type="direct_message",
        recipient_agent_id=recipient.id
    )
    db.add(message)
    db.flush()
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    recipient_name = recipient.display_name or f"Agent #{recipient.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} sent a message to {recipient_name}",
        "message_id": message.id,
        "author_agent_number": int(agent.agent_number),
        "author_name": author_name,
        "recipient_agent_number": int(recipient.agent_number),
        "recipient_name": recipient_name,
        "content_preview": " ".join((str(action.get("content") or "").split()))[:180],
    }


async def _execute_request_aid(db: Session, agent: Agent, action: dict) -> dict:
    """Request targeted aid from another agent."""
    target = db.query(Agent).filter(
        Agent.agent_number == action["target_agent_id"]
    ).first()

    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    target_name = target.display_name or f"Agent #{target.agent_number}"
    resource_type = str(action.get("resource_type") or "").strip().lower()
    amount = Decimal(str(action.get("amount")))
    reason_text = " ".join((action.get("reason") or "").split())
    message_content = (
        f"Can you send {amount.normalize()} {resource_type}? {reason_text}"
    )

    message = Message(
        author_agent_id=agent.id,
        content=message_content,
        message_type="direct_message",
        recipient_agent_id=target.id,
    )
    db.add(message)
    db.flush()

    db.add(
        Event(
            agent_id=target.id,
            event_type="aid_request_received",
            description=f"🆘 {author_name} requested {amount.normalize()} {resource_type} from you: {reason_text}",
            event_metadata=_with_runtime_metadata(
                {
                    "requesting_agent_id": agent.id,
                    "requesting_agent_number": agent.agent_number,
                    "target_agent_id": target.id,
                    "target_agent_number": target.agent_number,
                    "resource_type": resource_type,
                    "amount": str(amount),
                    "message_id": message.id,
                }
            ),
        )
    )
    relationship_memory_service.record_aid_request(db, requester=agent, target=target)

    return {
        "success": True,
        "description": f"{author_name} requested {amount.normalize()} {resource_type} from {target_name}",
        "message_id": message.id,
    }


async def _execute_public_accusation(db: Session, agent: Agent, action: dict) -> dict:
    """Make a public accusation against another agent without formal enforcement."""
    target = db.query(Agent).filter(
        Agent.agent_number == action["target_agent_id"]
    ).first()

    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    target_name = target.display_name or f"Agent #{target.agent_number}"
    accusation_text = " ".join((action.get("content") or "").split())
    post_content = (
        f"Public accusation against {target_name} (Agent #{target.agent_number}): "
        f"{accusation_text}"
    )

    message = Message(
        author_agent_id=agent.id,
        content=post_content,
        message_type="forum_post",
    )
    db.add(message)
    db.flush()

    db.add(
        Event(
            agent_id=target.id,
            event_type="accusation_received",
            description=f"⚠️ {author_name} publicly accused you: {accusation_text}",
            event_metadata=_with_runtime_metadata(
                {
                    "accuser_agent_id": agent.id,
                    "accuser_agent_number": agent.agent_number,
                    "target_agent_id": target.id,
                    "target_agent_number": target.agent_number,
                    "message_id": message.id,
                }
            ),
        )
    )
    relationship_memory_service.record_public_accusation(db, accuser=agent, target=target)

    return {
        "success": True,
        "description": f"{author_name} publicly accused {target_name}",
        "message_id": message.id,
    }


async def _execute_refuse_aid(db: Session, agent: Agent, action: dict) -> dict:
    """Directly refuse to provide aid to another agent."""
    target = db.query(Agent).filter(
        Agent.agent_number == action["target_agent_id"]
    ).first()
    request_event = _latest_aid_request_event(db, refuser=agent, requester=target)
    request_metadata = request_event.event_metadata if request_event and isinstance(request_event.event_metadata, dict) else {}

    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    target_name = target.display_name or f"Agent #{target.agent_number}"
    reason_text = " ".join((action.get("reason") or "").split())
    message_content = (
        f"I cannot provide aid right now. {reason_text}"
    )

    message = Message(
        author_agent_id=agent.id,
        content=message_content,
        message_type="direct_message",
        recipient_agent_id=target.id,
    )
    db.add(message)
    db.flush()

    db.add(
        Event(
            agent_id=target.id,
            event_type="aid_refusal_received",
            description=f"❌ {author_name} refused to provide aid: {reason_text}",
            event_metadata=_with_runtime_metadata(
                {
                    "refusing_agent_id": agent.id,
                    "refusing_agent_number": agent.agent_number,
                    "target_agent_id": target.id,
                    "target_agent_number": target.agent_number,
                    "message_id": message.id,
                    "request_event_id": request_event.id if request_event else None,
                    "request_message_id": request_metadata.get("message_id"),
                }
            ),
        )
    )
    relationship_memory_service.record_aid_refusal(db, refuser=agent, target=target)

    return {
        "success": True,
        "description": f"{author_name} refused aid to {target_name}",
        "message_id": message.id,
    }


async def _execute_contest_proposal(db: Session, agent: Agent, action: dict) -> dict:
    """Publicly contest another agent's active proposal."""
    proposal = db.query(Proposal).filter(Proposal.id == action["proposal_id"]).first()
    proposal_author = db.query(Agent).filter(Agent.id == proposal.author_agent_id).first()

    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    proposal_author_name = (
        proposal_author.display_name or f"Agent #{proposal_author.agent_number}"
        if proposal_author is not None
        else f"Agent #{proposal.author_agent_id}"
    )
    reason_text = " ".join((action.get("reason") or "").split())
    post_content = (
        f"Contesting proposal \"{proposal.title}\" (#{proposal.id}) by {proposal_author_name}: {reason_text}"
    )

    message = Message(
        author_agent_id=agent.id,
        content=post_content,
        message_type="forum_post",
    )
    db.add(message)
    db.flush()

    if proposal_author is not None and proposal_author.id != agent.id:
        db.add(
            Event(
                agent_id=proposal_author.id,
                event_type="proposal_contested_received",
                description=f"⚖️ {author_name} publicly contested your proposal \"{proposal.title}\": {reason_text}",
                event_metadata=_with_runtime_metadata(
                    {
                        "contesting_agent_id": agent.id,
                        "contesting_agent_number": agent.agent_number,
                        "proposal_id": proposal.id,
                        "proposal_title": proposal.title,
                        "proposal_author_agent_id": proposal.author_agent_id,
                        "message_id": message.id,
                    }
                ),
            )
        )
        relationship_memory_service.record_proposal_contest(
            db,
            challenger=agent,
            target=proposal_author,
        )

    return {
        "success": True,
        "description": f"{author_name} contested proposal: {proposal.title}",
        "message_id": message.id,
        "proposal_id": proposal.id,
    }


async def _execute_create_proposal(db: Session, agent: Agent, action: dict) -> dict:
    """Create a new proposal."""
    raw_voting_hours = runtime_config_service.get_effective_value_cached("PROPOSAL_VOTING_HOURS")
    try:
        voting_hours = max(0.05, float(raw_voting_hours or settings.PROPOSAL_VOTING_HOURS))
    except Exception:
        voting_hours = float(settings.PROPOSAL_VOTING_HOURS)
    voting_period = timedelta(hours=voting_hours)
    
    proposal = Proposal(
        author_agent_id=agent.id,
        title=action["title"],
        description=action["description"],
        proposal_type=str(action.get("proposal_type") or "other").strip().lower(),
        governance_class=str(action.get("governance_class") or "").strip().lower() or None,
        runtime_effect=action.get("runtime_effect") if isinstance(action.get("runtime_effect"), dict) else {},
        voting_closes_at=now_utc() + voting_period
    )
    db.add(proposal)
    db.flush()
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} created proposal: {action['title']}",
        "proposal_id": proposal.id
    }


async def _execute_vote(db: Session, agent: Agent, action: dict) -> dict:
    """Vote on a proposal."""
    proposal = db.query(Proposal).filter(Proposal.id == action["proposal_id"]).first()
    
    vote = Vote(
        proposal_id=proposal.id,
        agent_id=agent.id,
        vote=action["vote"],
        reasoning=action.get("reasoning")
    )
    db.add(vote)
    
    # Update vote counts
    if action["vote"] == "yes":
        proposal.votes_for += 1
    elif action["vote"] == "no":
        proposal.votes_against += 1
    else:
        proposal.votes_abstain += 1

    if proposal.author_agent_id != agent.id:
        proposal_author = db.query(Agent).filter(Agent.id == proposal.author_agent_id).first()
        if proposal_author is not None:
            relationship_memory_service.record_vote_alignment(
                db,
                voter=agent,
                proposal_author=proposal_author,
                vote=action["vote"],
            )
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    return {
        "success": True,
        "description": f"{author_name} voted {action['vote']} on Proposal #{proposal.id}: {proposal.title}",
    }


async def _execute_work(db: Session, agent: Agent, action: dict) -> dict:
    """Perform work to produce resources."""
    work_type = action["work_type"]
    hours = action.get("hours", 1)
    
    work_info = WORK_YIELDS[work_type]
    resource_type = work_info["resource"]
    base_yield = work_base_yield(work_type)
    efficiency = EFFICIENCY_CURVE.get(hours, 0.7)
    production_modifier = Decimal(str(event_generator.get_production_modifier(resource_type)))

    produced_amount = (
        base_yield
        * Decimal(str(hours))
        * Decimal(str(efficiency))
        * production_modifier
    ).quantize(Decimal("0.01"))
    contribution_amount = Decimal("0")
    contribution_rate = Decimal("0")
    reserve_active = False
    active_reserve_laws: list[Law] = []
    pool_before: Decimal | None = None
    pool_after: Decimal | None = None

    if resource_type in {"food", "energy"} and survival_reserve_law_active(db):
        reserve_active = True
        active_reserve_laws = active_survival_reserve_laws(db)
        contribution_rate = survival_reserve_contribution_rate(
            resource_type,
            energy_reserve=current_energy_reserve(db),
        )
        contribution_amount = (produced_amount * contribution_rate).quantize(Decimal("0.01"))
        if contribution_amount > produced_amount:
            contribution_amount = produced_amount

    amount_kept = produced_amount - contribution_amount
    
    # Add to agent's inventory
    inventory = db.query(AgentInventory).filter(
        AgentInventory.agent_id == agent.id,
        AgentInventory.resource_type == resource_type
    ).first()
    
    if inventory:
        inventory.quantity += amount_kept
    else:
        inventory = AgentInventory(
            agent_id=agent.id,
            resource_type=resource_type,
            quantity=amount_kept
        )
        db.add(inventory)

    if contribution_amount > 0:
        global_resource = db.query(GlobalResources).filter(
            GlobalResources.resource_type == resource_type
        ).first()
        if global_resource:
            pool_before = Decimal(str(global_resource.in_common_pool or 0))
            global_resource.in_common_pool += contribution_amount
            pool_after = Decimal(str(global_resource.in_common_pool or 0))
        db.add(
            Transaction(
                from_agent_id=agent.id,
                resource_type=resource_type,
                amount=contribution_amount,
                transaction_type="allocation",
            )
        )

    # Record transaction
    transaction = Transaction(
        to_agent_id=agent.id,
        resource_type=resource_type,
        amount=amount_kept,
        transaction_type="work_production"
    )
    db.add(transaction)
    
    author_name = agent.display_name or f"Agent #{agent.agent_number}"
    work_type_label = {
        "farm": "farmed",
        "generate": "generated",
        "gather": "gathered",
    }.get(work_type, "produced")
    description = f"{author_name} {work_type_label} {float(amount_kept):.2f} {resource_type} in {hours}h"
    if production_modifier != Decimal("1.0"):
        description += f" (environment modifier {float(production_modifier):.2f}x)"
    if reserve_active and contribution_amount > 0:
        description += (
            f" and contributed {float(contribution_amount):.2f} {resource_type} to the shared reserve"
        )
    result = {"success": True, "description": description}
    if reserve_active and contribution_amount > 0:
        result["reserve_contribution"] = {
            "resource": resource_type,
            "amount": _decimal_payload(contribution_amount),
            "rate": float(contribution_rate),
            "produced_amount": _decimal_payload(produced_amount),
            "kept_amount": _decimal_payload(amount_kept),
            "pool_before": _decimal_payload(pool_before),
            "pool_after": _decimal_payload(pool_after),
            "active_law_ids": [
                int(law.id) for law in active_reserve_laws if getattr(law, "id", None) is not None
            ],
            "active_law_count": len(active_reserve_laws),
        }
        result["pool_accessibility_context"] = _reserve_accessibility_context(
            db,
            active_laws=active_reserve_laws,
        )
    return result


async def _execute_trade(db: Session, agent: Agent, action: dict) -> dict:
    """Trade resources with another agent."""
    recipient = db.query(Agent).filter(
        Agent.agent_number == action["recipient_agent_id"]
    ).first()
    
    resource_type = action["resource_type"]
    amount = Decimal(str(action["amount"]))

    if not recipient:
        return {"success": False, "description": "Recipient agent not found"}

    recipient_name = recipient.display_name or f"Agent #{recipient.agent_number}"
    if recipient.status == "dead":
        return {"success": False, "description": f"{recipient_name} is dead and cannot receive resources"}
    
    # Decrease sender's inventory
    sender_inv = db.query(AgentInventory).filter(
        AgentInventory.agent_id == agent.id,
        AgentInventory.resource_type == resource_type
    ).first()
    if not sender_inv or sender_inv.quantity < amount:
        return {"success": False, "description": f"Insufficient {resource_type} to trade"}
    sender_inv.quantity -= amount
    
    # Increase recipient's inventory
    recipient_inv = db.query(AgentInventory).filter(
        AgentInventory.agent_id == recipient.id,
        AgentInventory.resource_type == resource_type
    ).first()
    
    if recipient_inv:
        recipient_inv.quantity += amount
    else:
        recipient_inv = AgentInventory(
            agent_id=recipient.id,
            resource_type=resource_type,
            quantity=amount
        )
        db.add(recipient_inv)
    
    # Record transaction
    transaction = Transaction(
        from_agent_id=agent.id,
        to_agent_id=recipient.id,
        resource_type=resource_type,
        amount=amount,
        transaction_type="trade"
    )
    db.add(transaction)
    relationship_memory_service.record_trade(db, sender=agent, recipient=recipient)
    
    sender_name = agent.display_name or f"Agent #{agent.agent_number}"
    
    # Check if this awakens a dormant agent.
    # Revival requires enough resources to pay the next active survival cycle.
    awakened = False
    if recipient.status == "dormant":
        # Check if recipient now has enough to survive the next cycle
        food_inv = db.query(AgentInventory).filter(
            AgentInventory.agent_id == recipient.id,
            AgentInventory.resource_type == "food"
        ).first()
        energy_inv = db.query(AgentInventory).filter(
            AgentInventory.agent_id == recipient.id,
            AgentInventory.resource_type == "energy"
        ).first()
        
        food_amount = float(food_inv.quantity) if food_inv else 0
        energy_amount = float(energy_inv.quantity) if energy_inv else 0
        
        required_food = float(active_food_cost())
        required_energy = float(active_energy_cost())
        if food_amount >= required_food and energy_amount >= required_energy:
            recipient.status = "active"
            recipient.starvation_cycles = 0  # Reset starvation counter on revival
            awakened = True
            
            # Log revival event
            from app.models.models import Event
            event = Event(
                agent_id=recipient.id,
                event_type="agent_revived",
                description=f"🌟 {recipient_name} has been revived thanks to resources from {sender_name}!",
                event_metadata=_with_runtime_metadata(
                    {
                        "revived_by": agent.agent_number,
                        "food": food_amount,
                        "energy": energy_amount,
                    }
                ),
            )
            db.add(event)
    
    description = f"{sender_name} traded {amount} {resource_type} to {recipient_name}"
    if awakened:
        description += f" (🌟 revived {recipient_name}!)"
    
    return {"success": True, "description": description}


# ============================================================================
# PHASE 3: ENFORCEMENT ACTIONS
# ============================================================================

async def _execute_initiate_enforcement(db: Session, agent: Agent, action: dict, enforcement_type: str) -> dict:
    """
    Initiate an enforcement action against another agent.
    
    Enforcement requires community support to execute:
    - 5 supporting votes to proceed
    - 24 hour voting window
    - Costs significant energy to initiate
    """
    from app.models.models import Enforcement, Law, Event
    
    target = db.query(Agent).filter(
        Agent.agent_number == action["target_agent_id"]
    ).first()
    
    law = db.query(Law).filter(Law.id == action["law_id"]).first()
    
    initiator_name = agent.display_name or f"Agent #{agent.agent_number}"
    target_name = target.display_name or f"Agent #{target.agent_number}"
    
    # Calculate voting window (24 hours)
    voting_closes = now_utc() + timedelta(hours=24)
    
    # Create enforcement record
    enforcement = Enforcement(
        initiator_agent_id=agent.id,
        target_agent_id=target.id,
        enforcement_type=enforcement_type,
        law_id=law.id,
        violation_description=action["violation_description"],
        votes_required=5,  # Need 5 supporters
        voting_closes_at=voting_closes,
    )
    
    # Add type-specific details
    if enforcement_type == "sanction":
        enforcement.sanction_cycles = action.get("sanction_cycles", 3)
    elif enforcement_type == "seizure":
        enforcement.seizure_resource = action.get("seizure_resource")
        enforcement.seizure_amount = Decimal(str(action.get("seizure_amount", 0)))
    
    db.add(enforcement)
    db.flush()  # Get the ID
    
    # Create event
    action_descriptions = {
        "sanction": f"sanction (restrict actions for {enforcement.sanction_cycles} cycles)",
        "seizure": f"seizure ({enforcement.seizure_amount} {enforcement.seizure_resource})",
        "exile": "exile (remove voting rights)"
    }
    
    event = Event(
        agent_id=agent.id,
        event_type="enforcement_initiated",
        description=f"⚖️ {initiator_name} has initiated {enforcement_type} against {target_name} for violating '{law.title}'",
        event_metadata=_with_runtime_metadata(
            {
                "enforcement_id": enforcement.id,
                "enforcement_type": enforcement_type,
                "target_agent": target.agent_number,
                "law_id": law.id,
                "law_title": law.title,
                "violation": action["violation_description"],
                "action": action_descriptions.get(enforcement_type, enforcement_type),
            }
        ),
    )
    db.add(event)
    
    # Create system message to alert community
    from app.models.models import Message
    alert = Message(
        author_agent_id=agent.id,
        content=f"⚖️ **ENFORCEMENT ACTION INITIATED**\n\n"
                f"{initiator_name} accuses {target_name} of violating the law: **{law.title}**\n\n"
                f"**Violation:** {action['violation_description']}\n\n"
                f"**Proposed action:** {action_descriptions.get(enforcement_type, enforcement_type)}\n\n"
                f"This enforcement requires 5 supporting votes to proceed. "
                f"Use 'vote_enforcement' with enforcement_id={enforcement.id} to support or oppose.",
        message_type="system_alert"
    )
    db.add(alert)
    
    return {
        "success": True,
        "description": f"⚖️ {initiator_name} initiated {enforcement_type} against {target_name} for violating '{law.title}'. Requires 5 supporters.",
        "enforcement_id": enforcement.id
    }


async def _execute_vote_enforcement(db: Session, agent: Agent, action: dict) -> dict:
    """
    Vote to support or oppose an enforcement action.
    
    If enough support is gathered, the enforcement executes automatically.
    """
    from app.models.models import Enforcement, EnforcementVote, Event
    
    enforcement_id = action["enforcement_id"]
    vote = action["vote"]  # "support" or "oppose"
    
    enforcement = db.query(Enforcement).filter(
        Enforcement.id == enforcement_id
    ).first()
    if not enforcement:
        return {"success": False, "description": f"Enforcement #{enforcement_id} not found"}
    if enforcement.status != "pending":
        return {"success": False, "description": f"Enforcement #{enforcement_id} is not pending"}

    closes_at = ensure_utc(enforcement.voting_closes_at)
    if closes_at and closes_at < now_utc():
        return {"success": False, "description": f"Voting window for enforcement #{enforcement_id} has closed"}
    
    voter_name = agent.display_name or f"Agent #{agent.agent_number}"
    target = enforcement.target
    target_name = target.display_name or f"Agent #{target.agent_number}"
    
    # Record vote
    enforcement_vote = EnforcementVote(
        enforcement_id=enforcement_id,
        agent_id=agent.id,
        vote=vote,
        reasoning=action.get("reasoning")
    )
    db.add(enforcement_vote)
    
    # Update vote counts
    if vote == "support":
        enforcement.support_votes += 1
    else:
        enforcement.oppose_votes += 1
    
    # Check if enough support to execute
    if enforcement.support_votes >= enforcement.votes_required:
        # EXECUTE THE ENFORCEMENT
        enforcement.status = "approved"
        enforcement.executed_at = now_utc()
        
        result = await _execute_enforcement(db, enforcement)
        enforcement.status = "executed"
        
        return {
            "success": True,
            "description": f"⚖️ {voter_name} voted to {vote} enforcement #{enforcement_id}. "
                          f"ENFORCEMENT APPROVED AND EXECUTED! {result}"
        }
    
    # Check if enough opposition to reject
    total_possible_votes = int(
        db.query(func.count(Agent.id))
        .filter(
            Agent.status != "dead",
            Agent.exiled.is_(False),
        )
        .scalar()
        or 0
    )
    votes_cast = enforcement.support_votes + enforcement.oppose_votes
    remaining_votes = max(0, total_possible_votes - votes_cast)
    max_possible_support = enforcement.support_votes + remaining_votes

    if max_possible_support < enforcement.votes_required:
        enforcement.status = "rejected"
        return {
            "success": True,
            "description": f"⚖️ {voter_name} voted to {vote} enforcement #{enforcement_id}. "
                          f"Enforcement REJECTED - not enough support possible."
        }
    
    return {
        "success": True,
        "description": f"⚖️ {voter_name} voted to {vote} enforcement #{enforcement_id} against {target_name}. "
                      f"({enforcement.support_votes}/{enforcement.votes_required} support, "
                      f"{enforcement.oppose_votes} oppose)"
    }


async def _execute_enforcement(db: Session, enforcement) -> str:
    """
    Actually execute an approved enforcement action.
    
    - Sanctions: Restrict agent's action rate
    - Seizures: Take resources from agent
    - Exile: Remove voting/proposal rights
    """
    from app.models.models import Event, Transaction
    
    target = enforcement.target
    target_name = target.display_name or f"Agent #{target.agent_number}"
    
    if enforcement.enforcement_type == "sanction":
        # Apply sanction - reduce rate limit until end date
        # Each cycle is ~60 minutes, sanction_cycles is in cycles
        hours = enforcement.sanction_cycles * 1  # 1 hour per cycle
        target.sanctioned_until = now_utc() + timedelta(hours=hours)
        
        event = Event(
            agent_id=target.id,
            event_type="agent_sanctioned",
            description=f"🔒 {target_name} has been SANCTIONED for {enforcement.sanction_cycles} cycles",
            event_metadata=_with_runtime_metadata(
                {
                    "enforcement_id": enforcement.id,
                    "sanction_cycles": enforcement.sanction_cycles,
                    "sanctioned_until": target.sanctioned_until.isoformat(),
                }
            ),
        )
        db.add(event)
        
        return f"{target_name} sanctioned for {enforcement.sanction_cycles} cycles"
    
    elif enforcement.enforcement_type == "seizure":
        # Seize resources from target
        inventory = db.query(AgentInventory).filter(
            AgentInventory.agent_id == target.id,
            AgentInventory.resource_type == enforcement.seizure_resource
        ).first()
        
        actual_amount = min(
            enforcement.seizure_amount,
            Decimal(str(inventory.quantity)) if inventory else Decimal("0")
        )
        
        if inventory and actual_amount > 0:
            inventory.quantity -= actual_amount
            
            # Record transaction
            transaction = Transaction(
                from_agent_id=target.id,
                resource_type=enforcement.seizure_resource,
                amount=actual_amount,
                transaction_type="seizure"
            )
            db.add(transaction)
        
        event = Event(
            agent_id=target.id,
            event_type="resources_seized",
            description=f"💰 {actual_amount} {enforcement.seizure_resource} SEIZED from {target_name}",
            event_metadata=_with_runtime_metadata(
                {
                    "enforcement_id": enforcement.id,
                    "resource": enforcement.seizure_resource,
                    "amount": float(actual_amount),
                }
            ),
        )
        db.add(event)
        
        return f"Seized {actual_amount} {enforcement.seizure_resource} from {target_name}"
    
    elif enforcement.enforcement_type == "exile":
        # Remove voting and proposal rights
        target.exiled = True
        
        event = Event(
            agent_id=target.id,
            event_type="agent_exiled",
            description=f"🚫 {target_name} has been EXILED - voting and proposal rights revoked",
            event_metadata=_with_runtime_metadata({"enforcement_id": enforcement.id}),
        )
        db.add(event)
        
        return f"{target_name} has been exiled from the community"
    
    return "Enforcement executed"
