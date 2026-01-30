"""Analytics endpoints for unified reporting across modes."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.db.database import get_db
from prompt_ledger.models.execution import Execution
from prompt_ledger.models.prompt import Prompt

router = APIRouter()


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

        return {
            "summary": {
                "total_executions": total_executions,
                "full_mode_prompts": full_prompts,
                "tracking_mode_prompts": tracking_prompts,
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

        return {
            "mode": mode,
            "prompt_count": prompt_count,
            "execution_count": stats.count or 0,
            "avg_latency_ms": int(stats.avg_latency or 0),
            "total_prompt_tokens": stats.total_prompt_tokens or 0,
            "total_response_tokens": stats.total_response_tokens or 0,
        }
