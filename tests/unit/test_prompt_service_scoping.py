"""Unit tests for project-scoped PromptService queries — Story 2.2."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.project import Project
from prompt_ledger.models.prompt import Prompt, compute_checksum
from prompt_ledger.services.prompt_service import PromptService


@pytest.fixture
async def two_projects(db_session: AsyncSession):
    """Create two projects and return their IDs."""
    proj_a = Project(name="project-a")
    proj_b = Project(name="project-b")
    db_session.add_all([proj_a, proj_b])
    await db_session.flush()
    return proj_a.project_id, proj_b.project_id


class TestPromptServiceScoping:
    async def test_register_prompt_sets_project_id(
        self, db_session: AsyncSession, two_projects
    ):
        proj_a_id, _ = two_projects
        service = PromptService(db_session, project_id=proj_a_id)
        template = "Hello {{name}}!"

        await service.register_code_prompts(
            [{"name": "greeting", "template_source": template}]
        )

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"])
            .select(Prompt)
            .where(Prompt.name == "greeting")
        )
        prompt = result.scalar_one()
        assert prompt.project_id == proj_a_id

    async def test_same_name_allowed_in_different_projects(
        self, db_session: AsyncSession, two_projects
    ):
        proj_a_id, proj_b_id = two_projects
        service_a = PromptService(db_session, project_id=proj_a_id)
        service_b = PromptService(db_session, project_id=proj_b_id)
        template = "Hello {{name}}!"

        result_a = await service_a.register_code_prompts(
            [{"name": "shared-name", "template_source": template}]
        )
        result_b = await service_b.register_code_prompts(
            [{"name": "shared-name", "template_source": template}]
        )

        assert result_a[0]["action"] == "new"
        assert result_b[0]["action"] == "new"

    async def test_get_prompt_by_name_scoped(
        self, db_session: AsyncSession, two_projects
    ):
        proj_a_id, proj_b_id = two_projects
        service_a = PromptService(db_session, project_id=proj_a_id)
        service_b = PromptService(db_session, project_id=proj_b_id)
        template = "Hello!"

        await service_a.register_code_prompts(
            [{"name": "exclusive", "template_source": template}]
        )

        found = await service_a.get_prompt_by_name("exclusive")
        not_found = await service_b.get_prompt_by_name("exclusive")

        assert found is not None
        assert not_found is None

    async def test_validate_mode_scoped(self, db_session: AsyncSession, two_projects):
        from fastapi import HTTPException

        proj_a_id, proj_b_id = two_projects
        service_a = PromptService(db_session, project_id=proj_a_id)
        service_b = PromptService(db_session, project_id=proj_b_id)
        template = "Hello!"

        await service_a.register_code_prompts(
            [{"name": "owned-prompt", "template_source": template}]
        )

        # Project A can validate its own prompt
        prompt = await service_a.validate_mode("owned-prompt", "tracking", "test")
        assert prompt is not None

        # Project B gets 404 (prompt doesn't exist in its namespace)
        with pytest.raises(HTTPException) as exc_info:
            await service_b.validate_mode("owned-prompt", "tracking", "test")
        assert exc_info.value.status_code == 404

    async def test_register_update_scoped(self, db_session: AsyncSession, two_projects):
        proj_a_id, proj_b_id = two_projects
        service_a = PromptService(db_session, project_id=proj_a_id)
        service_b = PromptService(db_session, project_id=proj_b_id)

        await service_a.register_code_prompts(
            [{"name": "versioned", "template_source": "v1 template"}]
        )

        # Project B updating same name creates its own new prompt, not an update
        result = await service_b.register_code_prompts(
            [{"name": "versioned", "template_source": "v1 template"}]
        )
        assert result[0]["action"] == "new"
        assert result[0]["version"] == 1
