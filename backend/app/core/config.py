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
    
    # Security
    SECRET_KEY: str = "development-secret-key-change-in-production"
    
    # CORS
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Simulation settings
    AGENT_LOOP_DELAY_SECONDS: int = 150  # 2.5 minutes
    DAY_LENGTH_MINUTES: int = 60  # 1 real hour = 1 sim day
    PROPOSAL_VOTING_HOURS: int = 24
    
    # Rate limiting
    MAX_ACTIONS_PER_HOUR: int = 20
    MAX_PROPOSALS_PER_DAY: int = 3
    
    # Resource defaults
    STARTING_FOOD: int = 10
    STARTING_ENERGY: int = 10
    STARTING_MATERIALS: int = 5
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
