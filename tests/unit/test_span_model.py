"""Unit tests for Span model - TDD approach for FR-001."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from prompt_ledger.models.execution import Execution
from prompt_ledger.models.model import Model
from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum
from prompt_ledger.models.span import Span


class TestSpanTableSchema:
    """Test Span table schema and structure."""

    @pytest.mark.asyncio
    async def test_span_table_exists(self, db_session: AsyncSession):
        """Test that spans table exists in database."""

        def get_tables(sync_conn):
            inspector = inspect(sync_conn)
            return inspector.get_table_names()

        conn = await db_session.connection()
        tables = await conn.run_sync(get_tables)
        assert "spans" in tables, "spans table should exist"

    @pytest.mark.asyncio
    async def test_span_table_has_required_columns(self, db_session: AsyncSession):
        """Test that spans table has all required columns."""

        def get_columns(sync_conn):
            inspector = inspect(sync_conn)
            return {col["name"] for col in inspector.get_columns("spans")}

        conn = await db_session.connection()
        columns = await conn.run_sync(get_columns)

        required_columns = {
            "span_id",
            "trace_id",
            "parent_span_id",
            "name",
            "kind",
            "start_time",
            "end_time",
            "duration_ms",
            "status",
            "error_message",
            "input_data",
            "output_data",
            "attributes",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "execution_id",
        }

        assert required_columns.issubset(
            columns
        ), f"Missing columns: {required_columns - columns}"

    @pytest.mark.asyncio
    async def test_span_table_has_indexes(self, db_session: AsyncSession):
        """Test that spans table has proper indexes for performance."""

        def get_indexes(sync_conn):
            inspector = inspect(sync_conn)
            return {idx["name"] for idx in inspector.get_indexes("spans")}

        conn = await db_session.connection()
        indexes = await conn.run_sync(get_indexes)

        # Should have index on trace_id for fast trace queries
        assert any(
            "trace_id" in idx_name.lower() for idx_name in indexes
        ), "Should have index on trace_id"


class TestSpanModelCreation:
    """Test creating Span model instances."""

    @pytest.mark.asyncio
    async def test_create_minimal_span(self, db_session: AsyncSession):
        """Test creating a span with minimal required fields."""
        span = Span(
            trace_id="trace-abc123", name="test_operation", kind="llm.generation"
        )

        db_session.add(span)
        await db_session.commit()

        assert span.span_id is not None
        assert span.trace_id == "trace-abc123"
        assert span.name == "test_operation"
        assert span.kind == "llm.generation"
        assert span.status == "ok"  # Default value

    @pytest.mark.asyncio
    async def test_create_llm_span_with_tokens(self, db_session: AsyncSession):
        """Test creating an LLM span with token counts."""
        span = Span(
            trace_id="trace-123",
            name="generate_response",
            kind="llm.generation",
            model="gpt-4o",
            prompt_tokens=150,
            completion_tokens=80,
            duration_ms=450,
        )

        db_session.add(span)
        await db_session.commit()

        assert span.model == "gpt-4o"
        assert span.prompt_tokens == 150
        assert span.completion_tokens == 80
        assert span.duration_ms == 450

    @pytest.mark.asyncio
    async def test_create_tool_span(self, db_session: AsyncSession):
        """Test creating a tool call span."""
        span = Span(
            trace_id="trace-456",
            name="web_search",
            kind="tool.search",
            input_data={"query": "Albert Einstein", "max_results": 3},
            output_data={"results": [{"title": "Einstein", "snippet": "..."}]},
            duration_ms=230,
            attributes={"search_engine": "wikipedia", "api_version": "2.0"},
        )

        db_session.add(span)
        await db_session.commit()

        assert span.kind == "tool.search"
        assert span.input_data["query"] == "Albert Einstein"
        assert span.output_data["results"][0]["title"] == "Einstein"
        assert span.attributes["search_engine"] == "wikipedia"

    @pytest.mark.asyncio
    async def test_create_failed_span(self, db_session: AsyncSession):
        """Test creating a span with error status."""
        span = Span(
            trace_id="trace-789",
            name="failed_operation",
            kind="llm.generation",
            status="error",
            error_message="OpenAI API rate limit exceeded",
        )

        db_session.add(span)
        await db_session.commit()

        assert span.status == "error"
        assert span.error_message == "OpenAI API rate limit exceeded"


class TestSpanParentChildRelationship:
    """Test self-referential parent-child relationships between spans."""

    @pytest.mark.asyncio
    async def test_parent_child_relationship(self, db_session: AsyncSession):
        """Test that parent-child relationship works correctly."""
        parent = Span(trace_id="trace-1", name="parent_span", kind="llm.generation")
        db_session.add(parent)
        await db_session.flush()

        child = Span(
            trace_id="trace-1",
            name="child_span",
            kind="llm.guardrail",
            parent_span_id=parent.span_id,
        )
        db_session.add(child)
        await db_session.commit()

        # Reload with eager loading of relationships
        result = await db_session.execute(
            select(Span)
            .options(selectinload(Span.parent_span), selectinload(Span.child_spans))
            .where(Span.span_id == parent.span_id)
        )
        parent_reloaded = result.scalar_one()

        result = await db_session.execute(
            select(Span)
            .options(selectinload(Span.parent_span))
            .where(Span.span_id == child.span_id)
        )
        child_reloaded = result.scalar_one()

        assert child_reloaded.parent_span_id == parent.span_id
        assert child_reloaded.parent_span == parent_reloaded
        assert child_reloaded in parent_reloaded.child_spans

    @pytest.mark.asyncio
    async def test_linear_chain_three_spans(self, db_session: AsyncSession):
        """Test linear chain: A → B → C."""
        span_a = Span(trace_id="trace-chain", name="A", kind="llm")
        db_session.add(span_a)
        await db_session.flush()

        span_b = Span(
            trace_id="trace-chain", name="B", kind="tool", parent_span_id=span_a.span_id
        )
        db_session.add(span_b)
        await db_session.flush()

        span_c = Span(
            trace_id="trace-chain", name="C", kind="llm", parent_span_id=span_b.span_id
        )
        db_session.add(span_c)
        await db_session.commit()

        # Reload with eager loading
        result = await db_session.execute(
            select(Span)
            .options(selectinload(Span.child_spans))
            .where(Span.span_id == span_a.span_id)
        )
        span_a_reloaded = result.scalar_one()

        result = await db_session.execute(
            select(Span)
            .options(selectinload(Span.child_spans), selectinload(Span.parent_span))
            .where(Span.span_id == span_b.span_id)
        )
        span_b_reloaded = result.scalar_one()

        result = await db_session.execute(
            select(Span)
            .options(selectinload(Span.parent_span))
            .where(Span.span_id == span_c.span_id)
        )
        span_c_reloaded = result.scalar_one()

        # Verify chain
        assert len(span_a_reloaded.child_spans) == 1
        assert span_a_reloaded.child_spans[0].name == "B"
        assert len(span_b_reloaded.child_spans) == 1
        assert span_b_reloaded.child_spans[0].name == "C"
        assert span_c_reloaded.parent_span.name == "B"

    @pytest.mark.asyncio
    async def test_parallel_fanout(self, db_session: AsyncSession):
        """Test parallel pattern: A → [B, C, D]."""
        span_a = Span(trace_id="trace-parallel", name="A", kind="llm")
        db_session.add(span_a)
        await db_session.flush()

        span_b = Span(
            trace_id="trace-parallel",
            name="B",
            kind="tool",
            parent_span_id=span_a.span_id,
        )
        span_c = Span(
            trace_id="trace-parallel",
            name="C",
            kind="tool",
            parent_span_id=span_a.span_id,
        )
        span_d = Span(
            trace_id="trace-parallel",
            name="D",
            kind="tool",
            parent_span_id=span_a.span_id,
        )

        db_session.add_all([span_b, span_c, span_d])
        await db_session.commit()

        # Reload with eager loading
        result = await db_session.execute(
            select(Span)
            .options(selectinload(Span.child_spans))
            .where(Span.span_id == span_a.span_id)
        )
        span_a_reloaded = result.scalar_one()

        assert len(span_a_reloaded.child_spans) == 3
        child_names = {child.name for child in span_a_reloaded.child_spans}
        assert child_names == {"B", "C", "D"}

    @pytest.mark.asyncio
    async def test_multiple_traces_isolated(self, db_session: AsyncSession):
        """Test that spans from different traces are properly isolated."""
        # Trace 1
        trace1_span = Span(trace_id="trace-1", name="Span1", kind="llm")

        # Trace 2
        trace2_span = Span(trace_id="trace-2", name="Span2", kind="llm")

        db_session.add_all([trace1_span, trace2_span])
        await db_session.commit()

        # Query spans by trace_id
        result = await db_session.execute(
            select(Span).where(Span.trace_id == "trace-1")
        )
        trace1_spans = result.scalars().all()

        assert len(trace1_spans) == 1
        assert trace1_spans[0].name == "Span1"


class TestSpanExecutionLinking:
    """Test linking between Span and Execution models."""

    @pytest.mark.asyncio
    async def test_span_without_execution(self, db_session: AsyncSession):
        """Test creating a span not linked to any execution (e.g., tool call)."""
        span = Span(
            trace_id="trace-123",
            name="external_tool_call",
            kind="tool.api",
            execution_id=None,
        )

        db_session.add(span)
        await db_session.commit()

        assert span.execution_id is None
        assert span.execution is None

    @pytest.mark.asyncio
    async def test_span_linked_to_execution(self, db_session: AsyncSession):
        """Test creating a span linked to a PromptLedger execution."""
        # Create necessary related objects
        prompt = Prompt(name=f"test_prompt_{uuid4()}", description="Test", mode="full")
        db_session.add(prompt)
        await db_session.flush()

        template = "Test template"
        version = PromptVersion(
            prompt_id=prompt.prompt_id,
            version_number=1,
            template_source=template,
            checksum_hash=compute_checksum(template),
            status="active",
        )
        db_session.add(version)
        await db_session.flush()

        model = Model(
            provider="openai",
            model_name="gpt-4o-mini",
            max_tokens=128000,
            supports_streaming=True,
        )
        db_session.add(model)
        await db_session.flush()

        # Create execution
        execution = Execution(
            prompt_id=prompt.prompt_id,
            version_id=version.version_id,
            model_id=model.model_id,
            execution_mode="sync",
            status="succeeded",
            rendered_prompt="Test prompt",
        )
        db_session.add(execution)
        await db_session.flush()

        # Create linked span
        span = Span(
            trace_id="trace-exec",
            name="prompt_execution",
            kind="llm.generation",
            execution_id=execution.execution_id,
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
        )
        db_session.add(span)
        await db_session.commit()

        # Reload with eager loading
        result = await db_session.execute(
            select(Execution)
            .options(selectinload(Execution.span))
            .where(Execution.execution_id == execution.execution_id)
        )
        execution_reloaded = result.scalar_one()

        result = await db_session.execute(
            select(Span)
            .options(selectinload(Span.execution))
            .where(Span.span_id == span.span_id)
        )
        span_reloaded = result.scalar_one()

        # Verify bidirectional relationship
        assert span_reloaded.execution_id == execution.execution_id
        assert span_reloaded.execution.execution_id == execution_reloaded.execution_id
        assert execution_reloaded.span.span_id == span_reloaded.span_id

    @pytest.mark.asyncio
    async def test_execution_can_have_at_most_one_span(self, db_session: AsyncSession):
        """Test that an execution can have at most one linked span (1:1 relationship)."""
        # Create execution
        prompt = Prompt(name=f"test_{uuid4()}", mode="full")
        db_session.add(prompt)
        await db_session.flush()

        version = PromptVersion(
            prompt_id=prompt.prompt_id,
            version_number=1,
            template_source="Test",
            checksum_hash=compute_checksum("Test"),
            status="active",
        )
        db_session.add(version)
        await db_session.flush()

        model = Model(provider="openai", model_name="gpt-4o", max_tokens=128000)
        db_session.add(model)
        await db_session.flush()

        execution = Execution(
            prompt_id=prompt.prompt_id,
            version_id=version.version_id,
            model_id=model.model_id,
            execution_mode="sync",
            status="succeeded",
            rendered_prompt="Test",
        )
        db_session.add(execution)
        await db_session.flush()

        # Create first span
        span1 = Span(
            trace_id="trace-1",
            name="span1",
            kind="llm",
            execution_id=execution.execution_id,
        )
        db_session.add(span1)
        await db_session.commit()

        # Reload with eager loading
        result = await db_session.execute(
            select(Execution)
            .options(selectinload(Execution.span))
            .where(Execution.execution_id == execution.execution_id)
        )
        execution_reloaded = result.scalar_one()

        # Verify single span relationship
        assert execution_reloaded.span.name == "span1"


class TestSpanKindValues:
    """Test valid span kind values based on OpenTelemetry conventions."""

    @pytest.mark.asyncio
    async def test_llm_generation_kind(self, db_session: AsyncSession):
        """Test LLM generation span kind."""
        span = Span(trace_id="t1", name="generate", kind="llm.generation")
        db_session.add(span)
        await db_session.commit()
        assert span.kind == "llm.generation"

    @pytest.mark.asyncio
    async def test_llm_guardrail_kind(self, db_session: AsyncSession):
        """Test LLM guardrail span kind."""
        span = Span(trace_id="t1", name="check", kind="llm.guardrail")
        db_session.add(span)
        await db_session.commit()
        assert span.kind == "llm.guardrail"

    @pytest.mark.asyncio
    async def test_llm_embedding_kind(self, db_session: AsyncSession):
        """Test LLM embedding span kind."""
        span = Span(trace_id="t1", name="embed", kind="llm.embedding")
        db_session.add(span)
        await db_session.commit()
        assert span.kind == "llm.embedding"

    @pytest.mark.asyncio
    async def test_tool_kind(self, db_session: AsyncSession):
        """Test tool span kind."""
        span = Span(trace_id="t1", name="search", kind="tool.search")
        db_session.add(span)
        await db_session.commit()
        assert span.kind == "tool.search"

    @pytest.mark.asyncio
    async def test_db_query_kind(self, db_session: AsyncSession):
        """Test database query span kind."""
        span = Span(trace_id="t1", name="vector_search", kind="db.query")
        db_session.add(span)
        await db_session.commit()
        assert span.kind == "db.query"

    @pytest.mark.asyncio
    async def test_agent_reasoning_kind(self, db_session: AsyncSession):
        """Test agent reasoning span kind."""
        span = Span(trace_id="t1", name="plan_action", kind="agent.reasoning")
        db_session.add(span)
        await db_session.commit()
        assert span.kind == "agent.reasoning"
