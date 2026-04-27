"""
Application configuration using Pydantic BaseSettings.
All settings are loaded from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration for the distributed chat system."""

    # --- Application ---
    APP_NAME: str = "DistributedChat"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # --- JWT ---
    JWT_SECRET_KEY: str = "jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://chatuser:chatpass@postgres:5432/chatdb"

    # Database pool settings
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Rate Limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60
    WS_RATE_LIMIT_PER_MINUTE: int = 30

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Presence ---
    PRESENCE_TIMEOUT_SECONDS: int = 60
    HEARTBEAT_INTERVAL_SECONDS: int = 30
    PING_TIMEOUT_SECONDS: int = 10

    # --- Backpressure ---
    MAX_SEND_QUEUE_SIZE: int = 100

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — avoids re-reading env on every call."""
    return Settings()
