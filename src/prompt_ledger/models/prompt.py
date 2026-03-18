"""Prompt and prompt version models."""

import hashlib
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    TEXT,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from prompt_ledger.db.database import Base


def compute_checksum(template_source: str) -> str:
    """Compute SHA-256 checksum of template source."""
    return hashlib.sha256(template_source.encode("utf-8")).hexdigest()


class Prompt(Base):
    """Prompt model."""

    __tablename__ = "prompts"

    prompt_id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("projects.project_id"),
        nullable=True,  # nullable until migration backfill; enforced NOT NULL in migration
    )
    name = Column(TEXT, nullable=False)
    description = Column(TEXT)
    owner_team = Column(TEXT)
    mode = Column(
        Enum("full", "tracking", name="prompt_mode"),
        nullable=False,
        server_default="full",
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    active_version_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey(
            "prompt_versions.version_id",
            use_alter=True,
            name="fk_prompt_active_version",
        ),
    )

    # Relationships
    versions = relationship(
        "PromptVersion",
        back_populates="prompt",
        cascade="all, delete-orphan",
        foreign_keys="PromptVersion.prompt_id",
    )
    executions = relationship("Execution", back_populates="prompt")

    # Active version relationship
    active_version = relationship(
        "PromptVersion", foreign_keys=[active_version_id], post_update=True
    )

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_prompt_name"),
        Index("idx_prompts_mode", "mode"),
        Index("idx_prompts_project_id", "project_id"),
    )


class PromptVersion(Base):
    """Prompt version model."""

    __tablename__ = "prompt_versions"

    version_id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    prompt_id = Column(
        PostgresUUID(as_uuid=True), ForeignKey("prompts.prompt_id"), nullable=False
    )
    version_number = Column(Integer, nullable=False)
    status = Column(
        Enum("draft", "active", "deprecated", name="prompt_version_status"),
        nullable=False,
        server_default="draft",
    )
    template_source = Column(TEXT, nullable=False)
    checksum_hash = Column(TEXT, nullable=False)
    created_by = Column(TEXT)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    prompt = relationship("Prompt", back_populates="versions", foreign_keys=[prompt_id])
    executions = relationship("Execution", back_populates="version")

    # Constraints
    __table_args__ = (
        UniqueConstraint("prompt_id", "version_number", name="uq_prompt_version"),
        UniqueConstraint("prompt_id", "checksum_hash", name="uq_prompt_checksum"),
    )
