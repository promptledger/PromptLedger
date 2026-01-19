"""Execution service for handling prompt execution."""

import time
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from jinja2 import Environment, TemplateError, UndefinedError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.execution import Execution, ExecutionInput
from prompt_ledger.models.model import Model
from prompt_ledger.models.prompt import Prompt, PromptVersion
from prompt_ledger.services.providers import ProviderAdapterFactory


class ExecutionService:
    """Service for managing prompt executions."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.provider_factory = ProviderAdapterFactory()

    async def execute_sync(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a prompt synchronously."""

        # Resolve prompt and version
        prompt, version, model = await self._resolve_execution_context(request)

        # Render prompt
        rendered_prompt, variables = await self._render_prompt(
            version.template_source, request.get("variables", {})
        )

        # Create execution record
        execution = await self._create_execution(
            prompt=prompt,
            version=version,
            model=model,
            rendered_prompt=rendered_prompt,
            variables=variables,
            mode="sync",
            request=request,
        )

        # Execute via provider
        provider = self.provider_factory.get_provider(model.provider)
        start_time = time.time()

        try:
            result = await provider.generate(
                rendered_prompt=rendered_prompt,
                model_name=model.model_name,
                params=request.get("params", {}),
            )

            # Update execution with results
            execution.status = "succeeded"
            execution.response_text = result["response_text"]
            execution.prompt_tokens = result.get("prompt_tokens")
            execution.response_tokens = result.get("response_tokens")
            execution.latency_ms = int((time.time() - start_time) * 1000)
            execution.completed_at = func.now()

        except Exception as e:
            execution.status = "failed"
            execution.error_type = type(e).__name__
            execution.error_message = str(e)
            execution.completed_at = func.now()
            raise

        await self.db.commit()

        return {
            "execution_id": str(execution.execution_id),
            "status": execution.status,
            "mode": execution.execution_mode,
            "response_text": execution.response_text,
            "telemetry": {
                "prompt_tokens": execution.prompt_tokens,
                "response_tokens": execution.response_tokens,
                "latency_ms": execution.latency_ms,
            },
        }

    async def submit_async(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a prompt for asynchronous execution."""

        # Resolve prompt and version
        prompt, version, model = await self._resolve_execution_context(request)

        # Render prompt
        rendered_prompt, variables = await self._render_prompt(
            version.template_source, request.get("variables", {})
        )

        # Create execution record
        execution = await self._create_execution(
            prompt=prompt,
            version=version,
            model=model,
            rendered_prompt=rendered_prompt,
            variables=variables,
            mode="async",
            request=request,
        )

        await self.db.commit()

        # Queue for async execution
        from ..workers.celery_app import celery_app

        celery_app.send_task("execute_prompt_task", args=[str(execution.execution_id)])

        return {
            "execution_id": str(execution.execution_id),
            "status": execution.status,
            "mode": execution.execution_mode,
        }

    async def _resolve_execution_context(
        self, request: Dict[str, Any]
    ) -> tuple[Prompt, PromptVersion, Model]:
        """Resolve prompt, version, and model from request."""

        prompt_name = request["prompt_name"]
        version_number = request.get("version_number")
        model_config = request["model"]

        # Find prompt
        result = await self.db.execute(select(Prompt).where(Prompt.name == prompt_name))
        prompt = result.scalar_one_or_none()
        if not prompt:
            raise ValueError(f"Prompt '{prompt_name}' not found")

        # Find version
        if version_number:
            result = await self.db.execute(
                select(PromptVersion).where(
                    PromptVersion.prompt_id == prompt.prompt_id,
                    PromptVersion.version_number == version_number,
                )
            )
            version = result.scalar_one_or_none()
        else:
            # Use active version
            result = await self.db.execute(
                select(PromptVersion).where(
                    PromptVersion.version_id == prompt.active_version_id
                )
            )
            version = result.scalar_one_or_none()

        if not version:
            raise ValueError(f"Prompt version not found")

        # Find model
        result = await self.db.execute(
            select(Model).where(
                Model.provider == model_config["provider"],
                Model.model_name == model_config["model_name"],
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(
                f"Model '{model_config['provider']}/{model_config['model_name']}' not found"
            )

        return prompt, version, model

    async def _render_prompt(
        self, template_source: str, variables: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """Render prompt template with variables."""

        env = Environment(undefined=StrictUndefined)
        template = env.from_string(template_source)

        try:
            rendered = template.render(**variables)
            return rendered, variables
        except (TemplateError, UndefinedError) as e:
            raise ValueError(f"Template rendering failed: {e}")

    async def _create_execution(
        self,
        prompt: Prompt,
        version: PromptVersion,
        model: Model,
        rendered_prompt: str,
        variables: Dict[str, Any],
        mode: str,
        request: Dict[str, Any],
    ) -> Execution:
        """Create execution record."""

        execution = Execution(
            prompt_id=prompt.prompt_id,
            version_id=version.version_id,
            model_id=model.model_id,
            environment=request.get("environment", "dev"),
            execution_mode=mode,
            status="queued" if mode == "async" else "running",
            correlation_id=request.get("correlation_id"),
            idempotency_key=request.get("idempotency_key"),
            rendered_prompt=rendered_prompt,
            temperature=request.get("params", {}).get("temperature"),
            top_k=request.get("params", {}).get("top_k"),
            top_p=request.get("params", {}).get("top_p"),
            repetition_penalty=request.get("params", {}).get("repetition_penalty"),
            max_new_tokens=request.get("params", {}).get("max_new_tokens"),
        )

        self.db.add(execution)
        await self.db.flush()

        # Create execution input record
        execution_input = ExecutionInput(
            execution_id=execution.execution_id,
            variables_json=variables,
        )
        self.db.add(execution_input)

        await self.db.flush()
        return execution


class StrictUndefined:
    """Strict undefined variable handler for Jinja2."""

    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        raise UndefinedError(f"'{self.name}' is undefined")

    def __getattr__(self, name: str) -> "StrictUndefined":
        raise UndefinedError(f"'{self.name}.{name}' is undefined")
