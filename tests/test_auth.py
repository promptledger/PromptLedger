"""Tests for API key authentication — Story 1.0.

TDD: write these tests first, confirm RED, then implement.
"""

import pytest
from httpx import AsyncClient

VALID_KEY = "test-key"
WRONG_KEY = "wrong-key"

# A representative endpoint from each router to confirm blanket coverage.
PROTECTED_ENDPOINTS = [
    ("GET", "/v1/prompts/any-prompt"),
    ("GET", "/v1/analytics/prompts"),
]


class TestApiKeyAuth:
    """Authentication enforcement tests."""

    @pytest.mark.parametrize("method,url", PROTECTED_ENDPOINTS)
    async def test_missing_key_returns_401(
        self, client: AsyncClient, method: str, url: str
    ):
        response = await client.request(method, url)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API key"

    @pytest.mark.parametrize("method,url", PROTECTED_ENDPOINTS)
    async def test_wrong_key_returns_401(
        self, client: AsyncClient, method: str, url: str
    ):
        response = await client.request(method, url, headers={"X-API-Key": WRONG_KEY})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API key"

    async def test_correct_key_does_not_return_401(self, client: AsyncClient):
        """Correct key passes auth (endpoint may still 404 — that's fine)."""
        response = await client.get(
            "/v1/prompts/nonexistent", headers={"X-API-Key": VALID_KEY}
        )
        assert response.status_code != 401

    async def test_health_exempt_from_auth(self, client: AsyncClient):
        """/health must return 200 with no API key."""
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_constant_time_comparison_used(self):
        """Structural test: verify_api_key must use secrets.compare_digest."""
        import inspect
        import secrets

        from prompt_ledger.api.dependencies import verify_api_key

        source = inspect.getsource(verify_api_key)
        assert (
            "secrets.compare_digest" in source
        ), "verify_api_key must use secrets.compare_digest(), not =="
