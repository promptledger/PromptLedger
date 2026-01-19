"""Execution models for tracking prompt runs."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..db.database import Base


class Execution(Base):
    """Execution tracking model."""
    
    __tablename__ = "executions"
    
    execution_id = Column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    
    # Foreign keys
    prompt_id = Column(
        PostgresUUID(as_uuid=True), ForeignKey("prompts.prompt_id"), nullable=False
    )
    version_id = Column(
        PostgresUUID(as_uuid=True), ForeignKey("prompt_versions.version_id"), nullable=False
    )
    model_id = Column(
        PostgresUUID(as_uuid=True), ForeignKey("models.model_id"), nullable=False
    )
    
    # Environment and mode
    environment = Column(String(50), nullable=False, default="dev")
    execution_mode = Column(String(10), nullable=False)  # sync, async
    status = Column(String(20), nullable=False, default="queued")  # queued, running, succeeded, failed, canceled
    
    # Tracking
    correlation_id = Column(String(100))
    idempotency_key = Column(String(100))
    
    # Content
    rendered_prompt = Column(Text, nullable=False)
    response_text = Column(Text)
    
    # Parameters
    temperature = Column(DOUBLE_PRECISION)
    top_k = Column(Integer)
    top_p = Column(DOUBLE_PRECISION)
    repetition_penalty = Column(DOUBLE_PRECISION)
    max_new_tokens = Column(Integer)
    
    # Telemetry
    prompt_tokens = Column(Integer)
    response_tokens = Column(Integer)
    latency_ms = Column(Integer)
    error_type = Column(String(100))
    error_message = Column(Text)
    
    # Timestamps
    created_at = Column(
        func.now(), nullable=False, default=datetime.utcnow
    )
    started_at = Column(func.now())
    completed_at = Column(func.now())
    
    # Relationships
    prompt = relationship("Prompt", back_populates="executions")
    version = relationship("PromptVersion", back_populates="executions")
    model = relationship("Model")
    execution_input = relationship("ExecutionInput", back_populates="execution", uselist=False)
    
    # Indexes
    __table_args__ = (
        Index("idx_exec_prompt_time", "prompt_id", "created_at.desc()"),
        Index("idx_exec_version_time", "version_id", "created_at.desc()"),
        Index("idx_exec_status_time", "status", "created_at.desc()"),
        Index("idx_exec_corr", "correlation_id"),
        UniqueConstraint(
            "prompt_id", "idempotency_key", 
            name="uq_exec_idempotency",
            postgresql_where=Column("idempotency_key").isnot(None)
        ),
    )


class ExecutionInput(Base):
    """Execution input variables."""
    
    __tablename__ = "execution_inputs"
    
    execution_id = Column(
        PostgresUUID(as_uuid=True), 
        ForeignKey("executions.execution_id"), 
        primary_key=True
    )
    variables_json = Column(JSONB, nullable=False)
    
    # Relationships
    execution = relationship("Execution", back_populates="execution_input")
