"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from prompt_ledger.api.main import app
from prompt_ledger.db.database import Base, get_db
from prompt_ledger.settings import settings

# Test database URL
TEST_DATABASE_URL = (
    "postgresql+asyncpg://postgres:password@localhost:5432/prompt_ledger_test"
)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

TestSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


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
