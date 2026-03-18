"""Integration and worker-path tests for Epic 3 async execution observability."""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.execution import Execution
from prompt_ledger.models.model import Model
from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum
from prompt_ledger.models.project import Project
from prompt_ledger.models.span import Span
from prompt_ledger.workers.tasks import execute_prompt_task


MOCK_GENERATE_RESULT = {
    "response_text": "Async test response",
    "prompt_tokens": 21,
    "response_tokens": 9,
    "latency_ms": 111,
}


async def _seed_model(
    db: AsyncSession,
    model_name: str = "gpt-4o-mini",
    provider: str = "openai",
) -> Model:
    model = Model(
        model_id=uuid.uuid4(),
        provider=provider,
        model_name=model_name,
        max_tokens=4096,
    )
    db.add(model)
    await db.flush()
    return model


async def _seed_tracking_prompt(
    db: AsyncSession,
    name: str,
    project_id,
) -> tuple[Prompt, PromptVersion]:
    prompt = Prompt(
        name=name,
        mode="tracking",
        description="test tracking prompt",
        project_id=project_id,
    )
    db.add(prompt)
    await db.flush()

    template = "You are a debater. Topic: {{topic}}"
    version = PromptVersion(
        prompt_id=prompt.prompt_id,
        version_number=1,
        template_source=template,
        checksum_hash=compute_checksum(template),
        status="active",
    )
    db.add(version)
    await db.flush()

    prompt.active_version_id = version.version_id
    await db.flush()
    return prompt, version


def _make_sync_sessionmaker(db_session: AsyncSession):
    async_url = db_session.bind.url.render_as_string(hide_password=False)
    sync_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url, future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory, engine


async def _default_project_id(db_session: AsyncSession):
    result = await db_session.execute(select(Project).where(Project.name == "default"))
    project = result.scalar_one_or_none()
    if project is None:
        project = Project(name="default")
        db_session.add(project)
        await db_session.flush()
    return project.project_id


async def _seed_parent_span(db: AsyncSession, project_id, trace_id: str) -> Span:
    parent = Span(
        trace_id=trace_id,
        name="parent",
        kind="workflow",
        status="ok",
        project_id=project_id,
    )
    db.add(parent)
    await db.flush()
    return parent


class TestAsyncSubmitEndpoint:
    async def test_submit_rejects_span_without_trace_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        project_id = await _default_project_id(db_session)
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "async.submit.invalid-span", project_id)
        await db_session.commit()

        response = await client.post(
            "/v1/executions/submit",
            headers={"X-API-Key": "test-key"},
            json={
                "prompt_name": "async.submit.invalid-span",
                "variables": {"topic": "test"},
                "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                "span": {"agent_id": "agent-x"},
            },
        )

        assert response.status_code == 422
        assert "trace_id" in response.json()["detail"]

    async def test_submit_forwards_span_context_to_celery_task(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        project_id = await _default_project_id(db_session)
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "async.submit.forward-span", project_id)
        await db_session.commit()

        span_block = {
            "trace_id": "async-trace-001",
            "parent_span_id": str(uuid.uuid4()),
            "agent_id": "agent-x",
            "kind": "llm.generation",
        }

        with patch(
            "prompt_ledger.workers.celery_app.celery_app.send_task"
        ) as mock_send_task:
            response = await client.post(
                "/v1/executions/submit",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": "async.submit.forward-span",
                    "variables": {"topic": "test"},
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "span": span_block,
                },
            )

        assert response.status_code == 202
        mock_send_task.assert_called_once()
        args = mock_send_task.call_args.kwargs["args"]
        assert len(args) == 2
        assert args[1]["trace_id"] == "async-trace-001"
        assert args[1]["agent_id"] == "agent-x"


class TestAsyncWorkerSpanCreation:
    async def test_worker_creates_span_and_returns_span_id(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        project_id = await _default_project_id(db_session)
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "async.worker.span", project_id)
        parent_span = await _seed_parent_span(
            db_session, project_id, "async-trace-001"
        )

        execution = Execution(
            prompt_id=(await db_session.execute(select(Prompt.prompt_id).where(Prompt.name == "async.worker.span"))).scalar_one(),
            version_id=(await db_session.execute(select(PromptVersion.version_id).join(Prompt, Prompt.prompt_id == PromptVersion.prompt_id).where(Prompt.name == "async.worker.span"))).scalar_one(),
            model_id=(await db_session.execute(select(Model.model_id).where(Model.model_name == "gpt-4o-mini"))).scalar_one(),
            model_name="gpt-4o-mini",
            project_id=project_id,
            environment="test",
            execution_mode="async",
            status="queued",
            rendered_prompt="Rendered prompt",
        )
        db_session.add(execution)
        await db_session.flush()
        await db_session.commit()

        sync_factory, sync_engine = _make_sync_sessionmaker(db_session)
        monkeypatch.setattr("prompt_ledger.workers.tasks.SyncSessionLocal", sync_factory)

        try:
            with patch(
                "prompt_ledger.services.providers.OpenAIAdapter.generate",
                new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
            ):
                result = await asyncio.to_thread(
                    execute_prompt_task.run,
                    str(execution.execution_id),
                    {
                        "trace_id": "async-trace-001",
                        "parent_span_id": str(parent_span.span_id),
                        "agent_id": "paper_1",
                    },
                )
        finally:
            sync_engine.dispose()

        assert result["status"] == "succeeded"
        assert result["span_id"] is not None

        refreshed = await db_session.execute(
            select(Span).where(Span.execution_id == execution.execution_id)
        )
        span = refreshed.scalar_one()
        assert span.trace_id == "async-trace-001"
        assert span.parent_span_id == parent_span.span_id
        assert span.agent_id == "paper_1"
        assert span.prompt_tokens == MOCK_GENERATE_RESULT["prompt_tokens"]
        assert span.completion_tokens == MOCK_GENERATE_RESULT["response_tokens"]

    async def test_worker_returns_null_span_id_when_no_span_context(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        project_id = await _default_project_id(db_session)
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "async.worker.nospan", project_id)

        execution = Execution(
            prompt_id=(await db_session.execute(select(Prompt.prompt_id).where(Prompt.name == "async.worker.nospan"))).scalar_one(),
            version_id=(await db_session.execute(select(PromptVersion.version_id).join(Prompt, Prompt.prompt_id == PromptVersion.prompt_id).where(Prompt.name == "async.worker.nospan"))).scalar_one(),
            model_id=(await db_session.execute(select(Model.model_id).where(Model.model_name == "gpt-4o-mini"))).scalar_one(),
            model_name="gpt-4o-mini",
            project_id=project_id,
            environment="test",
            execution_mode="async",
            status="queued",
            rendered_prompt="Rendered prompt",
        )
        db_session.add(execution)
        await db_session.flush()
        await db_session.commit()

        sync_factory, sync_engine = _make_sync_sessionmaker(db_session)
        monkeypatch.setattr("prompt_ledger.workers.tasks.SyncSessionLocal", sync_factory)

        try:
            with patch(
                "prompt_ledger.services.providers.OpenAIAdapter.generate",
                new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
            ):
                result = await asyncio.to_thread(
                    execute_prompt_task.run, str(execution.execution_id), None
                )
        finally:
            sync_engine.dispose()

        assert result["status"] == "succeeded"
        assert result["span_id"] is None

    async def test_worker_span_write_failure_does_not_fail_execution(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        project_id = await _default_project_id(db_session)
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "async.worker.spanfail", project_id)

        execution = Execution(
            prompt_id=(await db_session.execute(select(Prompt.prompt_id).where(Prompt.name == "async.worker.spanfail"))).scalar_one(),
            version_id=(await db_session.execute(select(PromptVersion.version_id).join(Prompt, Prompt.prompt_id == PromptVersion.prompt_id).where(Prompt.name == "async.worker.spanfail"))).scalar_one(),
            model_id=(await db_session.execute(select(Model.model_id).where(Model.model_name == "gpt-4o-mini"))).scalar_one(),
            model_name="gpt-4o-mini",
            project_id=project_id,
            environment="test",
            execution_mode="async",
            status="queued",
            rendered_prompt="Rendered prompt",
        )
        db_session.add(execution)
        await db_session.flush()
        await db_session.commit()

        sync_factory, sync_engine = _make_sync_sessionmaker(db_session)
        monkeypatch.setattr("prompt_ledger.workers.tasks.SyncSessionLocal", sync_factory)

        def boom(*args, **kwargs):
            raise RuntimeError("span flush failed")

        monkeypatch.setattr("prompt_ledger.workers.tasks.build_execution_span", boom)

        try:
            with patch(
                "prompt_ledger.services.providers.OpenAIAdapter.generate",
                new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
            ):
                result = await asyncio.to_thread(
                    execute_prompt_task.run,
                    str(execution.execution_id),
                    {"trace_id": "async-trace-fail"},
                )
        finally:
            sync_engine.dispose()

        assert result["status"] == "succeeded"
        assert result["span_id"] is None

        await db_session.refresh(execution)
        assert execution.status == "succeeded"
