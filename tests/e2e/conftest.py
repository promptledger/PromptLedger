"""E2E test fixtures — hits the live Railway deployment.

Required env vars:
    PROMPTLEDGER_URL      e.g. https://prompt-ledger-api-production.up.railway.app
    PROMPTLEDGER_API_KEY  your API key

Run with:
    pytest tests/e2e/ -v
    pytest tests/e2e/ -v --tb=short   # less noise on failure
"""

import os

import pytest
from promptledger_client import AsyncPromptLedgerClient


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: live end-to-end tests against Railway")


@pytest.fixture(scope="session")
def base_url() -> str:
    url = os.getenv("PROMPTLEDGER_URL", "").rstrip("/")
    if not url:
        pytest.skip("PROMPTLEDGER_URL not set — export it before running e2e tests")
    return url


@pytest.fixture(scope="session")
def api_key() -> str:
    key = os.getenv("PROMPTLEDGER_API_KEY", "")
    if not key:
        pytest.skip("PROMPTLEDGER_API_KEY not set — export it before running e2e tests")
    return key


@pytest.fixture(scope="session")
async def client(base_url: str, api_key: str) -> AsyncPromptLedgerClient:
    """Shared SDK client for the whole e2e session."""
    async with AsyncPromptLedgerClient(
        base_url=base_url, api_key=api_key, timeout=30.0
    ) as c:
        yield c
