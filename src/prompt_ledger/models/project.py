"""Project and ApiKey models for multi-tenant namespacing — Story 2.1."""

import hashlib
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from prompt_ledger.db.database import Base


class Project(Base):
    """A named tenant. All prompts, spans, and executions belong to a project."""

    __tablename__ = "projects"

    project_id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(Text, nullable=False, unique=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    api_keys = relationship(
        "ApiKey", back_populates="project", cascade="all, delete-orphan"
    )


class ApiKey(Base):
    """A hashed API key scoped to a project.

    The plaintext key is never stored — only its SHA-256 hash. The plaintext
    is returned exactly once at creation and then discarded.
    """

    __tablename__ = "api_keys"

    key_id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    key_hash = Column(Text, nullable=False, unique=True)
    project_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("projects.project_id"),
        nullable=False,
    )
    label = Column(Text, nullable=True)
    is_system_key = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project = relationship("Project", back_populates="api_keys")


def hash_api_key(plaintext: str) -> str:
    """Compute SHA-256 hash of a plaintext API key. Never store the plaintext."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
