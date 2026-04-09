"""Shared survival-cost and threshold helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.core.config import settings
from app.services.runtime_config import runtime_config_service


def _runtime_decimal(key: str, default: float, *, minimum: str) -> Decimal:
    raw_value = runtime_config_service.get_effective_value_cached(key)
    try:
        value = Decimal(str(raw_value if raw_value not in (None, "") else default))
    except (ArithmeticError, InvalidOperation, ValueError):
        value = Decimal(str(default))
    return max(Decimal(minimum), value)


def _runtime_int(key: str, default: int, *, minimum: int) -> int:
    raw_value = runtime_config_service.get_effective_value_cached(key)
    try:
        return max(minimum, int(raw_value if raw_value not in (None, "") else default))
    except (TypeError, ValueError):
        return max(minimum, int(default))


def active_food_cost() -> Decimal:
    return _runtime_decimal(
        "SURVIVAL_ACTIVE_FOOD_COST",
        settings.SURVIVAL_ACTIVE_FOOD_COST,
        minimum="0.01",
    )


def active_energy_cost() -> Decimal:
    return _runtime_decimal(
        "SURVIVAL_ACTIVE_ENERGY_COST",
        settings.SURVIVAL_ACTIVE_ENERGY_COST,
        minimum="0.01",
    )


def dormant_food_cost() -> Decimal:
    return _runtime_decimal(
        "SURVIVAL_DORMANT_FOOD_COST",
        settings.SURVIVAL_DORMANT_FOOD_COST,
        minimum="0.00",
    )


def dormant_energy_cost() -> Decimal:
    return _runtime_decimal(
        "SURVIVAL_DORMANT_ENERGY_COST",
        settings.SURVIVAL_DORMANT_ENERGY_COST,
        minimum="0.00",
    )


def death_threshold() -> int:
    return _runtime_int(
        "SURVIVAL_DEATH_THRESHOLD",
        settings.SURVIVAL_DEATH_THRESHOLD,
        minimum=1,
    )


def low_resource_warning_threshold(cost: Decimal) -> Decimal:
    return max(cost, cost * Decimal("2"))
