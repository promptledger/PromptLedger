"""Application settings and configuration."""

from typing import Any, Dict, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = "Prompt Ledger"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/prompt_ledger",
        description="PostgreSQL database URL",
    )

    @validator("database_url", pre=True)
    def convert_database_url(cls, v: str) -> str:
        """Convert standard postgres URL to asyncpg format for async operations."""
        if v.startswith("postgres://"):
            # Handle Railway's postgres:// format
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and "+asyncpg" not in v:
            # Handle postgresql:// without driver specified
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis URL for Celery broker"
    )

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key")

    # Security
    api_key: str = Field(
        default="dev-key-change-in-production",
        description="Internal API key for authentication",
    )

    # CORS and Host Configuration
    cors_origins: list[str] = Field(
        default=["*"],
        description="Allowed CORS origins. Use ['*'] for development, specify domains for production",
    )
    allowed_hosts: list[str] = Field(
        default=["*"],
        description="Allowed hosts for TrustedHostMiddleware. Use ['*'] to allow all (recommended for Railway)",
    )

    # Celery
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    @validator("celery_broker_url", always=True)
    def set_celery_broker(cls, v: Optional[str], values: Dict[str, Any]) -> str:
        """Set Celery broker URL from Redis URL."""
        return v or values.get("redis_url", "")

    @validator("celery_result_backend", always=True)
    def set_celery_backend(cls, v: Optional[str], values: Dict[str, Any]) -> str:
        """Set Celery result backend from Redis URL."""
        return v or values.get("redis_url", "")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
