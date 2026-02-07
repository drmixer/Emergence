"""Runtime config overrides and admin audit helpers."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import AdminConfigChange, RuntimeConfigOverride


@dataclass(frozen=True)
class MutableSettingSpec:
    python_type: type
    description: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: tuple[str, ...] | None = None


MUTABLE_SETTINGS: dict[str, MutableSettingSpec] = {
    "SIMULATION_RUN_MODE": MutableSettingSpec(
        python_type=str,
        allowed_values=("test", "real"),
        description="Simulation mode label used by ops and automation.",
    ),
    "SIMULATION_RUN_ID": MutableSettingSpec(
        python_type=str,
        description="Run label for metrics attribution (max 64 chars). Empty value uses auto-generated id.",
    ),
    "SIMULATION_ACTIVE": MutableSettingSpec(
        python_type=bool,
        description="Global run switch for worker loops (idle when false).",
    ),
    "SIMULATION_PAUSED": MutableSettingSpec(
        python_type=bool,
        description="Pauses simulation processing when true.",
    ),
    "FORCE_CHEAPEST_ROUTE": MutableSettingSpec(
        python_type=bool,
        description="Force low-cost model routing path.",
    ),
    "AGENT_LOOP_DELAY_SECONDS": MutableSettingSpec(
        python_type=int,
        min_value=60,
        max_value=900,
        description="Base delay between agent turns.",
    ),
    "OPENROUTER_RPM_LIMIT": MutableSettingSpec(
        python_type=int,
        min_value=1,
        max_value=120,
        description="OpenRouter requests-per-minute cap.",
    ),
    "LLM_ACTION_MAX_TOKENS": MutableSettingSpec(
        python_type=int,
        min_value=64,
        max_value=2048,
        description="Max completion tokens for strategic actions.",
    ),
    "LLM_ACTION_PARSE_RETRY_ATTEMPTS": MutableSettingSpec(
        python_type=int,
        min_value=0,
        max_value=5,
        description="Parser retry attempts on malformed action JSON.",
    ),
    "LLM_MEMORY_UPDATE_EVERY_N_CHECKPOINTS": MutableSettingSpec(
        python_type=int,
        min_value=1,
        max_value=24,
        description="Checkpoint cadence for memory compaction updates.",
    ),
    "LLM_MEMORY_MAX_CHARS": MutableSettingSpec(
        python_type=int,
        min_value=200,
        max_value=8000,
        description="Per-agent long-term memory char cap.",
    ),
    "LLM_DAILY_BUDGET_USD_SOFT": MutableSettingSpec(
        python_type=float,
        min_value=0,
        max_value=25,
        description="Soft spend cap; triggers degraded behavior.",
    ),
    "LLM_DAILY_BUDGET_USD_HARD": MutableSettingSpec(
        python_type=float,
        min_value=0,
        max_value=100,
        description="Hard spend cap; blocks extra paid LLM calls.",
    ),
    "LLM_MAX_CALLS_PER_DAY_TOTAL": MutableSettingSpec(
        python_type=int,
        min_value=1,
        max_value=50000,
        description="Global daily LLM call cap.",
    ),
    "LLM_MAX_CALLS_PER_DAY_OPENROUTER_FREE": MutableSettingSpec(
        python_type=int,
        min_value=0,
        max_value=50000,
        description="Daily cap for OpenRouter free-route calls.",
    ),
    "LLM_MAX_CALLS_PER_DAY_GROQ": MutableSettingSpec(
        python_type=int,
        min_value=0,
        max_value=50000,
        description="Daily cap for Groq-route calls.",
    ),
    "STOP_CONDITION_ENFORCEMENT_ENABLED": MutableSettingSpec(
        python_type=bool,
        description="Enable runtime stop conditions (budget/failures/DB pressure).",
    ),
    "STOP_PROVIDER_FAILURE_WINDOW_MINUTES": MutableSettingSpec(
        python_type=int,
        min_value=1,
        max_value=1440,
        description="Lookback window for repeated provider failure stop condition.",
    ),
    "STOP_PROVIDER_FAILURE_THRESHOLD": MutableSettingSpec(
        python_type=int,
        min_value=1,
        max_value=50000,
        description="Failed LLM calls in window required to stop the run.",
    ),
    "STOP_DB_POOL_UTILIZATION_THRESHOLD": MutableSettingSpec(
        python_type=float,
        min_value=0.5,
        max_value=1.0,
        description="QueuePool utilization threshold for DB pressure stop condition.",
    ),
    "STOP_DB_POOL_CONSECUTIVE_CHECKS": MutableSettingSpec(
        python_type=int,
        min_value=1,
        max_value=60,
        description="Consecutive high-pressure pool checks required before stopping run.",
    ),
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        if value in (0, 1):
            return bool(value)
    raise ValueError("expected boolean")


def _coerce_value(key: str, raw_value: Any, spec: MutableSettingSpec) -> Any:
    if spec.python_type is bool:
        value = _as_bool(raw_value)
    elif spec.python_type is int:
        if isinstance(raw_value, bool):
            raise ValueError("expected integer")
        value = int(raw_value)
    elif spec.python_type is float:
        if isinstance(raw_value, bool):
            raise ValueError("expected float")
        value = float(raw_value)
    elif spec.python_type is str:
        value = str(raw_value or "").strip()
    else:
        raise ValueError(f"unsupported type for {key}")

    if spec.allowed_values and str(value) not in spec.allowed_values:
        allowed = ", ".join(spec.allowed_values)
        raise ValueError(f"must be one of: {allowed}")

    if key == "SIMULATION_RUN_ID":
        text = str(value or "").strip()
        if len(text) > 64:
            raise ValueError("must be <= 64 characters")
        value = text

    if isinstance(value, (int, float)):
        if spec.min_value is not None and value < spec.min_value:
            raise ValueError(f"must be >= {spec.min_value}")
        if spec.max_value is not None and value > spec.max_value:
            raise ValueError(f"must be <= {spec.max_value}")

    return value


class RuntimeConfigService:
    """Read/write runtime overrides with validation + audit logs."""

    def __init__(self) -> None:
        self._cache_ttl_seconds = 5.0
        self._cache_expires_at = 0.0
        self._cached_effective: dict[str, Any] = {}

    def get_override_rows(self, db: Session) -> dict[str, RuntimeConfigOverride]:
        rows = db.query(RuntimeConfigOverride).all()
        return {row.key: row for row in rows}

    def get_overrides(self, db: Session) -> dict[str, Any]:
        rows = self.get_override_rows(db)
        return {key: row.value_json for key, row in rows.items()}

    def get_effective(self, db: Session) -> dict[str, Any]:
        overrides = self.get_overrides(db)
        effective: dict[str, Any] = {}
        for key in MUTABLE_SETTINGS:
            effective[key] = (
                overrides[key] if key in overrides else getattr(settings, key)
            )
        return effective

    def _refresh_cache(self) -> None:
        db = SessionLocal()
        try:
            self._cached_effective = self.get_effective(db)
            self._cache_expires_at = time.monotonic() + self._cache_ttl_seconds
        finally:
            db.close()

    def get_effective_value_cached(self, key: str) -> Any:
        if key not in MUTABLE_SETTINGS:
            return getattr(settings, key, None)
        now = time.monotonic()
        if now >= self._cache_expires_at or not self._cached_effective:
            try:
                self._refresh_cache()
            except Exception:
                # Fail open to static settings if runtime config table is unavailable.
                return getattr(settings, key, None)
        return self._cached_effective.get(key, getattr(settings, key))

    def get_config_payload(self, db: Session) -> dict[str, Any]:
        defaults = {key: getattr(settings, key) for key in MUTABLE_SETTINGS}
        overrides = self.get_overrides(db)
        effective = {key: overrides.get(key, defaults[key]) for key in MUTABLE_SETTINGS}
        mutable_keys = {
            key: {
                "type": spec.python_type.__name__,
                "description": spec.description,
                "min": spec.min_value,
                "max": spec.max_value,
                "allowed_values": (
                    list(spec.allowed_values) if spec.allowed_values else None
                ),
            }
            for key, spec in MUTABLE_SETTINGS.items()
        }
        return {
            "defaults": defaults,
            "overrides": overrides,
            "effective": effective,
            "mutable_keys": mutable_keys,
            "admin_write_enabled": bool(
                getattr(settings, "ADMIN_WRITE_ENABLED", False)
            ),
            "environment": getattr(settings, "ENVIRONMENT", "development"),
        }

    def update_settings(
        self,
        db: Session,
        updates: dict[str, Any],
        *,
        changed_by: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(updates, dict) or not updates:
            raise ValueError("`updates` must be a non-empty object")

        invalid_keys = sorted([key for key in updates if key not in MUTABLE_SETTINGS])
        if invalid_keys:
            raise ValueError(f"Unsupported config keys: {', '.join(invalid_keys)}")

        before = self.get_effective(db)
        override_rows = self.get_override_rows(db)

        validated_updates: dict[str, Any] = {}
        for key, raw_value in updates.items():
            spec = MUTABLE_SETTINGS[key]
            try:
                validated_updates[key] = _coerce_value(key, raw_value, spec)
            except Exception as exc:
                raise ValueError(f"Invalid value for `{key}`: {exc}") from exc

        after = dict(before)
        after.update(validated_updates)
        soft_cap = float(after.get("LLM_DAILY_BUDGET_USD_SOFT", 0) or 0)
        hard_cap = float(after.get("LLM_DAILY_BUDGET_USD_HARD", 0) or 0)
        if hard_cap > 0 and soft_cap > 0 and hard_cap < soft_cap:
            raise ValueError(
                "LLM_DAILY_BUDGET_USD_HARD must be >= LLM_DAILY_BUDGET_USD_SOFT"
            )

        applied: dict[str, Any] = {}
        for key, new_value in validated_updates.items():
            old_value = before.get(key)
            if old_value == new_value:
                continue

            row = override_rows.get(key)
            if row is None:
                row = RuntimeConfigOverride(
                    key=key,
                    value_json=new_value,
                    updated_by=changed_by,
                    reason=reason,
                )
                db.add(row)
            else:
                row.value_json = new_value
                row.updated_by = changed_by
                row.reason = reason

            db.add(
                AdminConfigChange(
                    key=key,
                    old_value=old_value,
                    new_value=new_value,
                    changed_by=changed_by,
                    environment=str(getattr(settings, "ENVIRONMENT", "development")),
                    reason=reason,
                )
            )
            applied[key] = new_value

        if applied:
            db.commit()
            after_update = dict(before)
            after_update.update(applied)
            self._cached_effective = after_update
            self._cache_expires_at = time.monotonic() + self._cache_ttl_seconds
        else:
            db.rollback()

        return {
            "applied": applied,
            "effective": self.get_effective(db),
        }

    @staticmethod
    def list_audit_entries(
        db: Session, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = (
            db.query(AdminConfigChange)
            .order_by(desc(AdminConfigChange.created_at), desc(AdminConfigChange.id))
            .offset(max(0, int(offset or 0)))
            .limit(max(1, min(int(limit or 50), 500)))
            .all()
        )
        return [
            {
                "id": int(row.id),
                "key": row.key,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "changed_by": row.changed_by,
                "environment": row.environment,
                "reason": row.reason,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]


runtime_config_service = RuntimeConfigService()
