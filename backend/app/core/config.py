"""
Core configuration for Emergence.
Uses Pydantic Settings for environment variable management.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
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
    
    # Security
    SECRET_KEY: str = "development-secret-key-change-in-production"
    
    # CORS
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Simulation settings
    AGENT_LOOP_DELAY_SECONDS: int = 150  # 2.5 minutes
    DAY_LENGTH_MINUTES: int = 60  # 1 real hour = 1 sim day
    PROPOSAL_VOTING_HOURS: int = 24
    SIMULATION_MAX_AGENTS: int = 0  # 0 = all agents (use 1-3 for cheap local tests)
    
    # Rate limiting
    MAX_ACTIONS_PER_HOUR: int = 20
    MAX_PROPOSALS_PER_DAY: int = 3
    
    # Resource defaults
    STARTING_FOOD: int = 50
    STARTING_ENERGY: int = 50
    STARTING_MATERIALS: int = 20
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
