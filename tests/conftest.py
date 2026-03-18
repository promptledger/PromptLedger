"""Pytest configuration and fixtures."""

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from prompt_ledger.api.main import app
from prompt_ledger.db.database import Base, get_db
from prompt_ledger.settings import settings


@pytest.fixture(scope="session")
def postgres_container():
    """Start a real Postgres container once per test session.

    Falls back gracefully in two situations:
    - TEST_DATABASE_URL is set (CI / make docker-up): use that URL directly.
    - Docker is not reachable (Docker Desktop not running): skip DB tests with a
      clear message rather than erroring with an obscure socket error.
    """
    if os.getenv("TEST_DATABASE_URL"):
        yield None
        return

    try:
        from testcontainers.postgres import PostgresContainer

        pg = PostgresContainer("postgres:15", driver="asyncpg")
        pg.start()
    except Exception:
        pytest.skip(
            "Docker not available — start Docker Desktop or set TEST_DATABASE_URL "
            "to run database tests"
        )
        return

    yield pg
    pg.stop()


@pytest_asyncio.fixture(scope="function")
async def db_session(postgres_container) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    if postgres_container is not None:
        db_url = postgres_container.get_connection_url()
    else:
        db_url = os.environ["TEST_DATABASE_URL"]

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database override."""
    from httpx import ASGITransport

    from prompt_ledger.api.dependencies import _key_cache
    from prompt_ledger.models.project import ApiKey, Project, hash_api_key
    from prompt_ledger.settings import settings

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Pin settings.api_key for the test session so tests can use a known value.
    original_key = settings.api_key
    settings.api_key = "test-key"

    # Clear auth cache to prevent inter-test pollution.
    _key_cache.clear()

    # Seed the default project and test key into the test DB.
    # The lifespan seeding uses the app's own DB connection (not db_session),
    # so we must seed manually here for auth to work in tests.
    default_project = Project(name="default")
    db_session.add(default_project)
    await db_session.flush()
    db_session.add(
        ApiKey(
            key_hash=hash_api_key("test-key"),
            project_id=default_project.project_id,
            label="test env var key",
            is_system_key=True,
        )
    )
    await db_session.flush()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    settings.api_key = original_key
    app.dependency_overrides.clear()
    _key_cache.clear()


@pytest.fixture
def sample_prompt_data():
    """Sample prompt data for testing."""
    return {
        "description": "Test prompt for summarization",
        "owner_team": "AI-Platform",
        "template_source": "Summarize the following text:\n{{text}}",
        "created_by": "test_user",
        "set_active": True,
    }


@pytest.fixture
def sample_execution_request():
    """Sample execution request for testing."""
    return {
        "prompt_name": "test_summarizer",
        "environment": "test",
        "variables": {"text": "This is a test document to summarize."},
        "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
        "params": {"max_new_tokens": 100, "temperature": 0.1},
    }
