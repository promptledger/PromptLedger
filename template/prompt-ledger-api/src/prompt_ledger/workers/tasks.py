"""Celery tasks for async execution."""

import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from ..db.database import SyncSessionLocal
from ..models.execution import Execution
from ..models.model import Model
from ..models.prompt import Prompt, PromptVersion
from ..services.providers import ProviderAdapterFactory
from .celery_app import celery_app


@celery_app.task(bind=True, max_retries=3)
def execute_prompt_task(self, execution_id: str) -> dict[str, str]:
    """Execute a prompt asynchronously using sync database operations.

    This task uses synchronous database operations (psycopg) instead of async
    (asyncpg) to avoid event loop conflicts in Celery's forked/threaded workers.
    """
    with SyncSessionLocal() as db:
        try:
            # Load execution
            execution = db.execute(
                select(Execution).where(Execution.execution_id == UUID(execution_id))
            ).scalar_one_or_none()

            if not execution:
                raise ValueError(f"Execution {execution_id} not found")

            # Mark as running
            execution.status = "running"
            execution.started_at = datetime.now(timezone.utc)
            db.commit()

            # Load related data
            result = db.execute(
                select(PromptVersion, Model)
                .join(Model, Model.model_id == execution.model_id)
                .where(PromptVersion.version_id == execution.version_id)
            )
            version, model = result.first()

            # Get provider and execute
            provider_factory = ProviderAdapterFactory()
            provider = provider_factory.get_provider(model.provider)
            start_time = time.time()

            # Prepare parameters
            params = {}
            if execution.temperature is not None:
                params["temperature"] = execution.temperature
            if execution.max_new_tokens is not None:
                params["max_tokens"] = execution.max_new_tokens
            if execution.top_p is not None:
                params["top_p"] = execution.top_p

            # Execute the LLM call (this is async, so we need to run it)
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                llm_result = loop.run_until_complete(
                    provider.generate(
                        rendered_prompt=execution.rendered_prompt,
                        model_name=model.model_name,
                        params=params,
                    )
                )
            finally:
                loop.close()

            # Update execution with results
            execution.status = "succeeded"
            execution.response_text = llm_result["response_text"]
            execution.prompt_tokens = llm_result.get("prompt_tokens")
            execution.response_tokens = llm_result.get("response_tokens")
            execution.latency_ms = int((time.time() - start_time) * 1000)
            execution.completed_at = datetime.now(timezone.utc)

            db.commit()

            return {"status": "succeeded", "execution_id": execution_id}

        except Exception as exc:
            # Handle retry logic
            if self.request.retries < self.max_retries:
                # Exponential backoff: 5s, 10s, 20s
                countdown = min(5 * (2**self.request.retries), 20)
                raise self.retry(exc=exc, countdown=countdown)

            # Final failure - update execution
            try:
                execution.status = "failed"
                execution.error_type = type(exc).__name__
                execution.error_message = str(exc)
                execution.completed_at = datetime.now(timezone.utc)
                db.commit()
            except Exception:
                pass  # Log error but don't fail the task

            return {"status": "failed", "execution_id": execution_id, "error": str(exc)}
