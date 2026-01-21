"""Code-based prompt management endpoints.

These endpoints support the "tracking mode" for prompts, where prompts are
defined in application code and the system tracks usage and automatically
detects version changes based on template content.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.db.database import get_db
from prompt_ledger.models.execution import Execution
from prompt_ledger.models.prompt import Prompt, PromptVersion
from prompt_ledger.services.execution import ExecutionService
from prompt_ledger.services.prompt_service import PromptService

router = APIRouter()


@router.post("/register-code", response_model=Dict[str, Any])
async def register_code_prompts(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Register code-based prompts with automatic versioning.

    This endpoint is designed for prompts defined in application code. It
    automatically detects content changes and creates new versions only when
    the template content has changed.

    Request format:
    ```json
    {
        "prompts": [
            {
                "name": "WELCOME",
                "template_source": "Hello {{name}}!",
                "template_hash": "abc123..."  // optional, computed if missing
            }
        ]
    }
    ```

    Response format:
    ```json
    {
        "registered": [
            {
                "name": "WELCOME",
                "mode": "tracking",
                "version": 2,
                "change_detected": true,
                "previous_version": 1
            }
        ]
    }
    ```

    Args:
        request: Registration request with list of prompts
        db: Database session

    Returns:
        Registration results with version information and change detection

    Raises:
        HTTPException(400): If no prompts provided or invalid data
    """
    service = PromptService(db)
    prompts = request.get("prompts", [])

    if not prompts:
        raise HTTPException(
            status_code=400,
            detail="No prompts provided. Include 'prompts' array in request body.",
        )

    results = await service.register_code_prompts(prompts)

    return {"registered": results}


@router.post("/{name}/execute", response_model=Dict[str, Any])
async def execute_code_prompt(
    name: str,
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Execute a code-based (tracking mode) prompt.

    This endpoint executes prompts that are in "tracking" mode. It will reject
    attempts to execute "full" mode prompts with a clear error message.

    Request format:
    ```json
    {
        "variables": {"name": "John"},
        "version": null,  // optional, uses active version if not specified
        "model_name": "gpt-4o-mini",
        "mode": "sync",  // or "async"
        "params": {  // optional model parameters
            "temperature": 0.7,
            "max_new_tokens": 800
        }
    }
    ```

    Response format (sync):
    ```json
    {
        "execution_id": "uuid",
        "prompt_mode": "tracking",
        "status": "succeeded",
        "response_text": "...",
        "telemetry": {"prompt_tokens": 15, "response_tokens": 8, "latency_ms": 450}
    }
    ```

    Response format (async):
    ```json
    {
        "execution_id": "uuid",
        "prompt_mode": "tracking",
        "status": "queued",
        "mode": "async"
    }
    ```

    Args:
        name: Prompt name
        request: Execution request with variables and configuration
        db: Database session

    Returns:
        Execution result with telemetry (sync) or execution ID (async)

    Raises:
        HTTPException(404): If prompt not found
        HTTPException(400): If prompt is not in tracking mode
    """
    # Validate prompt is in tracking mode
    prompt_service = PromptService(db)
    await prompt_service.validate_mode(name, "tracking", "execute operation")

    # Build execution request for execution service
    execution_request = {
        "prompt_name": name,
        "version_number": request.get("version"),
        "variables": request.get("variables", {}),
        "model": {
            "provider": "openai",  # Default to OpenAI for now
            "model_name": request.get("model_name", "gpt-4o-mini"),
        },
        "params": request.get("params", {}),
        "environment": request.get("environment", "dev"),
        "correlation_id": request.get("correlation_id"),
        "idempotency_key": request.get("idempotency_key"),
    }

    # Execute based on mode
    execution_service = ExecutionService(db)
    mode = request.get("mode", "sync")

    if mode == "sync":
        result = await execution_service.execute_sync(execution_request)
    elif mode == "async":
        result = await execution_service.submit_async(execution_request)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid execution mode: {mode}. Must be 'sync' or 'async'.",
        )

    # Add mode indicator to response
    result["prompt_mode"] = "tracking"
    return result


@router.get("/{name}/history", response_model=Dict[str, Any])
async def get_prompt_history(
    name: str,
    mode: str = "full",
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get prompt version history (works for both modes).

    Returns version history with execution counts for each version.
    Works for both full management mode and tracking mode prompts.

    Args:
        name: Prompt name
        mode: Filter by mode (not used for filtering, just for documentation)
        db: Database session

    Returns:
        Version history with execution counts

    Raises:
        HTTPException(404): If prompt not found
    """
    # Find prompt
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")

    # Get versions with execution counts
    result = await db.execute(
        select(
            PromptVersion, func.count(Execution.execution_id).label("execution_count")
        )
        .outerjoin(Execution, Execution.version_id == PromptVersion.version_id)
        .where(PromptVersion.prompt_id == prompt.prompt_id)
        .group_by(PromptVersion.version_id)
        .order_by(PromptVersion.version_number.desc())
    )
    versions_data = result.all()

    versions = []
    for version, exec_count in versions_data:
        versions.append(
            {
                "version": version.version_number,
                "template_hash": version.checksum_hash,
                "template_source": version.template_source,
                "created_at": version.created_at.isoformat(),
                "execution_count": exec_count,
            }
        )

    return {
        "prompt_name": name,
        "mode": prompt.mode,
        "current_version": versions[0]["version"] if versions else None,
        "versions": versions,
    }
