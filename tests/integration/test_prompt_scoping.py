"""Integration tests for project-scoped prompt endpoints — Story 2.2."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.api.dependencies import _key_cache
from prompt_ledger.api.main import app
from prompt_ledger.db.database import get_db
from prompt_ledger.models.project import ApiKey, Project, hash_api_key


@pytest.fixture
async def project_b_client(db_session: AsyncSession):
    """A second authenticated client for project B."""
    proj_b = Project(name="project-b")
    db_session.add(proj_b)
    await db_session.flush()

    key_b = "project-b-key"
    db_session.add(
        ApiKey(
            key_hash=hash_api_key(key_b),
            project_id=proj_b.project_id,
            label="project-b test key",
        )
    )
    await db_session.flush()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["X-API-Key"] = key_b
        yield ac

    _key_cache.clear()


class TestPromptScoping:
    async def test_list_prompts_returns_only_own_project(
        self, client: AsyncClient, project_b_client: AsyncClient
    ):
        """GET /v1/prompts returns only the calling project's prompts."""
        # Register prompt for project A (default)
        await client.post(
            "/v1/prompts/register-code",
            json={"prompts": [{"name": "proj-a-prompt", "template_source": "Hello A"}]},
        )

        # Project A sees its prompt
        resp_a = await client.get("/v1/prompts")
        assert resp_a.status_code == 200
        names_a = [p["name"] for p in resp_a.json()]
        assert "proj-a-prompt" in names_a

        # Project B sees empty list
        resp_b = await project_b_client.get("/v1/prompts")
        assert resp_b.status_code == 200
        assert resp_b.json() == []

    async def test_get_prompt_404_across_projects(
        self, client: AsyncClient, project_b_client: AsyncClient
    ):
        """GET /v1/prompts/{name} returns 404 if prompt belongs to another project."""
        await client.post(
            "/v1/prompts/register-code",
            json={"prompts": [{"name": "private-prompt", "template_source": "Secret"}]},
        )

        resp = await project_b_client.get("/v1/prompts/private-prompt")
        assert resp.status_code == 404

    async def test_put_prompt_scoped(
        self, client: AsyncClient, project_b_client: AsyncClient
    ):
        """PUT /v1/prompts/{name} by project B cannot overwrite project A's prompt."""
        await client.put(
            "/v1/prompts/contested",
            json={"template_source": "Project A version", "set_active": True},
        )

        # Project B creating same name creates its own prompt, not an overwrite
        resp = await project_b_client.put(
            "/v1/prompts/contested",
            json={"template_source": "Project B version", "set_active": True},
        )
        assert resp.status_code == 200

        # Project A's prompt is unchanged
        resp_a = await client.get("/v1/prompts/contested")
        assert resp_a.status_code == 200
        assert resp_a.json()["active_version"]["template_source"] == "Project A version"

    async def test_same_prompt_name_independent_versions(
        self, client: AsyncClient, project_b_client: AsyncClient
    ):
        """Two projects can register the same name with different templates independently."""
        await client.post(
            "/v1/prompts/register-code",
            json={"prompts": [{"name": "shared", "template_source": "Template for A"}]},
        )
        await project_b_client.post(
            "/v1/prompts/register-code",
            json={"prompts": [{"name": "shared", "template_source": "Template for B"}]},
        )

        resp_a = await client.get("/v1/prompts/shared")
        resp_b = await project_b_client.get("/v1/prompts/shared")

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert (
            resp_a.json()["active_version"]["template_source"]
            != resp_b.json()["active_version"]["template_source"]
        )

    async def test_register_code_scoped(
        self, client: AsyncClient, project_b_client: AsyncClient
    ):
        """register-code dry_run does not cross project boundaries."""
        await client.post(
            "/v1/prompts/register-code",
            json={"prompts": [{"name": "existing", "template_source": "v1"}]},
        )

        # Project B's dry-run sees it as "new", not "unchanged"
        resp = await project_b_client.post(
            "/v1/prompts/register-code",
            json={
                "prompts": [{"name": "existing", "template_source": "v1"}],
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["details"][0]["action"] == "new"
