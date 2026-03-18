"""Integration tests for DB-backed API key authentication — Story 2.1."""

import pytest
from httpx import AsyncClient


class TestAuthUpgrade:
    async def test_seeded_env_key_authenticates(self, client: AsyncClient):
        """The env var key seeded at startup resolves to the default project."""
        resp = await client.get("/v1/prompts", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200

    async def test_unknown_key_returns_401(self, client: AsyncClient):
        resp = await client.get("/v1/prompts", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    async def test_missing_key_returns_401(self, client: AsyncClient):
        resp = await client.get("/v1/prompts")
        assert resp.status_code == 401

    async def test_health_bypasses_auth(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_wrong_key_after_valid_request_still_401(self, client: AsyncClient):
        """Cache must not let a bad key ride on a prior good key's cache entry."""
        await client.get("/v1/prompts", headers={"X-API-Key": "test-key"})
        resp = await client.get("/v1/prompts", headers={"X-API-Key": "not-test-key"})
        assert resp.status_code == 401

    async def test_all_v1_endpoints_require_key(self, client: AsyncClient):
        """Spot-check that auth is applied across routers, not just prompts."""
        endpoints = [
            "/v1/prompts",
            "/v1/analytics/prompts",
        ]
        for endpoint in endpoints:
            resp = await client.get(endpoint)
            assert resp.status_code == 401, f"{endpoint} should require auth"
