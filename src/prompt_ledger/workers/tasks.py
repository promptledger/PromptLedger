"""Celery tasks for async execution."""

import time
from uuid import UUID

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from ..db.database import AsyncSessionLocal
from ..models.execution import Execution
from ..models.model import Model
from ..models.prompt import Prompt, PromptVersion
from ..services.providers import ProviderAdapterFactory
from .celery_app import celery_app


@celery_app.task(bind=True, max_retries=3)
def execute_prompt_task(self, execution_id: str) -> dict[str, str]:
    """Execute a prompt asynchronously."""
    
    # This is a sync task that creates an async context
    import asyncio
    
    return asyncio.run(_execute_prompt_async(self, execution_id))


async def _execute_prompt_async(task, execution_id: str) -> dict[str, str]:
    """Async execution logic."""
    
    async with AsyncSessionLocal() as db:
        try:
            # Load execution
            result = await db.execute(
                select(Execution).where(Execution.execution_id == UUID(execution_id))
            )
            execution = result.scalar_one_or_none()
            
            if not execution:
                raise ValueError(f"Execution {execution_id} not found")
            
            # Mark as running
            execution.status = "running"
            execution.started_at = func.now()
            await db.commit()
            
            # Load related data
            result = await db.execute(
                select(Prompt, PromptVersion, Model)
                .join(PromptVersion, Prompt.prompt_id == PromptVersion.prompt_id)
                .join(Model, Model.model_id == Execution.model_id)
                .where(Execution.execution_id == UUID(execution_id))
            )
            prompt, version, model = result.first()
            
            # Get provider and execute
            provider = ProviderAdapterFactory.get_provider(model.provider)
            start_time = time.time()
            
            # Prepare parameters
            params = {}
            if execution.temperature is not None:
                params["temperature"] = execution.temperature
            if execution.max_new_tokens is not None:
                params["max_tokens"] = execution.max_new_tokens
            if execution.top_p is not None:
                params["top_p"] = execution.top_p
            
            result = await provider.generate(
                rendered_prompt=execution.rendered_prompt,
                model_name=model.model_name,
                params=params,
            )
            
            # Update execution with results
            execution.status = "succeeded"
            execution.response_text = result["response_text"]
            execution.prompt_tokens = result.get("prompt_tokens")
            execution.response_tokens = result.get("response_tokens")
            execution.latency_ms = result["latency_ms"]
            execution.completed_at = func.now()
            
            await db.commit()
            
            return {"status": "succeeded", "execution_id": execution_id}
            
        except Exception as exc:
            # Handle retry logic
            if task.request.retries < task.max_retries:
                # Exponential backoff: 5s, 30s, 2m
                countdown = min(5 * (2 ** task.request.retries), 120)
                raise task.retry(exc=exc, countdown=countdown)
            
            # Final failure - update execution
            try:
                execution.status = "failed"
                execution.error_type = type(exc).__name__
                execution.error_message = str(exc)
                execution.completed_at = func.now()
                await db.commit()
            except Exception:
                pass  # Log error but don't fail the task
            
            return {"status": "failed", "execution_id": execution_id, "error": str(exc)}
