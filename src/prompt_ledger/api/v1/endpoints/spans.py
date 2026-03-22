"""Span ingestion and trace retrieval endpoints — Story 1.7, Epic 5."""

import base64
import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.api.dependencies import verify_api_key
from prompt_ledger.api.v1.schemas import SpanRequest
from prompt_ledger.db.database import get_db
from prompt_ledger.models.span import Span
from prompt_ledger.services.pricing import PricingTable

spans_router = APIRouter()
traces_router = APIRouter()

_pricing_table = PricingTable.default()


# ---------------------------------------------------------------------------
# Helper functions (pure Python — tested independently)
# ---------------------------------------------------------------------------


def _span_to_dict(span: Span) -> Dict[str, Any]:
    return {
        "span_id": str(span.span_id),
        "parent_span_id": str(span.parent_span_id) if span.parent_span_id else None,
        "trace_id": span.trace_id,
        "name": span.name,
        "kind": span.kind,
        "agent_id": span.agent_id,
        "prompt_name": span.prompt_name,
        "status": span.status,
        "start_time": span.start_time.isoformat() if span.start_time else None,
        "end_time": span.end_time.isoformat() if span.end_time else None,
        "duration_ms": span.duration_ms,
        "model": span.model,
        "prompt_tokens": span.prompt_tokens,
        "completion_tokens": span.completion_tokens,
        "attributes": span.attributes,
        "tool_name": span.tool_name,
        "success": span.success,
        "tool_args": span.tool_args,
        "tool_result": span.tool_result,
        "children": [],
    }


def _build_trace_tree(spans: List[Any]) -> List[Dict[str, Any]]:
    """Assemble a flat span list into a parent/child tree.

    Orphaned children (parent not in list) are attached to the root level.
    """
    nodes: Dict[str, Dict[str, Any]] = {}
    for span in spans:
        nodes[str(span.span_id)] = _span_to_dict(span)

    roots: List[Dict[str, Any]] = []
    for span in spans:
        node = nodes[str(span.span_id)]
        parent_id = str(span.parent_span_id) if span.parent_span_id else None
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots


def _build_trace_summary(
    trace_id: str, spans: List[Any], pricing: PricingTable
) -> Dict[str, Any]:
    """Compute aggregated cost and token summary for a trace."""
    total_prompt = 0
    total_completion = 0
    total_cost: Optional[float] = 0.0
    cost_breakdown = []
    agent_buckets: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"span_count": 0, "total_cost": 0.0, "total_prompt_tokens": 0}
    )

    start_times = []
    end_times = []

    for span in spans:
        pt = span.prompt_tokens or 0
        ct = span.completion_tokens or 0
        total_prompt += pt
        total_completion += ct

        if span.start_time:
            start_times.append(span.start_time)

        cost = _pricing_table.calculate_cost(span.model, pt, ct)
        provider = _pricing_table.infer_provider(span.model)

        if cost is None and span.model:
            total_cost = None  # unknown model — can't give reliable total
        elif total_cost is not None and cost is not None:
            total_cost += cost

        cost_breakdown.append(
            {
                "span_name": span.name,
                "agent_id": span.agent_id,
                "cost": cost,
                "provider": provider,
            }
        )

        if span.agent_id:
            bucket = agent_buckets[span.agent_id]
            bucket["span_count"] += 1
            bucket["total_prompt_tokens"] += pt
            if cost is not None and bucket["total_cost"] is not None:
                bucket["total_cost"] = (bucket["total_cost"] or 0) + cost
            else:
                bucket["total_cost"] = None

    duration_ms = None
    if start_times:
        earliest = min(start_times, key=lambda t: t.isoformat())
        # duration computed from span durations sum as approximation
        duration_ms = sum(s.duration_ms or 0 for s in spans) or None

    by_agent = [
        {"agent_id": agent_id, **stats} for agent_id, stats in agent_buckets.items()
    ]

    return {
        "trace_id": trace_id,
        "span_count": len(spans),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_cost": total_cost,
        "cost_breakdown": cost_breakdown,
        "by_agent": by_agent,
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Cursor helpers for GET /v1/traces pagination
# ---------------------------------------------------------------------------


def _encode_cursor(trace_start: datetime, trace_id: str) -> str:
    """Encode (trace_start, trace_id) into a URL-safe base64 cursor string."""
    data = {"ts": trace_start.isoformat(), "tid": trace_id}
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def _decode_cursor(cursor_str: str):
    """Decode a cursor string into (trace_start, trace_id).

    Raises HTTP 422 if the cursor is malformed.
    """
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor_str.encode()))
        ts = datetime.fromisoformat(data["ts"])
        tid: str = data["tid"]
        return ts, tid
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid cursor value")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@spans_router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any]
)
async def ingest_span(
    payload: SpanRequest,
    db: AsyncSession = Depends(get_db),
    project_id: UUID = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Ingest one span from a client (Mode 2 observability).

    Accepts an OpenTelemetry-style span payload and writes it to the spans
    table. Returns the assigned span_id.

    When kind == "tool", the tool_name field is required. Non-tool spans
    that include tool_name are rejected with a 422.
    """
    parent_uuid: Optional[UUID] = None
    if payload.parent_span_id:
        try:
            parent_uuid = UUID(str(payload.parent_span_id))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400, detail="parent_span_id must be a valid UUID"
            )

    span = Span(
        trace_id=payload.trace_id,
        parent_span_id=parent_uuid,
        name=payload.name,
        kind=payload.kind,
        agent_id=payload.agent_id,
        prompt_name=payload.prompt_name,
        status=payload.status,
        duration_ms=payload.duration_ms,
        error_message=payload.error_message,
        model=payload.model,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        input_data=payload.input_data,
        output_data=payload.output_data,
        attributes=payload.attributes,
        tool_name=payload.tool_name,
        success=payload.success,
        tool_args=payload.tool_args,
        tool_result=payload.tool_result,
        project_id=project_id,
    )

    db.add(span)
    await db.commit()
    await db.refresh(span)

    return {"span_id": str(span.span_id)}


@traces_router.get("", response_model=Dict[str, Any])
async def list_traces(
    agent_id: Optional[str] = None,
    status: Optional[Literal["ok", "error"]] = None,
    prompt_name: Optional[str] = None,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    page_size: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    project_id: UUID = Depends(verify_api_key),
) -> Dict[str, Any]:
    """List traces with optional filtering and cursor-based pagination.

    Returns trace-level summaries (aggregate of all spans per trace_id).
    Supports filtering by agent_id, status, prompt_name, and time range.
    Results are ordered by trace start time ascending.
    """
    # --- span-level conditions (applied before grouping) ---
    span_conds = [Span.project_id == project_id]

    if agent_id:
        agent_tids = (
            select(Span.trace_id)
            .where(Span.project_id == project_id, Span.agent_id == agent_id)
            .distinct()
            .scalar_subquery()
        )
        span_conds.append(Span.trace_id.in_(agent_tids))

    if prompt_name:
        prompt_tids = (
            select(Span.trace_id)
            .where(Span.project_id == project_id, Span.prompt_name == prompt_name)
            .distinct()
            .scalar_subquery()
        )
        span_conds.append(Span.trace_id.in_(prompt_tids))

    # --- aggregation subquery ---
    has_error_expr = func.max(case((Span.status == "error", 1), else_=0))
    trace_start_expr = func.min(Span.start_time)

    agg_subq = (
        select(
            Span.trace_id,
            trace_start_expr.label("trace_start"),
            func.count(Span.span_id).label("span_count"),
            func.coalesce(func.sum(Span.prompt_tokens), 0).label("total_prompt_tokens"),
            func.coalesce(func.sum(Span.completion_tokens), 0).label(
                "total_completion_tokens"
            ),
            has_error_expr.label("has_error"),
        )
        .where(and_(*span_conds))
        .group_by(Span.trace_id)
        .subquery()
    )

    # --- outer query with post-aggregation filters ---
    outer_q = select(agg_subq)

    if status == "error":
        outer_q = outer_q.where(agg_subq.c.has_error == 1)
    elif status == "ok":
        outer_q = outer_q.where(agg_subq.c.has_error == 0)

    if from_:
        outer_q = outer_q.where(agg_subq.c.trace_start >= from_)
    if to:
        outer_q = outer_q.where(agg_subq.c.trace_start <= to)

    # --- cursor-based pagination ---
    if cursor:
        cursor_ts, cursor_tid = _decode_cursor(cursor)
        outer_q = outer_q.where(
            or_(
                agg_subq.c.trace_start > cursor_ts,
                and_(
                    agg_subq.c.trace_start == cursor_ts,
                    agg_subq.c.trace_id > cursor_tid,
                ),
            )
        )

    # Fetch one extra row to detect whether there is a next page
    outer_q = outer_q.order_by(agg_subq.c.trace_start, agg_subq.c.trace_id).limit(
        page_size + 1
    )

    result = await db.execute(outer_q)
    rows = result.fetchall()

    has_next = len(rows) > page_size
    rows = rows[:page_size]

    next_cursor: Optional[str] = None
    if has_next and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last.trace_start, last.trace_id)

    traces = [
        {
            "trace_id": row.trace_id,
            "status": "error" if row.has_error else "ok",
            "span_count": row.span_count,
            "total_prompt_tokens": row.total_prompt_tokens,
            "total_completion_tokens": row.total_completion_tokens,
            "total_cost": None,
            "start_time": row.trace_start.isoformat() if row.trace_start else None,
        }
        for row in rows
    ]

    return {"traces": traces, "next_cursor": next_cursor}


@traces_router.get("/{trace_id}", response_model=Dict[str, Any])
async def get_trace(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
    project_id: UUID = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Retrieve all spans for a trace as a parent/child tree."""
    result = await db.execute(
        select(Span)
        .where(Span.trace_id == trace_id, Span.project_id == project_id)
        .order_by(Span.start_time)
    )
    spans = result.scalars().all()

    if not spans:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    tree = _build_trace_tree(spans)
    start = min(s.start_time for s in spans if s.start_time)
    end = max((s.end_time for s in spans if s.end_time), default=None)

    return {
        "trace_id": trace_id,
        "span_count": len(spans),
        "start_time": start.isoformat() if start else None,
        "end_time": end.isoformat() if end else None,
        "duration_ms": sum(s.duration_ms or 0 for s in spans) or None,
        "spans": tree,
    }


@traces_router.get("/{trace_id}/summary", response_model=Dict[str, Any])
async def get_trace_summary(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
    project_id: UUID = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Aggregated cost and token summary for a trace, broken down by agent."""
    result = await db.execute(
        select(Span)
        .where(Span.trace_id == trace_id, Span.project_id == project_id)
        .order_by(Span.start_time)
    )
    spans = result.scalars().all()

    if not spans:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    return _build_trace_summary(trace_id, spans, _pricing_table)
