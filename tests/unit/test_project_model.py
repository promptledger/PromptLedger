"""Unit tests for Project and ApiKey ORM models — Story 2.1."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.project import ApiKey, Project, hash_api_key


class TestProjectModel:
    async def test_create_project(self, db_session: AsyncSession):
        project = Project(name="srf")
        db_session.add(project)
        await db_session.flush()

        assert project.project_id is not None
        assert project.name == "srf"
        assert project.created_at is not None

    async def test_project_name_unique(self, db_session: AsyncSession):
        db_session.add(Project(name="duplicate"))
        await db_session.flush()

        db_session.add(Project(name="duplicate"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_default_project_creatable(self, db_session: AsyncSession):
        project = Project(name="default")
        db_session.add(project)
        await db_session.flush()
        assert project.name == "default"


class TestApiKeyModel:
    async def test_create_api_key(self, db_session: AsyncSession):
        project = Project(name="test-project")
        db_session.add(project)
        await db_session.flush()

        key = ApiKey(
            key_hash="abc123hash",
            project_id=project.project_id,
            label="test-key",
        )
        db_session.add(key)
        await db_session.flush()

        assert key.key_id is not None
        assert key.key_hash == "abc123hash"
        assert key.project_id == project.project_id
        assert key.label == "test-key"
        assert key.is_system_key is False
        assert key.created_at is not None

    async def test_is_system_key_defaults_false(self, db_session: AsyncSession):
        project = Project(name="p1")
        db_session.add(project)
        await db_session.flush()

        key = ApiKey(key_hash="h1", project_id=project.project_id)
        db_session.add(key)
        await db_session.flush()

        assert key.is_system_key is False

    async def test_system_key_flag_can_be_set(self, db_session: AsyncSession):
        project = Project(name="default")
        db_session.add(project)
        await db_session.flush()

        key = ApiKey(
            key_hash="systemhash",
            project_id=project.project_id,
            label="legacy env var key",
            is_system_key=True,
        )
        db_session.add(key)
        await db_session.flush()

        assert key.is_system_key is True

    async def test_key_hash_unique(self, db_session: AsyncSession):
        project = Project(name="p2")
        db_session.add(project)
        await db_session.flush()

        db_session.add(ApiKey(key_hash="same_hash", project_id=project.project_id))
        await db_session.flush()

        db_session.add(ApiKey(key_hash="same_hash", project_id=project.project_id))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_project_relationship_loads(self, db_session: AsyncSession):
        project = Project(name="rel-test")
        db_session.add(project)
        await db_session.flush()

        key = ApiKey(key_hash="relhash", project_id=project.project_id)
        db_session.add(key)
        await db_session.flush()
        await db_session.refresh(key, ["project"])

        assert key.project.name == "rel-test"

    async def test_project_has_multiple_keys(self, db_session: AsyncSession):
        project = Project(name="multi-key")
        db_session.add(project)
        await db_session.flush()

        db_session.add(
            ApiKey(key_hash="hash-a", project_id=project.project_id, label="prod")
        )
        db_session.add(
            ApiKey(key_hash="hash-b", project_id=project.project_id, label="staging")
        )
        await db_session.flush()
        await db_session.refresh(project, ["api_keys"])

        assert len(project.api_keys) == 2


class TestHashApiKey:
    def test_returns_hex_string(self):
        result = hash_api_key("my-key")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_input_same_output(self):
        assert hash_api_key("key") == hash_api_key("key")

    def test_different_inputs_different_outputs(self):
        assert hash_api_key("key-a") != hash_api_key("key-b")
