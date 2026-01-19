"""Tests for prompt management endpoints."""

import pytest
from httpx import AsyncClient


class TestPrompts:
    """Test prompt CRUD operations."""
    
    async def test_create_prompt(self, client: AsyncClient, sample_prompt_data):
        """Test creating a new prompt."""
        response = await client.put(
            "/v1/prompts/test_summarizer",
            json=sample_prompt_data,
            headers={"X-API-Key": "test-key"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "prompt" in data
        assert "version" in data
        assert data["version_change"] is True
        assert data["prompt"]["name"] == "test_summarizer"
        assert data["version"]["version_number"] == 1
    
    async def test_update_prompt_same_content(
        self, client: AsyncClient, sample_prompt_data
    ):
        """Test updating prompt with same content (no new version)."""
        # Create initial prompt
        await client.put(
            "/v1/prompts/test_summarizer",
            json=sample_prompt_data,
            headers={"X-API-Key": "test-key"},
        )
        
        # Update with same content
        response = await client.put(
            "/v1/prompts/test_summarizer",
            json=sample_prompt_data,
            headers={"X-API-Key": "test-key"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["version_change"] is False
    
    async def test_update_prompt_new_content(
        self, client: AsyncClient, sample_prompt_data
    ):
        """Test updating prompt with new content (new version)."""
        # Create initial prompt
        await client.put(
            "/v1/prompts/test_summarizer",
            json=sample_prompt_data,
            headers={"X-API-Key": "test-key"},
        )
        
        # Update with new content
        new_data = sample_prompt_data.copy()
        new_data["template_source"] = "New template: {{text}}"
        
        response = await client.put(
            "/v1/prompts/test_summarizer",
            json=new_data,
            headers={"X-API-Key": "test-key"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["version_change"] is True
        assert data["version"]["version_number"] == 2
    
    async def test_get_prompt(self, client: AsyncClient, sample_prompt_data):
        """Test retrieving a prompt."""
        # Create prompt first
        await client.put(
            "/v1/prompts/test_summarizer",
            json=sample_prompt_data,
            headers={"X-API-Key": "test-key"},
        )
        
        # Get prompt
        response = await client.get(
            "/v1/prompts/test_summarizer",
            headers={"X-API-Key": "test-key"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "test_summarizer"
        assert data["description"] == sample_prompt_data["description"]
        assert "active_version" in data
        assert data["active_version"]["template_source"] == sample_prompt_data["template_source"]
    
    async def test_get_nonexistent_prompt(self, client: AsyncClient):
        """Test retrieving a non-existent prompt."""
        response = await client.get(
            "/v1/prompts/nonexistent",
            headers={"X-API-Key": "test-key"},
        )
        
        assert response.status_code == 404
    
    async def test_list_prompt_versions(self, client: AsyncClient, sample_prompt_data):
        """Test listing prompt versions."""
        # Create prompt
        await client.put(
            "/v1/prompts/test_summarizer",
            json=sample_prompt_data,
            headers={"X-API-Key": "test-key"},
        )
        
        # Create second version
        new_data = sample_prompt_data.copy()
        new_data["template_source"] = "Version 2: {{text}}"
        await client.put(
            "/v1/prompts/test_summarizer",
            json=new_data,
            headers={"X-API-Key": "test-key"},
        )
        
        # List versions
        response = await client.get(
            "/v1/prompts/test_summarizer/versions",
            headers={"X-API-Key": "test-key"},
        )
        
        assert response.status_code == 200
        versions = response.json()
        assert len(versions) == 2
        assert versions[0]["version_number"] == 2  # Most recent first
        assert versions[1]["version_number"] == 1
