"""Analytics endpoints for unified reporting across modes."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.db.database import get_db
from prompt_ledger.models.execution import Execution
from prompt_ledger.models.model import Model
from prompt_ledger.models.prompt import Prompt
from prompt_ledger.services.pricing import PricingTable

router = APIRouter()

# Loaded once at module import.  Operators can override the path via
# the PRICING_YAML_PATH env var before the process starts.
_pricing_table = PricingTable.default()


def _compute_total_cost(model_token_rows: List) -> Optional[float]:
    """Compute total cost from SQL rows of (model_name, total_input, total_output).

    Returns 0.0  when there are no rows (no executions → zero cost incurred).
    Returns None when any model name is unrecognised (can't give a reliable total).
    Returns the summed cost when all models are known.
    """
    total = 0.0
    for row in model_token_rows:
        cost = _pricing_table.calculate_cost(
            row.model_name, row.total_input, row.total_output
        )
        if cost is None:
            return None
        total += cost
    return total


async def _cost_by_mode(
    db: AsyncSession, mode: Optional[str] = None
) -> Optional[float]:
    """Query token totals grouped by model name and compute total cost.

    Args:
        db:   Async DB session.
        mode: Prompt mode filter ('full' or 'tracking').  None = all modes.
    """
    query = (
        select(
            Model.model_name,
            func.sum(Execution.prompt_tokens).label("total_input"),
            func.sum(Execution.response_tokens).label("total_output"),
        )
        .join(Model, Model.model_id == Execution.model_id)
        .join(Prompt, Prompt.prompt_id == Execution.prompt_id)
        .group_by(Model.model_name)
    )
    if mode is not None:
        query = query.where(Prompt.mode == mode)

    result = await db.execute(query)
    rows = result.all()
    return _compute_total_cost(rows)


@router.get("/prompts", response_model=Dict[str, Any])
async def get_prompts_analytics(
    mode: str = Query("all", pattern="^(all|full|tracking)$"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get unified analytics across both prompt modes.

    This endpoint provides aggregated statistics for prompt executions,
    broken down by management mode (full vs tracking). It allows filtering
    by mode or retrieving combined statistics.

    Query parameters:
    - mode: Filter by mode ('all', 'full', or 'tracking'). Default: 'all'

    Response format:
    ```json
    {
        "summary": {
            "total_executions": 1250,
            "full_mode_prompts": 8,
            "tracking_mode_prompts": 12
        },
        "by_mode": {
            "full": {
                "execution_count": 800,
                "avg_latency_ms": 950
            },
            "tracking": {
                "execution_count": 450,
                "avg_latency_ms": 420
            }
        }
    }
    ```

    Args:
        mode: Mode filter ('all', 'full', or 'tracking')
        db: Database session

    Returns:
        Analytics data aggregated by mode
    """
    if mode == "all":
        # Total execution count
        total_result = await db.execute(select(func.count(Execution.execution_id)))
        total_executions = total_result.scalar() or 0

        # Count prompts by mode
        full_count_result = await db.execute(
            select(func.count(Prompt.prompt_id)).where(Prompt.mode == "full")
        )
        full_prompts = full_count_result.scalar() or 0

        tracking_count_result = await db.execute(
            select(func.count(Prompt.prompt_id)).where(Prompt.mode == "tracking")
        )
        tracking_prompts = tracking_count_result.scalar() or 0

        # Execution stats by mode - full
        full_exec_result = await db.execute(
            select(
                func.count(Execution.execution_id).label("count"),
                func.avg(Execution.latency_ms).label("avg_latency"),
            )
            .join(Prompt, Prompt.prompt_id == Execution.prompt_id)
            .where(Prompt.mode == "full")
        )
        full_stats = full_exec_result.first()

        # Execution stats by mode - tracking
        tracking_exec_result = await db.execute(
            select(
                func.count(Execution.execution_id).label("count"),
                func.avg(Execution.latency_ms).label("avg_latency"),
            )
            .join(Prompt, Prompt.prompt_id == Execution.prompt_id)
            .where(Prompt.mode == "tracking")
        )
        tracking_stats = tracking_exec_result.first()

        total_cost = await _cost_by_mode(db, mode=None)

        return {
            "summary": {
                "total_executions": total_executions,
                "full_mode_prompts": full_prompts,
                "tracking_mode_prompts": tracking_prompts,
                "total_cost": total_cost,
            },
            "by_mode": {
                "full": {
                    "execution_count": full_stats.count or 0,
                    "avg_latency_ms": int(full_stats.avg_latency or 0),
                },
                "tracking": {
                    "execution_count": tracking_stats.count or 0,
                    "avg_latency_ms": int(tracking_stats.avg_latency or 0),
                },
            },
        }

    else:
        # Mode-specific analytics
        # Count prompts in this mode
        prompt_count_result = await db.execute(
            select(func.count(Prompt.prompt_id)).where(Prompt.mode == mode)
        )
        prompt_count = prompt_count_result.scalar() or 0

        # Execution stats for this mode
        exec_stats_result = await db.execute(
            select(
                func.count(Execution.execution_id).label("count"),
                func.avg(Execution.latency_ms).label("avg_latency"),
                func.sum(Execution.prompt_tokens).label("total_prompt_tokens"),
                func.sum(Execution.response_tokens).label("total_response_tokens"),
            )
            .join(Prompt, Prompt.prompt_id == Execution.prompt_id)
            .where(Prompt.mode == mode)
        )
        stats = exec_stats_result.first()

        total_cost = await _cost_by_mode(db, mode=mode)

        return {
            "mode": mode,
            "prompt_count": prompt_count,
            "execution_count": stats.count or 0,
            "avg_latency_ms": int(stats.avg_latency or 0),
            "total_prompt_tokens": stats.total_prompt_tokens or 0,
            "total_response_tokens": stats.total_response_tokens or 0,
            "total_cost": total_cost,
        }
