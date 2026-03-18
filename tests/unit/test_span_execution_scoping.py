"""Unit tests for project-scoped Span and Execution queries — Story 2.3."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.project import Project
from prompt_ledger.models.span import Span


@pytest.fixture
async def two_projects(db_session: AsyncSession):
    """Create two projects and return their IDs."""
    proj_a = Project(name="project-a")
    proj_b = Project(name="project-b")
    db_session.add_all([proj_a, proj_b])
    await db_session.flush()
    return proj_a.project_id, proj_b.project_id


class TestSpanProjectScoping:
    async def test_span_has_project_id_column(
        self, db_session: AsyncSession, two_projects
    ):
        """Span model must have a project_id column."""
        proj_a_id, _ = two_projects

        span = Span(
            trace_id="trace-001",
            name="test-span",
            kind="llm.generation",
            project_id=proj_a_id,
        )
        db_session.add(span)
        await db_session.flush()

        result = await db_session.execute(
            select(Span).where(Span.span_id == span.span_id)
        )
        saved = result.scalar_one()
        assert saved.project_id == proj_a_id

    async def test_same_trace_id_allowed_in_different_projects(
        self, db_session: AsyncSession, two_projects
    ):
        """Same trace_id can exist in two projects without collision."""
        proj_a_id, proj_b_id = two_projects
        trace_id = "shared-trace-xyz"

        span_a = Span(
            trace_id=trace_id,
            name="span-a",
            kind="llm.generation",
            project_id=proj_a_id,
        )
        span_b = Span(
            trace_id=trace_id,
            name="span-b",
            kind="llm.generation",
            project_id=proj_b_id,
        )
        db_session.add_all([span_a, span_b])
        await db_session.flush()

        result = await db_session.execute(
            select(Span).where(Span.trace_id == trace_id, Span.project_id == proj_a_id)
        )
        proj_a_spans = result.scalars().all()
        assert len(proj_a_spans) == 1
        assert proj_a_spans[0].name == "span-a"

    async def test_get_trace_scoped_by_project(
        self, db_session: AsyncSession, two_projects
    ):
        """Querying a trace by project_id only returns spans for that project."""
        proj_a_id, proj_b_id = two_projects
        trace_id = "exclusive-trace"

        # Only project A has this trace
        span = Span(
            trace_id=trace_id,
            name="only-in-a",
            kind="llm.generation",
            project_id=proj_a_id,
        )
        db_session.add(span)
        await db_session.flush()

        # Project A finds it
        result_a = await db_session.execute(
            select(Span).where(Span.trace_id == trace_id, Span.project_id == proj_a_id)
        )
        assert len(result_a.scalars().all()) == 1

        # Project B sees nothing
        result_b = await db_session.execute(
            select(Span).where(Span.trace_id == trace_id, Span.project_id == proj_b_id)
        )
        assert len(result_b.scalars().all()) == 0

    async def test_agent_analytics_scoped_by_project(
        self, db_session: AsyncSession, two_projects
    ):
        """Agent analytics query returns only spans for the given project."""
        proj_a_id, proj_b_id = two_projects

        # Project A has an agent with 2 spans
        for i in range(2):
            db_session.add(
                Span(
                    trace_id=f"trace-a-{i}",
                    name=f"span-{i}",
                    kind="llm.generation",
                    agent_id="agent-alpha",
                    project_id=proj_a_id,
                    prompt_tokens=10,
                    completion_tokens=5,
                )
            )
        # Project B has the same agent_id with 5 spans
        for i in range(5):
            db_session.add(
                Span(
                    trace_id=f"trace-b-{i}",
                    name=f"span-b-{i}",
                    kind="llm.generation",
                    agent_id="agent-alpha",
                    project_id=proj_b_id,
                    prompt_tokens=10,
                    completion_tokens=5,
                )
            )
        await db_session.flush()

        from sqlalchemy import func

        result = await db_session.execute(
            select(
                Span.agent_id,
                func.count(Span.span_id).label("total_spans"),
            )
            .where(Span.agent_id.isnot(None), Span.project_id == proj_a_id)
            .group_by(Span.agent_id)
        )
        rows = result.all()
        assert len(rows) == 1
        assert rows[0].total_spans == 2
