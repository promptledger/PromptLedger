"""Pytest configuration and fixtures."""

import asyncio

# Test database URL - use postgres service name when in Docker
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from prompt_ledger.api.main import app
from prompt_ledger.db.database import Base, get_db
from prompt_ledger.settings import settings

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:password@postgres:5432/prompt_ledger_test",
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    # Create engine for this test
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
    )

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

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
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
