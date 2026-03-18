"""Unit tests for the DB-backed verify_api_key dependency — Story 2.1."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.project import ApiKey, Project, hash_api_key


class TestVerifyApiKey:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear the auth cache before and after each test."""
        from prompt_ledger.api.dependencies import _key_cache

        _key_cache.clear()
        yield
        _key_cache.clear()

    async def test_valid_key_returns_project_id(self, db_session: AsyncSession):
        from prompt_ledger.api.dependencies import verify_api_key

        project = Project(name="auth-test")
        db_session.add(project)
        await db_session.flush()

        plaintext = "valid-secret-key"
        db_session.add(
            ApiKey(key_hash=hash_api_key(plaintext), project_id=project.project_id)
        )
        await db_session.flush()

        result = await verify_api_key(x_api_key=plaintext, db=db_session)
        assert result == project.project_id

    async def test_unknown_key_raises_401(self, db_session: AsyncSession):
        from prompt_ledger.api.dependencies import verify_api_key

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(x_api_key="totally-unknown-key", db=db_session)
        assert exc_info.value.status_code == 401

    async def test_empty_key_raises_401(self, db_session: AsyncSession):
        from prompt_ledger.api.dependencies import verify_api_key

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(x_api_key="", db=db_session)
        assert exc_info.value.status_code == 401

    async def test_error_detail_does_not_leak_internals(self, db_session: AsyncSession):
        from prompt_ledger.api.dependencies import verify_api_key

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(x_api_key="bad-key", db=db_session)
        assert "Invalid or missing API key" in exc_info.value.detail

    async def test_cache_hit_skips_db_on_second_call(self, db_session: AsyncSession):
        """Second call with the same key must not execute a DB query."""
        from prompt_ledger.api.dependencies import verify_api_key

        project = Project(name="cache-proj")
        db_session.add(project)
        await db_session.flush()

        plaintext = "cacheable-key"
        db_session.add(
            ApiKey(key_hash=hash_api_key(plaintext), project_id=project.project_id)
        )
        await db_session.flush()

        # First call — cache miss, hits DB
        result1 = await verify_api_key(x_api_key=plaintext, db=db_session)
        assert result1 == project.project_id

        # Second call — cache hit, DB must not be called
        with patch.object(db_session, "execute", wraps=db_session.execute) as mock_exec:
            result2 = await verify_api_key(x_api_key=plaintext, db=db_session)
            assert result2 == project.project_id
            mock_exec.assert_not_called()

    async def test_different_projects_different_keys(self, db_session: AsyncSession):
        from prompt_ledger.api.dependencies import verify_api_key

        proj_a = Project(name="proj-a")
        proj_b = Project(name="proj-b")
        db_session.add_all([proj_a, proj_b])
        await db_session.flush()

        db_session.add(
            ApiKey(key_hash=hash_api_key("key-a"), project_id=proj_a.project_id)
        )
        db_session.add(
            ApiKey(key_hash=hash_api_key("key-b"), project_id=proj_b.project_id)
        )
        await db_session.flush()

        result_a = await verify_api_key(x_api_key="key-a", db=db_session)
        result_b = await verify_api_key(x_api_key="key-b", db=db_session)

        assert result_a == proj_a.project_id
        assert result_b == proj_b.project_id
        assert result_a != result_b
