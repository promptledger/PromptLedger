"""Integration tests for code-based prompt endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum


@pytest.fixture
async def full_prompt(db_session: AsyncSession):
    """Create a full mode prompt for testing."""
    prompt = Prompt(name="full_mode_prompt", mode="full", description="Full mode")
    db_session.add(prompt)
    await db_session.flush()  # Flush to get prompt_id

    version = PromptVersion(
        prompt_id=prompt.prompt_id,
        version_number=1,
        template_source="Full mode template {{var}}",
        checksum_hash=compute_checksum("Full mode template {{var}}"),
        status="active",
    )
    db_session.add(version)
    await db_session.flush()

    prompt.active_version_id = version.version_id
    await db_session.commit()
    await db_session.refresh(prompt)
    return prompt


@pytest.fixture
async def tracking_prompt(db_session: AsyncSession):
    """Create a tracking mode prompt for testing."""
    prompt = Prompt(name="tracking_mode_prompt", mode="tracking")
    db_session.add(prompt)
    await db_session.flush()  # Flush to get prompt_id

    version = PromptVersion(
        prompt_id=prompt.prompt_id,
        version_number=1,
        template_source="Tracking mode template {{var}}",
        checksum_hash=compute_checksum("Tracking mode template {{var}}"),
        status="active",
    )
    db_session.add(version)
    await db_session.flush()

    prompt.active_version_id = version.version_id
    await db_session.commit()
    await db_session.refresh(prompt)
    return prompt


class TestRegisterCodePrompts:
    """Test POST /v1/prompts/register-code endpoint."""

    @pytest.mark.asyncio
    async def test_register_new_code_prompts(self, client: AsyncClient):
        """Test registering new code-based prompts."""
        # Arrange
        template = "Hello {{name}}!"
        payload = {
            "prompts": [
                {
                    "name": "WELCOME",
                    "template_source": template,
                    "template_hash": compute_checksum(template),
                }
            ]
        }

        # Act
        response = await client.post(
            "/v1/prompts/register-code", json=payload, headers={"X-API-Key": "test-key"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "registered" in data
        assert len(data["registered"]) == 1
        assert data["registered"][0]["name"] == "WELCOME"
        assert data["registered"][0]["mode"] == "tracking"
        assert data["registered"][0]["version"] == 1
        assert data["registered"][0]["change_detected"] is False

    @pytest.mark.asyncio
    async def test_register_detects_content_changes(self, client: AsyncClient):
        """Test change detection on re-registration."""
        # Arrange
        template_v1 = "Hello {{name}}!"
        template_v2 = "Hi {{name}}, welcome!"

        # Act - Register twice with different content
        await client.post(
            "/v1/prompts/register-code",
            json={
                "prompts": [
                    {
                        "name": "WELCOME",
                        "template_source": template_v1,
                        "template_hash": compute_checksum(template_v1),
                    }
                ]
            },
            headers={"X-API-Key": "test-key"},
        )

        response = await client.post(
            "/v1/prompts/register-code",
            json={
                "prompts": [
                    {
                        "name": "WELCOME",
                        "template_source": template_v2,
                        "template_hash": compute_checksum(template_v2),
                    }
                ]
            },
            headers={"X-API-Key": "test-key"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["registered"][0]["version"] == 2
        assert data["registered"][0]["change_detected"] is True
        assert data["registered"][0]["previous_version"] == 1

    @pytest.mark.asyncio
    async def test_register_unchanged_prompt_returns_same_version(
        self, client: AsyncClient
    ):
        """Test re-registering unchanged prompt doesn't create new version."""
        # Arrange
        template = "Hello {{name}}!"
        payload = {
            "prompts": [
                {
                    "name": "STABLE",
                    "template_source": template,
                    "template_hash": compute_checksum(template),
                }
            ]
        }

        # Act - Register twice with same content
        response1 = await client.post(
            "/v1/prompts/register-code", json=payload, headers={"X-API-Key": "test-key"}
        )
        response2 = await client.post(
            "/v1/prompts/register-code", json=payload, headers={"X-API-Key": "test-key"}
        )

        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        assert data1["registered"][0]["version"] == 1
        assert data2["registered"][0]["version"] == 1  # Same version
        assert data2["registered"][0]["change_detected"] is False

    @pytest.mark.asyncio
    async def test_register_multiple_prompts(self, client: AsyncClient):
        """Test registering multiple prompts in one request."""
        # Arrange
        payload = {
            "prompts": [
                {
                    "name": "WELCOME",
                    "template_source": "Hello!",
                    "template_hash": compute_checksum("Hello!"),
                },
                {
                    "name": "GOODBYE",
                    "template_source": "Bye!",
                    "template_hash": compute_checksum("Bye!"),
                },
            ]
        }

        # Act
        response = await client.post(
            "/v1/prompts/register-code", json=payload, headers={"X-API-Key": "test-key"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["registered"]) == 2
        assert data["registered"][0]["name"] == "WELCOME"
        assert data["registered"][1]["name"] == "GOODBYE"

    @pytest.mark.asyncio
    async def test_register_empty_list_returns_400(self, client: AsyncClient):
        """Test registering empty list returns error."""
        # Arrange
        payload = {"prompts": []}

        # Act
        response = await client.post(
            "/v1/prompts/register-code", json=payload, headers={"X-API-Key": "test-key"}
        )

        # Assert
        assert response.status_code == 400
        assert "no prompts" in response.json()["detail"].lower()


class TestExecuteCodePrompt:
    """Test POST /v1/prompts/{name}/execute endpoint."""

    @pytest.mark.asyncio
    async def test_execute_tracking_mode_prompt_sync(
        self, client: AsyncClient, tracking_prompt: Prompt, seed_models
    ):
        """Test executing a tracking mode prompt synchronously."""
        # Arrange
        payload = {
            "variables": {"var": "test"},
            "model_name": "gpt-4o-mini",
            "mode": "sync",
        }

        # Act
        response = await client.post(
            f"/v1/prompts/{tracking_prompt.name}/execute",
            json=payload,
            headers={"X-API-Key": "test-key"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "execution_id" in data
        assert data.get("prompt_mode") == "tracking"
        assert data.get("status") in ["succeeded", "queued"]

    @pytest.mark.asyncio
    async def test_execute_full_mode_prompt_fails(
        self, client: AsyncClient, full_prompt: Prompt
    ):
        """Test executing full mode prompt via code endpoint fails."""
        # Arrange
        payload = {
            "variables": {"var": "test"},
            "model_name": "gpt-4o-mini",
            "mode": "sync",
        }

        # Act
        response = await client.post(
            f"/v1/prompts/{full_prompt.name}/execute",
            json=payload,
            headers={"X-API-Key": "test-key"},
        )

        # Assert
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "full mode" in detail.lower()
        assert "PUT" in detail  # Should suggest correct endpoint

    @pytest.mark.asyncio
    async def test_execute_nonexistent_prompt_returns_404(self, client: AsyncClient):
        """Test executing non-existent prompt returns 404."""
        # Arrange
        payload = {
            "variables": {"var": "test"},
            "model_name": "gpt-4o-mini",
            "mode": "sync",
        }

        # Act
        response = await client.post(
            "/v1/prompts/nonexistent/execute",
            json=payload,
            headers={"X-API-Key": "test-key"},
        )

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestPromptHistory:
    """Test GET /v1/prompts/{name}/history endpoint."""

    @pytest.mark.asyncio
    async def test_get_tracking_mode_history(
        self, client: AsyncClient, tracking_prompt: Prompt
    ):
        """Test getting history for tracking mode prompt."""
        # Act
        response = await client.get(
            f"/v1/prompts/{tracking_prompt.name}/history?mode=tracking",
            headers={"X-API-Key": "test-key"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["prompt_name"] == tracking_prompt.name
        assert data["mode"] == "tracking"
        assert data["current_version"] == 1
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version"] == 1

    @pytest.mark.asyncio
    async def test_get_full_mode_history(
        self, client: AsyncClient, full_prompt: Prompt
    ):
        """Test getting history for full mode prompt."""
        # Act
        response = await client.get(
            f"/v1/prompts/{full_prompt.name}/history?mode=full",
            headers={"X-API-Key": "test-key"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["prompt_name"] == full_prompt.name
        assert data["mode"] == "full"

    @pytest.mark.asyncio
    async def test_history_includes_execution_counts(
        self, client: AsyncClient, tracking_prompt: Prompt
    ):
        """Test history includes execution counts per version."""
        # Act
        response = await client.get(
            f"/v1/prompts/{tracking_prompt.name}/history",
            headers={"X-API-Key": "test-key"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "execution_count" in data["versions"][0]


@pytest.fixture
async def seed_models(db_session: AsyncSession):
    """Seed database with test models."""
    from prompt_ledger.models.model import Model

    model = Model(
        provider="openai",
        model_name="gpt-4o-mini",
        max_tokens=4096,
        supports_streaming=False,
    )
    db_session.add(model)
    await db_session.commit()
    return model
