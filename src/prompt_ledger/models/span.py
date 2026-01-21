"""Span model for workflow execution tracking - FR-001."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from prompt_ledger.db.database import Base


class Span(Base):
    """Observability span for tracking operations in agentic workflows.

    Spans represent individual operations within a trace:
    - PromptLedger executions (linked to Execution)
    - External LLM calls (no Execution link)
    - Tool calls (search, API, database)
    - Agent reasoning steps
    - Any other workflow operation

    Based on OpenTelemetry span model for industry compatibility.
    """

    __tablename__ = "spans"

    # Primary key
    span_id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Trace correlation
    trace_id = Column(String(100), nullable=False, index=True)
    parent_span_id = Column(
        PostgresUUID(as_uuid=True), ForeignKey("spans.span_id"), nullable=True
    )

    # Identity
    name = Column(String(100), nullable=False)
    kind = Column(String(50), nullable=False)  # "llm.generation", "tool.search", etc.

    # Timing
    start_time = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Status
    status = Column(String(20), nullable=False, default="ok")  # "ok", "error"
    error_message = Column(Text, nullable=True)

    # Flexible content (JSONB for arbitrary data)
    input_data = Column(JSONB, nullable=True)  # Input to this operation
    output_data = Column(JSONB, nullable=True)  # Output from this operation
    attributes = Column(JSONB, nullable=True)  # Arbitrary metadata

    # LLM-specific fields (only populated for LLM spans)
    model = Column(String(100), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    # Link to Execution (nullable - only for PromptLedger executions)
    execution_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("executions.execution_id"),
        nullable=True,
        unique=True,  # 1:1 relationship
    )

    # Relationships
    # Self-referential for parent-child tree
    parent_span = relationship(
        "Span",
        remote_side=[span_id],
        foreign_keys=[parent_span_id],
        backref="child_spans",
    )

    # Link to Execution (when this span represents a PromptLedger execution)
    execution = relationship("Execution", back_populates="span", uselist=False)

    # Indexes for query performance
    __table_args__ = (
        Index("idx_span_trace_id", "trace_id"),
        Index("idx_span_parent_id", "parent_span_id"),
        Index("idx_span_execution_id", "execution_id"),
        Index("idx_span_trace_start", "trace_id", "start_time"),
    )

    def __repr__(self) -> str:
        """String representation of Span."""
        return (
            f"<Span(span_id={self.span_id}, trace_id={self.trace_id}, "
            f"name={self.name}, kind={self.kind}, status={self.status})>"
        )
