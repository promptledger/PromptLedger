"""Story 1.3 — register-code dry-run and change detection tests.

TDD: confirm RED before implementing.
"""

import pytest
from httpx import AsyncClient

HEADERS = {"X-API-Key": "test-key"}


class TestRegisterCodeDryRun:
    """dry_run=true must compute results without writing to the database."""

    async def test_dry_run_new_prompt_returns_action_new(self, client: AsyncClient):
        response = await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={
                "prompts": [{"name": "dry.new", "template_source": "Hello {{name}}"}],
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        detail = next(d for d in data["details"] if d["name"] == "dry.new")
        assert detail["action"] == "new"
        assert detail["hash_changed"] is True

    async def test_dry_run_new_prompt_creates_no_db_row(self, client: AsyncClient):
        await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={
                "prompts": [{"name": "dry.ghost", "template_source": "Ghost {{x}}"}],
                "dry_run": True,
            },
        )
        # Prompt must not exist after dry run
        response = await client.get("/v1/prompts/dry.ghost", headers=HEADERS)
        assert response.status_code == 404

    async def test_dry_run_unchanged_prompt_returns_action_unchanged(
        self, client: AsyncClient
    ):
        # Register for real first
        await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={"prompts": [{"name": "dry.stable", "template_source": "Hi {{x}}"}]},
        )
        # Dry run with same content
        response = await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={
                "prompts": [{"name": "dry.stable", "template_source": "Hi {{x}}"}],
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        detail = next(d for d in data["details"] if d["name"] == "dry.stable")
        assert detail["action"] == "unchanged"
        assert detail["hash_changed"] is False

    async def test_dry_run_changed_prompt_returns_action_update_no_write(
        self, client: AsyncClient
    ):
        # Register v1
        await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={"prompts": [{"name": "dry.change", "template_source": "Old {{x}}"}]},
        )
        # Dry run with new content
        response = await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={
                "prompts": [{"name": "dry.change", "template_source": "New {{x}}"}],
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        detail = next(d for d in data["details"] if d["name"] == "dry.change")
        assert detail["action"] == "update"
        assert detail["hash_changed"] is True

        # Verify no new version was written
        versions = await client.get("/v1/prompts/dry.change/versions", headers=HEADERS)
        assert len(versions.json()) == 1

    async def test_live_run_changed_prompt_returns_action_update_and_writes(
        self, client: AsyncClient
    ):
        await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={"prompts": [{"name": "live.change", "template_source": "Old {{x}}"}]},
        )
        response = await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={
                "prompts": [{"name": "live.change", "template_source": "New {{x}}"}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        detail = next(d for d in data["details"] if d["name"] == "live.change")
        assert detail["action"] == "update"
        assert detail["hash_changed"] is True

        versions = await client.get("/v1/prompts/live.change/versions", headers=HEADERS)
        assert len(versions.json()) == 2

    async def test_counts_sum_to_total(self, client: AsyncClient):
        response = await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={
                "prompts": [
                    {"name": "count.a", "template_source": "A {{x}}"},
                    {"name": "count.b", "template_source": "B {{x}}"},
                    {"name": "count.c", "template_source": "C {{x}}"},
                ],
            },
        )
        data = response.json()
        total = (
            data.get("registered", 0)
            + data.get("updated", 0)
            + data.get("unchanged", 0)
        )
        assert total == 3

    async def test_response_includes_details_without_dry_run(self, client: AsyncClient):
        """Live runs also return the details array (enables CI diff reporting)."""
        response = await client.post(
            "/v1/prompts/register-code",
            headers=HEADERS,
            json={"prompts": [{"name": "ci.prompt", "template_source": "CI {{x}}"}]},
        )
        data = response.json()
        assert "details" in data
        assert data["details"][0]["name"] == "ci.prompt"
        assert data["details"][0]["action"] in ("new", "update", "unchanged")
