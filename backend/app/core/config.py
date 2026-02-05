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
    
    # LLM APIs
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    # LLM routing
    # - "auto": use model mapping if known, otherwise prefer OpenRouter if configured, else Groq
    # - "openrouter": force OpenRouter for all unknown models
    # - "groq": force Groq for all unknown models
    LLM_PROVIDER: str = "auto"
    # When forcing Groq (or falling back), pick one of: llama-3.3-70b | llama-3.1-8b
    GROQ_DEFAULT_MODEL: str = "llama-3.1-8b"
    # If Groq is selected, optionally allow falling back to OpenRouter on rate limits/errors.
    # Keep this off in dev if you want "Groq-only" and to avoid OpenRouter charges.
    ALLOW_OPENROUTER_FALLBACK: bool = False
    # Optional: send a small % of lightweight agents through Groq even when OpenRouter is available.
    # Deterministic per-agent (based on agent id). Suggested: 0.05–0.10.
    GROQ_LIGHTWEIGHT_SHARE: float = 0.0

    # Provider concurrency caps to reduce rate limiting (esp. Groq free tier).
    GROQ_MAX_CONCURRENCY: int = 2
    OPENROUTER_MAX_CONCURRENCY: int = 6
    
    # Security
    SECRET_KEY: str = "development-secret-key-change-in-production"
    
    # CORS
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Simulation settings
    AGENT_LOOP_DELAY_SECONDS: int = 150  # 2.5 minutes
    DAY_LENGTH_MINUTES: int = 60  # 1 real hour = 1 sim day
    # Can be fractional in dev for faster end-to-end testing (e.g. 0.25 = 15 minutes).
    PROPOSAL_VOTING_HOURS: float = 24.0
    SIMULATION_MAX_AGENTS: int = 0  # 0 = all agents (use 1-3 for cheap local tests)

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
