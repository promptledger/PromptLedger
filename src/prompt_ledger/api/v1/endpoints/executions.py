"""Execution endpoints."""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...db.database import get_db
from ...models.execution import Execution, ExecutionInput
from ...models.model import Model
from ...models.prompt import Prompt, PromptVersion
from ...services.execution import ExecutionService
from ...services.providers import ProviderAdapterFactory

router = APIRouter()


@router.post("/run", response_model=Dict[str, Any])
async def run_execution_sync(
    execution_request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Execute a prompt synchronously."""
    
    service = ExecutionService(db)
    result = await service.execute_sync(execution_request)
    return result


@router.post("/submit", response_model=Dict[str, Any])
async def submit_execution_async(
    execution_request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Submit a prompt for asynchronous execution."""
    
    service = ExecutionService(db)
    result = await service.submit_async(execution_request)
    return result


@router.get("/{execution_id}", response_model=Dict[str, Any])
async def get_execution(
    execution_id: str = Path(..., description="Execution ID"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get execution status and results."""
    
    try:
        uuid_obj = UUID(execution_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid execution ID format")
    
    result = await db.execute(
        select(Execution)
        .where(Execution.execution_id == uuid_obj)
        .options(
            # Eager load relationships
            selectinload(Execution.prompt),
            selectinload(Execution.version),
            selectinload(Execution.model),
            selectinload(Execution.execution_input)
        )
    )
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    response = {
        "execution_id": str(execution.execution_id),
        "status": execution.status,
        "mode": execution.execution_mode,
        "environment": execution.environment,
        "created_at": execution.created_at.isoformat(),
    }
    
    # Include results if completed
    if execution.status in ["succeeded", "failed"]:
        response["response_text"] = execution.response_text
        response["completed_at"] = execution.completed_at.isoformat() if execution.completed_at else None
        
        if execution.status == "failed":
            response["error_type"] = execution.error_type
            response["error_message"] = execution.error_message
    
    # Include telemetry if available
    if execution.prompt_tokens is not None:
        response["telemetry"] = {
            "prompt_tokens": execution.prompt_tokens,
            "response_tokens": execution.response_tokens,
            "latency_ms": execution.latency_ms,
        }
    
    return response


@router.get("/", response_model=Dict[str, Any])
async def list_executions(
    prompt_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List executions with optional filtering."""
    
    query = select(Execution).order_by(Execution.created_at.desc())
    
    # Apply filters
    if prompt_name:
        query = query.join(Prompt).where(Prompt.name == prompt_name)
    
    if status:
        query = query.where(Execution.status == status)
    
    # Apply pagination
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    executions = result.scalars().all()
    
    return {
        "executions": [
            {
                "execution_id": str(exec.execution_id),
                "prompt_name": exec.prompt.name if exec.prompt else None,
                "status": exec.status,
                "mode": exec.execution_mode,
                "created_at": exec.created_at.isoformat(),
                "completed_at": exec.completed_at.isoformat() if exec.completed_at else None,
            }
            for exec in executions
        ],
        "total": len(executions),
        "limit": limit,
        "offset": offset,
    }
