"""Aid request lifecycle classification shared by UI and agent context."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import ensure_utc, now_utc
from app.models.models import Agent, AgentInventory, Event
from app.services.live_run_scope import LiveRunWindow, apply_run_window
from app.services.survival_config import active_energy_cost, active_food_cost


AID_LIFECYCLE_STATUSES = (
    "fulfilled_by_trade",
    "refused",
    "reserve_covered",
    "answered_directly",
    "mechanically_unaffordable",
    "stale_resource_changed",
    "unresolved",
)

TRACE_EVENT_TYPES = (
    "trade",
    "refuse_aid",
    "aid_refusal_received",
    "direct_message",
    "reserve_aid",
    "reserve_shortfall",
    "became_dormant",
    "agent_died",
)

STALE_RESOURCE_CHANGE_MINUTES = 30


def event_runtime_run_id(event: Event) -> str:
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    runtime = metadata.get("runtime") if isinstance(metadata, dict) else {}
    return str((runtime or {}).get("run_id") or "").strip()


def event_action(event: Event) -> dict[str, Any]:
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    action = metadata.get("action") if isinstance(metadata, dict) else {}
    return action if isinstance(action, dict) else {}


def event_result(event: Event) -> dict[str, Any]:
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    result = metadata.get("result") if isinstance(metadata, dict) else {}
    return result if isinstance(result, dict) else {}


def agent_label(agent: Agent | None) -> dict[str, Any] | None:
    if agent is None:
        return None
    return {
        "id": int(agent.id),
        "agent_number": int(agent.agent_number),
        "display_name": agent.display_name,
        "tier": int(agent.tier or 0),
        "personality_type": str(agent.personality_type or ""),
        "status": str(agent.status or ""),
    }


def aid_status_counts() -> dict[str, int]:
    return {status: 0 for status in AID_LIFECYCLE_STATUSES}


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def _request_metadata(event: Event) -> dict[str, Any]:
    return event.event_metadata if isinstance(event.event_metadata, dict) else {}


def _request_parties(db: Session, request_event: Event) -> tuple[Agent | None, Agent | None]:
    if request_event.event_type == "aid_request_received":
        metadata = _request_metadata(request_event)
        requester_id = int(metadata.get("requesting_agent_id") or 0)
        target_id = int(metadata.get("target_agent_id") or request_event.agent_id or 0)
        requester = db.query(Agent).filter(Agent.id == requester_id).first() if requester_id > 0 else None
        target = db.query(Agent).filter(Agent.id == target_id).first() if target_id > 0 else None
        return requester, target

    if request_event.event_type == "request_aid":
        requester_id = int(request_event.agent_id or 0)
        action = event_action(request_event)
        target_number = int(action.get("target_agent_id") or 0)
        requester = db.query(Agent).filter(Agent.id == requester_id).first() if requester_id > 0 else None
        target = db.query(Agent).filter(Agent.agent_number == target_number).first() if target_number > 0 else None
        return requester, target

    return None, None


def _request_resource_and_amount(request_event: Event) -> tuple[str, Decimal]:
    if request_event.event_type == "aid_request_received":
        metadata = _request_metadata(request_event)
        return (
            str(metadata.get("resource_type") or "").strip().lower(),
            _decimal_value(metadata.get("amount")),
        )

    action = event_action(request_event)
    return (
        str(action.get("resource_type") or "").strip().lower(),
        _decimal_value(action.get("amount")),
    )


def _request_reason(request_event: Event) -> str:
    if request_event.event_type == "request_aid":
        return str(event_action(request_event).get("reason") or "").strip()
    metadata = _request_metadata(request_event)
    return str(metadata.get("reason") or "").strip()


def _request_message_id(request_event: Event) -> Any:
    if request_event.event_type == "aid_request_received":
        return _request_metadata(request_event).get("message_id")
    return event_result(request_event).get("message_id")


def _event_matches_run(event: Event, run_window: LiveRunWindow | None) -> bool:
    if run_window is None or run_window.run_id is None:
        return True
    run_id = str(run_window.run_id or "").strip()
    tagged_run_id = event_runtime_run_id(event)
    return tagged_run_id in {"", run_id}


def _trace_events_for_request(
    db: Session,
    *,
    request_event: Event,
    run_window: LiveRunWindow | None = None,
) -> list[Event]:
    request_at = ensure_utc(request_event.created_at)
    query = db.query(Event).filter(Event.event_type.in_(TRACE_EVENT_TYPES))
    if request_at is not None:
        query = query.filter(Event.created_at >= request_at)
    if run_window is not None and run_window.run_id is not None:
        query = apply_run_window(query, Event.created_at, run_window)
    events = query.order_by(Event.created_at.asc(), Event.id.asc()).limit(300).all()
    return [event for event in events if _event_matches_run(event, run_window)]


def _response_refuses_request(
    *,
    event: Event,
    requester: Agent,
    target: Agent,
    request_message_id: Any,
) -> bool:
    if event.event_type == "refuse_aid":
        action = event_action(event)
        return int(event.agent_id or 0) == int(target.id) and int(action.get("target_agent_id") or 0) == int(
            requester.agent_number
        )

    if event.event_type != "aid_refusal_received":
        return False

    metadata = _request_metadata(event)
    try:
        refusing_agent_id = int(metadata.get("refusing_agent_id") or 0)
        target_agent_id = int(metadata.get("target_agent_id") or 0)
    except (TypeError, ValueError):
        return False
    if refusing_agent_id != int(target.id) or target_agent_id != int(requester.id):
        return False
    if request_message_id is None:
        return True
    event_request_message_id = metadata.get("request_message_id")
    return event_request_message_id in (None, "") or str(event_request_message_id) == str(request_message_id)


def _event_is_trade_fulfillment(event: Event, *, requester: Agent, target: Agent, resource_type: str) -> bool:
    if event.event_type != "trade" or int(event.agent_id or 0) != int(target.id):
        return False
    action = event_action(event)
    recipient_number = int(action.get("recipient_agent_id") or 0)
    if recipient_number != int(requester.agent_number):
        return False
    trade_resource = str(action.get("resource_type") or "").strip().lower()
    return not resource_type or trade_resource == resource_type


def _event_is_direct_answer(event: Event, *, requester: Agent, target: Agent) -> bool:
    if event.event_type != "direct_message" or int(event.agent_id or 0) != int(target.id):
        return False
    action = event_action(event)
    return int(action.get("recipient_agent_id") or 0) == int(requester.agent_number)


def _agent_inventory_map(db: Session, agent: Agent) -> dict[str, Decimal]:
    rows = db.query(AgentInventory).filter(AgentInventory.agent_id == agent.id).all()
    inventory = {"food": Decimal("0"), "energy": Decimal("0"), "materials": Decimal("0")}
    for row in rows:
        inventory[str(row.resource_type)] = _decimal_value(row.quantity)
    return inventory


def _request_is_stale_due_resource_change(
    db: Session,
    *,
    request_event: Event,
    requester: Agent,
    resource_type: str,
    requested_amount: Decimal,
) -> bool:
    request_at = ensure_utc(request_event.created_at)
    if request_at is None:
        return False
    age = now_utc() - request_at
    if age < timedelta(minutes=STALE_RESOURCE_CHANGE_MINUTES):
        return False
    if str(requester.status or "") == "dead":
        return True

    inventory = _agent_inventory_map(db, requester)
    can_pay_active = (
        inventory.get("food", Decimal("0")) >= active_food_cost()
        and inventory.get("energy", Decimal("0")) >= active_energy_cost()
    )
    if not can_pay_active:
        return False
    if resource_type not in {"food", "energy", "materials"}:
        return True
    return inventory.get(resource_type, Decimal("0")) >= requested_amount


def classify_aid_request_event(
    db: Session,
    *,
    request_event: Event,
    run_window: LiveRunWindow | None = None,
) -> dict[str, Any] | None:
    """Classify a request_aid or aid_request_received event into a lifecycle state."""
    requester, target = _request_parties(db, request_event)
    if requester is None or target is None:
        return None

    resource_type, requested_amount = _request_resource_and_amount(request_event)
    request_at = ensure_utc(request_event.created_at)
    request_message_id = _request_message_id(request_event)

    first_trade: Event | None = None
    first_refusal: Event | None = None
    first_reserve: Event | None = None
    first_direct_answer: Event | None = None
    first_unaffordable: Event | None = None

    for event in _trace_events_for_request(db, request_event=request_event, run_window=run_window):
        event_at = ensure_utc(event.created_at)
        if request_at is not None and event_at is not None and event_at < request_at:
            continue
        if first_trade is None and _event_is_trade_fulfillment(
            event,
            requester=requester,
            target=target,
            resource_type=resource_type,
        ):
            first_trade = event
        elif first_refusal is None and _response_refuses_request(
            event=event,
            requester=requester,
            target=target,
            request_message_id=request_message_id,
        ):
            first_refusal = event
        elif first_reserve is None and event.event_type == "reserve_aid" and int(event.agent_id or 0) == int(requester.id):
            first_reserve = event
        elif first_direct_answer is None and _event_is_direct_answer(event, requester=requester, target=target):
            first_direct_answer = event
        elif first_unaffordable is None and event.event_type in {"became_dormant", "agent_died"} and int(
            event.agent_id or 0
        ) == int(target.id):
            first_unaffordable = event
        elif first_unaffordable is None and event.event_type == "reserve_shortfall" and int(event.agent_id or 0) == int(
            requester.id
        ):
            first_unaffordable = event

    first_response = sorted(
        [
            event
            for event in (
                first_trade,
                first_refusal,
                first_reserve,
                first_direct_answer,
                first_unaffordable,
            )
            if event is not None
        ],
        key=lambda event: (ensure_utc(event.created_at) or now_utc(), int(event.id or 0)),
    )
    response = first_response[0] if first_response else None

    if response is not None and response is first_trade:
        status = "fulfilled_by_trade"
    elif response is not None and response is first_refusal:
        status = "refused"
    elif response is not None and response is first_reserve:
        status = "reserve_covered"
    elif response is not None and response is first_direct_answer:
        status = "answered_directly"
    elif response is not None and response is first_unaffordable:
        status = "mechanically_unaffordable"
    elif _request_is_stale_due_resource_change(
        db,
        request_event=request_event,
        requester=requester,
        resource_type=resource_type,
        requested_amount=requested_amount,
    ):
        status = "stale_resource_changed"
    else:
        status = "unresolved"

    return {
        "request_event_id": int(request_event.id),
        "request_at": request_at.isoformat() if request_at else None,
        "requester": agent_label(requester),
        "target": agent_label(target),
        "resource_type": resource_type,
        "amount": str(requested_amount.normalize()) if requested_amount else "",
        "reason": _request_reason(request_event),
        "status": status,
        "response_event_id": int(response.id) if response else None,
        "response_event_type": str(response.event_type) if response else None,
        "response_at": ensure_utc(response.created_at).isoformat() if response and response.created_at else None,
        "request_description": request_event.description,
        "response_description": response.description if response else None,
    }
