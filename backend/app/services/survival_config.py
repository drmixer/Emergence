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


def _runtime_bool(key: str, default: bool) -> bool:
    raw_value = runtime_config_service.get_effective_value_cached(key)
    if raw_value in (None, ""):
        return bool(default)
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(raw_value, (int, float)):
        if raw_value in (0, 1):
            return bool(raw_value)
    return bool(default)


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


def reserve_auto_revive_enabled() -> bool:
    return _runtime_bool(
        "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED",
        settings.SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED,
    )


def reserve_active_aid_enabled() -> bool:
    return _runtime_bool(
        "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED",
        settings.SURVIVAL_RESERVE_ACTIVE_AID_ENABLED,
    )


def reserve_dormant_maintenance_enabled() -> bool:
    return _runtime_bool(
        "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED",
        settings.SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED,
    )


def reserve_auto_contribution_enabled() -> bool:
    return _runtime_bool(
        "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED",
        settings.SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED,
    )


def low_resource_warning_threshold(cost: Decimal | int | float | str) -> Decimal:
    normalized = Decimal(str(cost))
    return max(normalized, normalized * Decimal("2"))
