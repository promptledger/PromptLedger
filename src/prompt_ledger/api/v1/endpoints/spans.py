"""Span ingestion and trace retrieval endpoints — Story 1.7."""

from collections import defaultdict
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
# Endpoints
# ---------------------------------------------------------------------------


@spans_router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any]
)
async def ingest_span(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Ingest one span from a client (Mode 2 observability).

    Accepts an OpenTelemetry-style span payload and writes it to the spans
    table. Returns the assigned span_id.
    """
    trace_id = payload.get("trace_id")
    if not trace_id:
        raise HTTPException(status_code=400, detail="trace_id is required")

    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    kind = payload.get("kind", "llm.generation")

    parent_span_id = payload.get("parent_span_id")
    parent_uuid: Optional[UUID] = None
    if parent_span_id:
        try:
            parent_uuid = UUID(str(parent_span_id))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400, detail="parent_span_id must be a valid UUID"
            )

    span = Span(
        trace_id=trace_id,
        parent_span_id=parent_uuid,
        name=name,
        kind=kind,
        agent_id=payload.get("agent_id"),
        prompt_name=payload.get("prompt_name"),
        status=payload.get("status", "ok"),
        duration_ms=payload.get("duration_ms"),
        model=payload.get("model"),
        prompt_tokens=payload.get("prompt_tokens"),
        completion_tokens=payload.get("completion_tokens"),
        input_data=payload.get("input_data"),
        output_data=payload.get("output_data"),
        attributes=payload.get("attributes"),
    )

    db.add(span)
    await db.commit()
    await db.refresh(span)

    return {"span_id": str(span.span_id)}


@traces_router.get("/{trace_id}", response_model=Dict[str, Any])
async def get_trace(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve all spans for a trace as a parent/child tree."""
    result = await db.execute(
        select(Span).where(Span.trace_id == trace_id).order_by(Span.start_time)
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
) -> Dict[str, Any]:
    """Aggregated cost and token summary for a trace, broken down by agent."""
    result = await db.execute(
        select(Span).where(Span.trace_id == trace_id).order_by(Span.start_time)
    )
    spans = result.scalars().all()

    if not spans:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    return _build_trace_summary(trace_id, spans, _pricing_table)
