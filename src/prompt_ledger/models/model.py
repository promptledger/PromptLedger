"""Model definition for AI providers."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.sql import func

from prompt_ledger.db.database import Base


class Model(Base):
    """AI model configuration."""

    __tablename__ = "models"

    model_id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider = Column(String(50), nullable=False)  # openai, anthropic, etc.
    model_name = Column(String(100), nullable=False)
    max_tokens = Column(Integer)
    supports_streaming = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("provider", "model_name", name="uq_provider_model"),
    )
