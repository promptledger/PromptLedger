"""Tests for context.py — trace ID and parent span ID propagation via contextvars.

Key property under test: contextvars are task-local in asyncio. A value set in
task A must NOT be visible in a sibling task B that was created without inheriting
task A's context.
"""

import asyncio

import pytest
from promptledger_client.context import (
    current_parent_span_id,
    current_trace_id,
    set_parent_span_id,
    start_trace,
)

# ---------------------------------------------------------------------------
# start_trace / current_trace_id
# ---------------------------------------------------------------------------


def test_start_trace_returns_non_empty_string():
    async def inner():
        return start_trace()

    result = asyncio.run(inner())
    assert isinstance(result, str)
    assert len(result) > 0


def test_start_trace_sets_current_trace_id():
    async def inner():
        trace_id = start_trace()
        return trace_id, current_trace_id()

    trace_id, current = asyncio.run(inner())
    assert trace_id == current


def test_each_start_trace_call_produces_unique_id():
    async def inner():
        id1 = start_trace()
        id2 = start_trace()
        return id1, id2

    id1, id2 = asyncio.run(inner())
    assert id1 != id2


def test_current_trace_id_returns_none_in_fresh_context():
    """A brand-new asyncio.run() has no inherited trace_id."""

    async def inner():
        return current_trace_id()

    result = asyncio.run(inner())
    assert result is None


async def test_trace_id_does_not_leak_into_sibling_task():
    """Task B created after task A sets a trace must NOT see task A's trace_id.

    asyncio.create_task() copies the *current* context at creation time.
    If task B is created before task A sets the contextvar, task B sees None.
    """

    result_holder = {}

    async def task_a():
        start_trace()
        await asyncio.sleep(0)
        result_holder["a"] = current_trace_id()

    async def task_b():
        # created before task_a mutates its context
        await asyncio.sleep(0)
        result_holder["b"] = current_trace_id()

    # Create task_b first (captures context before task_a sets anything)
    tb = asyncio.create_task(task_b())
    ta = asyncio.create_task(task_a())
    await asyncio.gather(ta, tb)

    assert result_holder["a"] is not None
    assert result_holder["b"] is None  # sibling never called start_trace


# ---------------------------------------------------------------------------
# parent_span_id
# ---------------------------------------------------------------------------


def test_current_parent_span_id_returns_none_in_fresh_context():
    async def inner():
        return current_parent_span_id()

    result = asyncio.run(inner())
    assert result is None


def test_set_and_get_parent_span_id():
    async def inner():
        set_parent_span_id("span-abc-123")
        return current_parent_span_id()

    result = asyncio.run(inner())
    assert result == "span-abc-123"


async def test_parent_span_id_does_not_leak_into_sibling_task():
    result_holder = {}

    async def task_a():
        set_parent_span_id("span-from-a")
        await asyncio.sleep(0)
        result_holder["a"] = current_parent_span_id()

    async def task_b():
        await asyncio.sleep(0)
        result_holder["b"] = current_parent_span_id()

    tb = asyncio.create_task(task_b())
    ta = asyncio.create_task(task_a())
    await asyncio.gather(ta, tb)

    assert result_holder["a"] == "span-from-a"
    assert result_holder["b"] is None
