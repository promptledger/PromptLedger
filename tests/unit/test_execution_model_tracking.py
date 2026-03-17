"""Unit tests for Story 1.8 — Execution Telemetry Enhancement.

TDD: these tests are written BEFORE the implementation exists.
They must fail (RED) before any implementation is written.

These tests are pure-Python and require no Docker/database.
"""

import pytest
from sqlalchemy import inspect

from prompt_ledger.models.execution import Execution


class TestExecutionOrmModelNameColumn:
    """Execution ORM model has a model_name column (Story 1.8 schema change)."""

    def test_execution_has_model_name_attribute(self):
        """Execution ORM class has a model_name attribute."""
        assert hasattr(Execution, "model_name")

    def test_model_name_is_mapped_column(self):
        """model_name is a mapped SQLAlchemy column on the executions table."""
        mapper = inspect(Execution)
        column_names = [col.key for col in mapper.mapper.column_attrs]
        assert "model_name" in column_names

    def test_model_name_column_is_nullable(self):
        """model_name column must be nullable (no backfill for existing rows)."""
        mapper = inspect(Execution)
        col = mapper.mapper.columns["model_name"]
        assert col.nullable is True

    def test_model_name_column_is_string(self):
        """model_name column is a String type."""
        from sqlalchemy import String

        mapper = inspect(Execution)
        col = mapper.mapper.columns["model_name"]
        assert isinstance(col.type, String)
