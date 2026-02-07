"""Runtime stop-condition guardrails for worker safety."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.core.time import now_utc
from app.models.models import Event
from app.services.runtime_config import runtime_config_service
from app.services.usage_budget import usage_budget

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StopDecision:
    should_stop: bool
    reason: str | None = None
    details: dict[str, Any] | None = None


class RunGuardrailService:
    """
    Evaluate and enforce runtime stop conditions.

    Stop conditions:
    - hard budget breach
    - repeated provider failures in recent window
    - sustained DB pool exhaustion pressure
    """

    def __init__(self) -> None:
        self._db_pressure_streak = 0

    def evaluate(self) -> StopDecision:
        if not bool(
            runtime_config_service.get_effective_value_cached(
                "STOP_CONDITION_ENFORCEMENT_ENABLED"
            )
        ):
            self._db_pressure_streak = 0
            return StopDecision(False)

        if bool(runtime_config_service.get_effective_value_cached("SIMULATION_PAUSED")):
            return StopDecision(False)
        if not bool(
            runtime_config_service.get_effective_value_cached("SIMULATION_ACTIVE")
        ):
            return StopDecision(False)

        budget_decision = self._check_budget_hard_stop()
        if budget_decision.should_stop:
            return budget_decision

        provider_decision = self._check_provider_failures()
        if provider_decision.should_stop:
            return provider_decision

        db_pool_decision = self._check_db_pool_pressure()
        if db_pool_decision.should_stop:
            return db_pool_decision

        return StopDecision(False)

    def evaluate_and_enforce(self) -> StopDecision:
        decision = self.evaluate()
        if decision.should_stop:
            self._enforce_stop(decision)
        return decision

    @staticmethod
    def _check_budget_hard_stop() -> StopDecision:
        hard_budget = float(
            runtime_config_service.get_effective_value_cached(
                "LLM_DAILY_BUDGET_USD_HARD"
            )
            or 0.0
        )
        if hard_budget <= 0:
            return StopDecision(False)

        snapshot = usage_budget.get_snapshot()
        if float(snapshot.estimated_cost_usd) > hard_budget:
            details = {
                "day_key": snapshot.day_key.isoformat(),
                "estimated_cost_usd": float(snapshot.estimated_cost_usd),
                "hard_budget_usd": hard_budget,
            }
            return StopDecision(True, "hard_budget_exceeded", details)
        return StopDecision(False)

    @staticmethod
    def _check_provider_failures() -> StopDecision:
        threshold = int(
            runtime_config_service.get_effective_value_cached(
                "STOP_PROVIDER_FAILURE_THRESHOLD"
            )
            or 0
        )
        window_minutes = int(
            runtime_config_service.get_effective_value_cached(
                "STOP_PROVIDER_FAILURE_WINDOW_MINUTES"
            )
            or 0
        )
        if threshold <= 0 or window_minutes <= 0:
            return StopDecision(False)

        since_ts = now_utc() - timedelta(minutes=window_minutes)
        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_count,
                        COALESCE(SUM(CASE WHEN success THEN 0 ELSE 1 END), 0) AS failure_count
                    FROM llm_usage
                    WHERE created_at >= :since_ts
                    """
                ),
                {"since_ts": since_ts},
            ).first()
        except Exception as exc:
            logger.warning("Provider-failure stop check unavailable: %s", exc)
            return StopDecision(False)
        finally:
            db.close()

        successes = int((row.success_count if row else 0) or 0)
        failures = int((row.failure_count if row else 0) or 0)
        if failures < threshold:
            return StopDecision(False)

        total = successes + failures
        failure_rate = (failures / total) if total > 0 else 1.0
        details = {
            "window_minutes": window_minutes,
            "failure_threshold": threshold,
            "failures": failures,
            "successes": successes,
            "failure_rate": round(failure_rate, 4),
        }
        return StopDecision(True, "provider_failures_repeated", details)

    def _check_db_pool_pressure(self) -> StopDecision:
        threshold = float(
            runtime_config_service.get_effective_value_cached(
                "STOP_DB_POOL_UTILIZATION_THRESHOLD"
            )
            or 0.0
        )
        required_checks = int(
            runtime_config_service.get_effective_value_cached(
                "STOP_DB_POOL_CONSECUTIVE_CHECKS"
            )
            or 0
        )
        if threshold <= 0 or required_checks <= 0:
            self._db_pressure_streak = 0
            return StopDecision(False)

        pool = getattr(engine, "pool", None)
        if pool is None or not hasattr(pool, "checkedout") or not hasattr(pool, "size"):
            self._db_pressure_streak = 0
            return StopDecision(False)

        checked_out = max(0, int(pool.checkedout()))
        base_size = max(1, int(pool.size()))
        max_overflow = int(getattr(pool, "_max_overflow", 0))
        if max_overflow < 0:
            capacity = max(base_size, checked_out)
        else:
            capacity = max(1, base_size + max_overflow)
        utilization = checked_out / capacity

        if utilization >= threshold:
            self._db_pressure_streak += 1
        else:
            self._db_pressure_streak = 0
            return StopDecision(False)

        if self._db_pressure_streak < required_checks:
            return StopDecision(False)

        details = {
            "checked_out": checked_out,
            "capacity": capacity,
            "utilization": round(utilization, 4),
            "utilization_threshold": threshold,
            "consecutive_checks_required": required_checks,
            "consecutive_checks_observed": self._db_pressure_streak,
        }
        return StopDecision(True, "db_pool_pressure", details)

    @staticmethod
    def _enforce_stop(decision: StopDecision) -> None:
        reason = decision.reason or "unknown_stop_condition"
        reason_text = f"Stop condition tripped: {reason}"
        metadata = {
            "reason": reason,
            "details": decision.details or {},
            "triggered_at": now_utc().isoformat(),
        }

        db = SessionLocal()
        try:
            try:
                runtime_config_service.update_settings(
                    db,
                    {
                        "SIMULATION_ACTIVE": False,
                        "SIMULATION_PAUSED": True,
                    },
                    changed_by="system:guardrail",
                    reason=reason_text,
                )
            except Exception as exc:
                db.rollback()
                logger.error(
                    "Failed to persist runtime stop overrides for guardrail: %s", exc
                )

            db.add(
                Event(
                    event_type="simulation_stopped_guardrail",
                    description=reason_text,
                    event_metadata=metadata,
                )
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Failed to persist guardrail stop event: %s", exc)
        finally:
            db.close()

        logger.error(
            "Simulation stop condition triggered (%s): %s",
            reason,
            decision.details or {},
        )


run_guardrail_service = RunGuardrailService()
