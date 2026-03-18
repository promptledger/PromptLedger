"""Integration tests for admin API endpoints — Story 2.4."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.api.dependencies import _key_cache
from prompt_ledger.models.project import ApiKey, Project, hash_api_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _add_project_with_key(
    db_session: AsyncSession, project_name: str, plaintext_key: str
) -> Project:
    """Seed a non-default project and key directly into db_session."""
    project = Project(name=project_name)
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        ApiKey(
            key_hash=hash_api_key(plaintext_key),
            project_id=project.project_id,
            label=f"{project_name}-key",
        )
    )
    await db_session.flush()
    _key_cache.clear()
    return project


# ---------------------------------------------------------------------------
# GET /v1/admin/projects
# ---------------------------------------------------------------------------


class TestListProjects:
    async def test_non_default_key_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A key from a non-default project must be rejected with 403."""
        await _add_project_with_key(db_session, "other-proj", "other-key")

        resp = await client.get(
            "/v1/admin/projects", headers={"X-API-Key": "other-key"}
        )
        assert resp.status_code == 403

    async def test_unknown_key_returns_401(self, client: AsyncClient):
        """No valid key → 401 (from verify_api_key, before admin check)."""
        resp = await client.get(
            "/v1/admin/projects", headers={"X-API-Key": "not-a-key"}
        )
        assert resp.status_code == 401

    async def test_returns_all_projects_with_required_fields(
        self, client: AsyncClient
    ):
        """Response contains project_id, name, created_at for each project."""
        resp = await client.get(
            "/v1/admin/projects", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        projects = resp.json()
        assert isinstance(projects, list)
        assert len(projects) >= 1

        for proj in projects:
            assert "project_id" in proj
            assert "name" in proj
            assert "created_at" in proj

    async def test_response_contains_no_key_material(self, client: AsyncClient):
        """Response must never expose key hashes or plaintext."""
        resp = await client.get(
            "/v1/admin/projects", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        for proj in resp.json():
            assert "key_hash" not in proj
            assert "api_key" not in proj

    async def test_default_project_present(self, client: AsyncClient):
        """The 'default' project must always appear in the list."""
        resp = await client.get(
            "/v1/admin/projects", headers={"X-API-Key": "test-key"}
        )
        names = [p["name"] for p in resp.json()]
        assert "default" in names


# ---------------------------------------------------------------------------
# GET /v1/admin/projects/{project_id}/keys
# ---------------------------------------------------------------------------


class TestListProjectKeys:
    async def test_returns_key_metadata_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Response contains key_id, label, created_at, is_system_key — no secrets."""
        project = await _add_project_with_key(db_session, "kp-proj", "kp-key")

        resp = await client.get(
            f"/v1/admin/projects/{project.project_id}/keys",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        keys = resp.json()
        assert isinstance(keys, list)
        assert len(keys) >= 1

        for k in keys:
            assert "key_id" in k
            assert "label" in k
            assert "created_at" in k
            assert "is_system_key" in k

    async def test_response_contains_no_plaintext_or_hash(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """key_hash and api_key must never appear in the keys list response."""
        project = await _add_project_with_key(db_session, "no-secret-proj", "ns-key")

        resp = await client.get(
            f"/v1/admin/projects/{project.project_id}/keys",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        for k in resp.json():
            assert "key_hash" not in k
            assert "api_key" not in k

    async def test_unknown_project_returns_404(self, client: AsyncClient):
        """Requesting keys for a project that doesn't exist → 404."""
        import uuid

        resp = await client.get(
            f"/v1/admin/projects/{uuid.uuid4()}/keys",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 404

    async def test_non_default_key_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Non-admin key cannot list keys even for its own project."""
        project = await _add_project_with_key(
            db_session, "forbidden-proj", "forbidden-key"
        )

        resp = await client.get(
            f"/v1/admin/projects/{project.project_id}/keys",
            headers={"X-API-Key": "forbidden-key"},
        )
        assert resp.status_code == 403

    async def test_system_key_is_flagged(self, client: AsyncClient, db_session: AsyncSession):
        """The seeded env-var key appears with is_system_key=true."""
        # Find the default project_id
        resp_projects = await client.get(
            "/v1/admin/projects", headers={"X-API-Key": "test-key"}
        )
        default_proj = next(
            p for p in resp_projects.json() if p["name"] == "default"
        )

        resp = await client.get(
            f"/v1/admin/projects/{default_proj['project_id']}/keys",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        system_keys = [k for k in resp.json() if k["is_system_key"]]
        assert len(system_keys) >= 1


# ---------------------------------------------------------------------------
# POST /v1/admin/projects
# ---------------------------------------------------------------------------


class TestCreateProject:
    async def test_non_default_key_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await _add_project_with_key(db_session, "cp-other", "cp-other-key")

        resp = await client.post(
            "/v1/admin/projects",
            json={"name": "new-project", "key_label": "prod"},
            headers={"X-API-Key": "cp-other-key"},
        )
        assert resp.status_code == 403

    async def test_create_project_returns_project_id_and_plaintext_key(
        self, client: AsyncClient
    ):
        """Response must include project_id, name, api_key, key_id."""
        resp = await client.post(
            "/v1/admin/projects",
            json={"name": "brand-new-proj", "key_label": "prod"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "project_id" in data
        assert data["name"] == "brand-new-proj"
        assert "api_key" in data
        assert "key_id" in data
        assert data["api_key"].startswith("pl-")

    async def test_returned_key_authenticates(self, client: AsyncClient):
        """The plaintext key from POST /v1/admin/projects must work immediately."""
        resp = await client.post(
            "/v1/admin/projects",
            json={"name": "auth-check-proj"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201
        new_key = resp.json()["api_key"]

        resp2 = await client.get(
            "/v1/prompts", headers={"X-API-Key": new_key}
        )
        assert resp2.status_code == 200

    async def test_duplicate_project_name_returns_409(self, client: AsyncClient):
        """Creating two projects with the same name must fail with 409."""
        await client.post(
            "/v1/admin/projects",
            json={"name": "dup-proj"},
            headers={"X-API-Key": "test-key"},
        )
        resp = await client.post(
            "/v1/admin/projects",
            json={"name": "dup-proj"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 409

    async def test_key_not_retrievable_after_creation(self, client: AsyncClient):
        """The plaintext key is returned once; subsequent listing only shows metadata."""
        create_resp = await client.post(
            "/v1/admin/projects",
            json={"name": "one-time-key-proj"},
            headers={"X-API-Key": "test-key"},
        )
        assert create_resp.status_code == 201
        data = create_resp.json()
        project_id = data["project_id"]

        keys_resp = await client.get(
            f"/v1/admin/projects/{project_id}/keys",
            headers={"X-API-Key": "test-key"},
        )
        assert keys_resp.status_code == 200
        for k in keys_resp.json():
            assert "api_key" not in k
            assert "key_hash" not in k


# ---------------------------------------------------------------------------
# POST /v1/admin/projects/{project_id}/keys  (key loss recovery)
# ---------------------------------------------------------------------------


class TestIssueAdditionalKey:
    async def test_issues_new_valid_key(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Issuing a replacement key returns a working plaintext key."""
        project = await _add_project_with_key(
            db_session, "recovery-proj", "original-key"
        )

        resp = await client.post(
            f"/v1/admin/projects/{project.project_id}/keys",
            json={"label": "replacement"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "api_key" in data
        assert "key_id" in data
        assert data["api_key"].startswith("pl-")

        # New key must authenticate
        resp2 = await client.get(
            "/v1/prompts", headers={"X-API-Key": data["api_key"]}
        )
        assert resp2.status_code == 200

    async def test_old_key_still_works_before_revocation(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Old key remains valid until explicitly revoked."""
        project = await _add_project_with_key(
            db_session, "overlap-proj", "overlap-old-key"
        )

        await client.post(
            f"/v1/admin/projects/{project.project_id}/keys",
            json={"label": "overlap-new"},
            headers={"X-API-Key": "test-key"},
        )

        resp = await client.get(
            "/v1/prompts", headers={"X-API-Key": "overlap-old-key"}
        )
        assert resp.status_code == 200

    async def test_unknown_project_returns_404(self, client: AsyncClient):
        import uuid

        resp = await client.post(
            f"/v1/admin/projects/{uuid.uuid4()}/keys",
            json={"label": "ghost"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 404

    async def test_non_default_key_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        project = await _add_project_with_key(
            db_session, "iak-proj", "iak-key"
        )

        resp = await client.post(
            f"/v1/admin/projects/{project.project_id}/keys",
            json={"label": "sneaky"},
            headers={"X-API-Key": "iak-key"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /v1/admin/keys/{key_id}
# ---------------------------------------------------------------------------


class TestRevokeKey:
    async def test_revoked_key_returns_401(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """After revocation, requests with that key return 401."""
        project = await _add_project_with_key(
            db_session, "revoke-proj", "to-revoke-key"
        )

        # Find the key_id for "to-revoke-key"
        from sqlalchemy import select
        result = await db_session.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key("to-revoke-key"))
        )
        key_row = result.scalar_one()

        resp = await client.delete(
            f"/v1/admin/keys/{key_row.key_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 204

        resp2 = await client.get(
            "/v1/prompts", headers={"X-API-Key": "to-revoke-key"}
        )
        assert resp2.status_code == 401

    async def test_system_key_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Attempting to delete the seeded system key must return 409 Conflict."""
        from sqlalchemy import select
        result = await db_session.execute(
            select(ApiKey).where(ApiKey.is_system_key.is_(True))
        )
        system_key = result.scalar_one()

        resp = await client.delete(
            f"/v1/admin/keys/{system_key.key_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 409

    async def test_unknown_key_id_returns_404(self, client: AsyncClient):
        import uuid

        resp = await client.delete(
            f"/v1/admin/keys/{uuid.uuid4()}",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 404

    async def test_non_default_key_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        project = await _add_project_with_key(
            db_session, "del-proj", "del-key"
        )
        from sqlalchemy import select
        result = await db_session.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key("del-key"))
        )
        key_row = result.scalar_one()

        resp = await client.delete(
            f"/v1/admin/keys/{key_row.key_id}",
            headers={"X-API-Key": "del-key"},
        )
        assert resp.status_code == 403
