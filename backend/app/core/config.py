"""
Core configuration for Emergence.
Uses Pydantic Settings for environment variable management.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pydantic import model_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_empty_env_values(cls, data):
        if not isinstance(data, dict):
            return data
        # Railway (and other platforms) sometimes inject empty-string env vars.
        # Treat them as "unset" so typed fields (bool/int/float) don't crash on startup.
        return {key: value for key, value in data.items() if value != ""}
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "info"
    
    # Database
    DATABASE_URL: str = "postgresql://localhost:5432/emergence"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    # Optional Redis key prefix for usage/budget counters.
    # If empty, usage_budget falls back to RAILWAY_PROJECT_NAME for isolation.
    USAGE_BUDGET_KEY_PREFIX: str = ""
    
    # LLM APIs
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"
    MISTRAL_SMALL_MODEL: str = "mistral-small-latest"
    # LLM routing
    # - "auto": use model mapping if known, otherwise prefer OpenRouter, then Mistral, then Groq
    # - "openrouter": force OpenRouter for all unknown models
    # - "groq": force Groq for all unknown models
    # - "mistral": force direct Mistral for all unknown models
    LLM_PROVIDER: str = "auto"
    # When forcing Groq (or falling back), pick one of: llama-3.3-70b | llama-3.1-8b
    GROQ_DEFAULT_MODEL: str = "llama-3.1-8b"
    # If Groq is selected, optionally allow falling back to OpenRouter on rate limits/errors.
    # Keep this off in dev if you want "Groq-only" and to avoid OpenRouter charges.
    ALLOW_OPENROUTER_FALLBACK: bool = False
    # Optional: send a small % of lightweight agents through Groq even when OpenRouter is available.
    # Deterministic per-agent (based on agent id). Suggested: 0.05–0.10.
    # Legacy knob for old model_type routing; keep 0.0 with pinned cohort assignments.
    GROQ_LIGHTWEIGHT_SHARE: float = 0.0

    # Provider concurrency caps to reduce rate limiting (esp. Groq free tier).
    GROQ_MAX_CONCURRENCY: int = 2
    OPENROUTER_MAX_CONCURRENCY: int = 6
    MISTRAL_MAX_CONCURRENCY: int = 4
    OPENROUTER_RPM_LIMIT: int = 6
    # Action-generation output controls (checkpoint decisions).
    LLM_ACTION_MAX_TOKENS: int = 350
    LLM_ACTION_PARSE_RETRY_ATTEMPTS: int = 2

    # Daily LLM budget and throughput guardrails.
    # Soft cap: degrade model route / max_tokens.
    # Hard cap: stop paid/extra calls and return controlled fallback.
    LLM_DAILY_BUDGET_USD_SOFT: float = 0.50
    LLM_DAILY_BUDGET_USD_HARD: float = 1.00
    LLM_MAX_CALLS_PER_DAY_TOTAL: int = 2200
    LLM_MAX_CALLS_PER_DAY_OPENROUTER_FREE: int = 900
    LLM_MAX_CALLS_PER_DAY_GROQ: int = 1800

    # Memory compaction knobs (used by upcoming memory subsystem).
    LLM_MEMORY_UPDATE_EVERY_N_CHECKPOINTS: int = 3
    LLM_MEMORY_MAX_CHARS: int = 1200
    
    # Security
    SECRET_KEY: str = "development-secret-key-change-in-production"

    # Internal admin/ops dashboard controls.
    # Keep ADMIN_WRITE_ENABLED=false in production until explicitly enabled.
    ADMIN_ENABLED: bool = False
    ADMIN_WRITE_ENABLED: bool = False
    ADMIN_API_TOKEN: str = ""
    # Optional comma-separated IP allowlist for admin requests.
    # Example: "127.0.0.1,10.0.0.5"
    ADMIN_IP_ALLOWLIST: str = ""
    
    # CORS
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Simulation settings
    AGENT_LOOP_DELAY_SECONDS: int = 150  # 2.5 minutes
    DAY_LENGTH_MINUTES: int = 60  # 1 real hour = 1 sim day
    # Can be fractional in dev for faster end-to-end testing (e.g. 0.25 = 15 minutes).
    PROPOSAL_VOTING_HOURS: float = 24.0
    SIMULATION_MAX_AGENTS: int = 50  # Default v1 runtime cap; set 0 to process all seeded agents
    # Runtime ops controls (can be overridden via internal admin APIs).
    SIMULATION_RUN_MODE: str = "test"  # test | real
    SIMULATION_ACTIVE: bool = True
    SIMULATION_PAUSED: bool = False
    FORCE_CHEAPEST_ROUTE: bool = False
    # Optional run label for llm_usage attribution rows. If empty, runtime generates one.
    SIMULATION_RUN_ID: str = ""
    # Optional perception lag for agent context (in seconds). Adds information asymmetry.
    PERCEPTION_LAG_SECONDS: int = 120

    # LLM-generated narration (summaries/story/highlights). These call OpenRouter by default and may cost money.
    SUMMARIES_ENABLED: bool = False
    SUMMARY_LLM_MODEL: str = "openrouter/anthropic/claude-3-haiku"
    
    # Rate limiting
    MAX_ACTIONS_PER_HOUR: int = 20
    MAX_PROPOSALS_PER_DAY: int = 3
    
    # Resource defaults
    STARTING_FOOD: int = 50
    STARTING_ENERGY: int = 50
    STARTING_MATERIALS: int = 20
    
    # NOTE: legacy inner Config is intentionally not used; SettingsConfigDict above is Pydantic v2.


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
