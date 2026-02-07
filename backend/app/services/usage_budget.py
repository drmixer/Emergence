"""
Usage + budget tracking for LLM calls.

Stores per-call usage rows in Postgres and keeps fast daily counters in Redis.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import redis
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import now_utc
from app.services.runtime_config import runtime_config_service

logger = logging.getLogger(__name__)


@dataclass
class BudgetSnapshot:
    day_key: date
    calls_total: int
    calls_openrouter_free: int
    calls_groq: int
    estimated_cost_usd: float


@dataclass
class BudgetDecision:
    allowed: bool
    reason: str | None
    soft_cap_reached: bool
    snapshot: BudgetSnapshot


class UsageBudgetService:
    """Budget checks + usage recording with Redis counters and DB fallback."""

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._redis_checked = False

    def _get_redis(self) -> redis.Redis | None:
        if self._redis_checked and self._redis is None:
            return None
        if self._redis is not None:
            return self._redis
        try:
            self._redis = redis.Redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
            # Quick check so we fail fast and fall back to DB.
            self._redis.ping()
            self._redis_checked = True
            return self._redis
        except Exception as e:
            self._redis_checked = True
            logger.warning("Usage budget Redis unavailable; using DB fallback: %s", e)
            self._redis = None
            return None

    @staticmethod
    def _key_prefix() -> str:
        configured = str(getattr(settings, "USAGE_BUDGET_KEY_PREFIX", "") or "").strip()
        fallback = str(os.environ.get("RAILWAY_PROJECT_NAME", "") or "").strip()
        prefix = configured or fallback
        if not prefix:
            return ""
        normalized = re.sub(r"[^a-zA-Z0-9:_-]+", "-", prefix.lower()).strip("-")
        return f"{normalized}:" if normalized else ""

    @staticmethod
    def _counter_keys(day_key: date) -> dict[str, str]:
        day = day_key.isoformat()
        prefix = UsageBudgetService._key_prefix()
        return {
            "total": f"{prefix}llm:usage:{day}:calls_total",
            "openrouter_free": f"{prefix}llm:usage:{day}:calls_openrouter_free",
            "groq": f"{prefix}llm:usage:{day}:calls_groq",
            "cost": f"{prefix}llm:usage:{day}:estimated_cost_usd",
        }

    def _get_db_snapshot(self, day_key: date) -> BudgetSnapshot:
        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS calls_total,
                        COALESCE(SUM(CASE WHEN provider = 'openrouter' AND model_name LIKE '%:free' THEN 1 ELSE 0 END), 0) AS calls_openrouter_free,
                        COALESCE(SUM(CASE WHEN provider = 'groq' THEN 1 ELSE 0 END), 0) AS calls_groq,
                        COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                    FROM llm_usage
                    WHERE day_key = :day_key
                    """
                ),
                {"day_key": day_key},
            ).first()
            if not row:
                return BudgetSnapshot(day_key, 0, 0, 0, 0.0)
            return BudgetSnapshot(
                day_key=day_key,
                calls_total=int(row.calls_total or 0),
                calls_openrouter_free=int(row.calls_openrouter_free or 0),
                calls_groq=int(row.calls_groq or 0),
                estimated_cost_usd=float(row.estimated_cost_usd or 0.0),
            )
        except Exception:
            # On first deploy, table may not exist until migration runs.
            return BudgetSnapshot(day_key, 0, 0, 0, 0.0)
        finally:
            db.close()

    def _get_redis_snapshot(self, day_key: date) -> BudgetSnapshot | None:
        r = self._get_redis()
        if r is None:
            return None
        keys = self._counter_keys(day_key)
        try:
            values = r.mget(
                [keys["total"], keys["openrouter_free"], keys["groq"], keys["cost"]]
            )
            if not values or any(v is None for v in values):
                return None
            return BudgetSnapshot(
                day_key=day_key,
                calls_total=int(values[0] or 0),
                calls_openrouter_free=int(values[1] or 0),
                calls_groq=int(values[2] or 0),
                estimated_cost_usd=float(values[3] or 0.0),
            )
        except Exception:
            return None

    def _seed_redis_snapshot(self, snapshot: BudgetSnapshot) -> None:
        r = self._get_redis()
        if r is None:
            return
        keys = self._counter_keys(snapshot.day_key)
        ttl_seconds = 60 * 60 * 72
        try:
            pipe = r.pipeline(transaction=False)
            pipe.setnx(keys["total"], snapshot.calls_total)
            pipe.setnx(keys["openrouter_free"], snapshot.calls_openrouter_free)
            pipe.setnx(keys["groq"], snapshot.calls_groq)
            pipe.setnx(keys["cost"], snapshot.estimated_cost_usd)
            pipe.expire(keys["total"], ttl_seconds)
            pipe.expire(keys["openrouter_free"], ttl_seconds)
            pipe.expire(keys["groq"], ttl_seconds)
            pipe.expire(keys["cost"], ttl_seconds)
            pipe.execute()
        except Exception:
            return

    def get_snapshot(self) -> BudgetSnapshot:
        day_key = now_utc().date()
        redis_snapshot = self._get_redis_snapshot(day_key)
        if redis_snapshot is not None:
            return redis_snapshot
        db_snapshot = self._get_db_snapshot(day_key)
        self._seed_redis_snapshot(db_snapshot)
        return db_snapshot

    def preflight(self, provider: str, model_name: str) -> BudgetDecision:
        snapshot = self.get_snapshot()

        hard_budget = float(runtime_config_service.get_effective_value_cached("LLM_DAILY_BUDGET_USD_HARD") or 0.0)
        max_total = int(runtime_config_service.get_effective_value_cached("LLM_MAX_CALLS_PER_DAY_TOTAL") or 0)
        max_or_free = int(
            runtime_config_service.get_effective_value_cached("LLM_MAX_CALLS_PER_DAY_OPENROUTER_FREE") or 0
        )
        max_groq = int(runtime_config_service.get_effective_value_cached("LLM_MAX_CALLS_PER_DAY_GROQ") or 0)

        if hard_budget > 0 and snapshot.estimated_cost_usd >= hard_budget:
            return BudgetDecision(False, "hard_budget_reached", False, snapshot)
        if max_total > 0 and snapshot.calls_total >= max_total:
            return BudgetDecision(False, "max_calls_total_reached", False, snapshot)
        if provider == "openrouter" and model_name.endswith(":free") and max_or_free > 0:
            if snapshot.calls_openrouter_free >= max_or_free:
                return BudgetDecision(False, "max_calls_openrouter_free_reached", False, snapshot)
        if provider == "groq" and max_groq > 0:
            if snapshot.calls_groq >= max_groq:
                return BudgetDecision(False, "max_calls_groq_reached", False, snapshot)

        soft_budget = float(runtime_config_service.get_effective_value_cached("LLM_DAILY_BUDGET_USD_SOFT") or 0.0)
        soft_cap_reached = False
        if soft_budget > 0 and snapshot.estimated_cost_usd >= soft_budget:
            soft_cap_reached = True
        if max_total > 0 and snapshot.calls_total >= int(max_total * 0.85):
            soft_cap_reached = True
        if provider == "openrouter" and model_name.endswith(":free") and max_or_free > 0:
            if snapshot.calls_openrouter_free >= int(max_or_free * 0.85):
                soft_cap_reached = True
        if provider == "groq" and max_groq > 0:
            if snapshot.calls_groq >= int(max_groq * 0.85):
                soft_cap_reached = True

        return BudgetDecision(True, None, soft_cap_reached, snapshot)

    @staticmethod
    def estimate_cost_usd(
        provider: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> float:
        # Most current routes in this project are free-tier.
        if provider == "groq":
            return 0.0
        if provider == "openrouter" and model_name.endswith(":free"):
            return 0.0

        # Conservative fallback estimate for non-free models.
        # Input: $0.50 / 1M tokens, Output: $1.50 / 1M tokens
        in_rate_per_million = Decimal("0.50")
        out_rate_per_million = Decimal("1.50")

        if prompt_tokens > 0 or completion_tokens > 0:
            estimated = (
                (Decimal(prompt_tokens) / Decimal(1_000_000)) * in_rate_per_million
                + (Decimal(completion_tokens) / Decimal(1_000_000)) * out_rate_per_million
            )
        else:
            estimated = (Decimal(total_tokens) / Decimal(1_000_000)) * Decimal("1.00")
        return float(max(Decimal("0"), estimated))

    def record_call(
        self,
        run_id: str | None,
        agent_id: int | None,
        checkpoint_number: int | None,
        provider: str,
        model_name: str,
        model_type: str | None,
        resolved_model_name: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        success: bool,
        fallback_used: bool,
        byok_used: bool | None = None,
        latency_ms: int | None = None,
        error_type: str | None = None,
    ) -> None:
        day_key = now_utc().date()
        estimated_cost = self.estimate_cost_usd(
            provider=provider,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        db = SessionLocal()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO llm_usage (
                        day_key, run_id, agent_id, checkpoint_number,
                        provider, model_type, model_name, resolved_model_name,
                        prompt_tokens, completion_tokens, total_tokens,
                        estimated_cost_usd, success, fallback_used, byok_used, latency_ms, error_type
                    ) VALUES (
                        :day_key, :run_id, :agent_id, :checkpoint_number,
                        :provider, :model_type, :model_name, :resolved_model_name,
                        :prompt_tokens, :completion_tokens, :total_tokens,
                        :estimated_cost_usd, :success, :fallback_used, :byok_used, :latency_ms, :error_type
                    )
                    """
                ),
                {
                    "day_key": day_key,
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "checkpoint_number": checkpoint_number,
                    "provider": provider,
                    "model_type": model_type,
                    "model_name": model_name,
                    "resolved_model_name": (resolved_model_name or model_name),
                    "prompt_tokens": max(0, int(prompt_tokens or 0)),
                    "completion_tokens": max(0, int(completion_tokens or 0)),
                    "total_tokens": max(0, int(total_tokens or 0)),
                    "estimated_cost_usd": estimated_cost,
                    "success": bool(success),
                    "fallback_used": bool(fallback_used),
                    "byok_used": byok_used,
                    "latency_ms": (None if latency_ms is None else max(0, int(latency_ms))),
                    "error_type": error_type,
                },
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Failed to persist llm_usage row: %s", e)
            return
        finally:
            db.close()

        r = self._get_redis()
        if r is None:
            return

        keys = self._counter_keys(day_key)
        ttl_seconds = 60 * 60 * 72
        try:
            pipe = r.pipeline(transaction=False)
            pipe.incr(keys["total"], 1)
            if provider == "openrouter" and model_name.endswith(":free"):
                pipe.incr(keys["openrouter_free"], 1)
            if provider == "groq":
                pipe.incr(keys["groq"], 1)
            pipe.incrbyfloat(keys["cost"], estimated_cost)
            pipe.expire(keys["total"], ttl_seconds)
            pipe.expire(keys["openrouter_free"], ttl_seconds)
            pipe.expire(keys["groq"], ttl_seconds)
            pipe.expire(keys["cost"], ttl_seconds)
            pipe.execute()
        except Exception:
            return


usage_budget = UsageBudgetService()
