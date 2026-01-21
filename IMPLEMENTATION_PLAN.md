# Implementation Plan: Dual-Mode Prompt Management

**Feature:** Code-Based Prompt Tracking Mode
**Date:** 2026-01-19
**Approach:** Test-Driven Development (TDD) - Red-Green-Refactor

---

## Overview

This document outlines all code changes required to implement the dual-mode prompt management feature. Changes are organized by layer with TDD approach.

**Dual Modes:**
1. **Full Management Mode** (existing) - Database-first, dynamic updates
2. **Code-Based Tracking Mode** (new) - Git-first, version control integration

---

## 1. Database Layer Changes

### 1.1 Create New Migration

**File:** `alembic/versions/002_add_prompt_mode.py`

**Purpose:** Add `mode` field to prompts table

```python
"""Add mode field to prompts table

Revision ID: 002
Revises: 001
Create Date: 2026-01-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create prompt_mode enum
    op.execute("CREATE TYPE prompt_mode AS ENUM ('full', 'tracking')")

    # Add mode column to prompts table
    op.add_column('prompts',
        sa.Column('mode', sa.Enum('full', 'tracking', name='prompt_mode'),
                  nullable=False, server_default='full')
    )

    # Create index for mode-based queries
    op.create_index('idx_prompts_mode', 'prompts', ['mode'])


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_prompts_mode', table_name='prompts')

    # Drop column
    op.drop_column('prompts', 'mode')

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS prompt_mode")
```

### 1.2 Update Models

**File:** `src/prompt_ledger/models/prompt.py`

**Changes:**

```python
# ADD after imports:
from sqlalchemy import Enum

# ADD to Prompt class (line ~38, after owner_team):
    mode = Column(
        Enum('full', 'tracking', name='prompt_mode'),
        nullable=False,
        server_default='full'
    )
```

**TDD: Write test first**

**File:** `tests/unit/test_models_prompt_mode.py` (NEW FILE)

```python
"""Test prompt mode functionality."""

import pytest
from sqlalchemy import select
from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum


class TestPromptMode:
    """Test prompt mode field and operations."""

    async def test_prompt_defaults_to_full_mode(self, db_session):
        """Test that new prompts default to 'full' mode."""
        # Arrange & Act
        prompt = Prompt(name="test_prompt", description="Test")
        db_session.add(prompt)
        await db_session.commit()

        # Assert
        result = await db_session.execute(
            select(Prompt).where(Prompt.name == "test_prompt")
        )
        saved_prompt = result.scalar_one()
        assert saved_prompt.mode == 'full'

    async def test_prompt_can_be_created_with_tracking_mode(self, db_session):
        """Test creating prompt in tracking mode."""
        # Arrange & Act
        prompt = Prompt(name="code_prompt", mode="tracking")
        db_session.add(prompt)
        await db_session.commit()

        # Assert
        result = await db_session.execute(
            select(Prompt).where(Prompt.name == "code_prompt")
        )
        saved_prompt = result.scalar_one()
        assert saved_prompt.mode == 'tracking'

    async def test_mode_index_exists(self, db_session):
        """Test that mode index exists for query optimization."""
        # This test verifies the migration created the index
        # Query information_schema to check index existence
        from sqlalchemy import text

        result = await db_session.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'prompts' AND indexname = 'idx_prompts_mode'"
        ))
        index = result.scalar_one_or_none()
        assert index == 'idx_prompts_mode'
```

---

## 2. Services Layer Changes

### 2.1 Create New Prompt Service for Code-Based Operations

**File:** `src/prompt_ledger/services/prompt_service.py` (NEW FILE)

**Purpose:** Handle prompt registration and versioning for both modes

**TDD: Write tests first**

**File:** `tests/unit/test_prompt_service.py` (NEW FILE)

```python
"""Test prompt service functionality."""

import pytest
from prompt_ledger.services.prompt_service import PromptService
from prompt_ledger.models.prompt import Prompt, PromptVersion


class TestPromptServiceCodeBased:
    """Test code-based prompt registration."""

    async def test_register_new_code_prompt(self, db_session):
        """Test registering a new code-based prompt."""
        # Arrange
        service = PromptService(db_session)
        prompts_data = [{
            "name": "WELCOME",
            "template_source": "Hello {{name}}!",
            "template_hash": "abc123..."
        }]

        # Act
        result = await service.register_code_prompts(prompts_data)

        # Assert
        assert len(result) == 1
        assert result[0]["name"] == "WELCOME"
        assert result[0]["mode"] == "tracking"
        assert result[0]["version"] == 1
        assert result[0]["change_detected"] == False  # First registration

    async def test_register_unchanged_prompt_no_new_version(self, db_session):
        """Test re-registering unchanged prompt doesn't create new version."""
        # Arrange
        service = PromptService(db_session)
        template = "Hello {{name}}!"
        prompts_data = [{
            "name": "WELCOME",
            "template_source": template,
            "template_hash": compute_checksum(template)
        }]

        # Act - Register twice
        result1 = await service.register_code_prompts(prompts_data)
        result2 = await service.register_code_prompts(prompts_data)

        # Assert
        assert result1[0]["version"] == 1
        assert result2[0]["version"] == 1  # Same version
        assert result2[0]["change_detected"] == False

    async def test_register_changed_prompt_creates_new_version(self, db_session):
        """Test changing template content creates new version."""
        # Arrange
        service = PromptService(db_session)
        template_v1 = "Hello {{name}}!"
        template_v2 = "Hi {{name}}, welcome!"

        # Act - Register, then update
        result1 = await service.register_code_prompts([{
            "name": "WELCOME",
            "template_source": template_v1,
            "template_hash": compute_checksum(template_v1)
        }])

        result2 = await service.register_code_prompts([{
            "name": "WELCOME",
            "template_source": template_v2,
            "template_hash": compute_checksum(template_v2)
        }])

        # Assert
        assert result1[0]["version"] == 1
        assert result2[0]["version"] == 2
        assert result2[0]["change_detected"] == True
        assert result2[0]["previous_version"] == 1


class TestModeValidation:
    """Test mode validation logic."""

    async def test_validate_full_mode_prompt(self, db_session):
        """Test validating full mode prompt."""
        # Arrange
        service = PromptService(db_session)
        prompt = Prompt(name="full_prompt", mode="full")
        db_session.add(prompt)
        await db_session.commit()

        # Act & Assert
        await service.validate_mode("full_prompt", "full", "PUT operation")
        # Should not raise

    async def test_validate_mode_mismatch_raises_error(self, db_session):
        """Test mode mismatch raises HTTPException."""
        # Arrange
        service = PromptService(db_session)
        prompt = Prompt(name="tracking_prompt", mode="tracking")
        db_session.add(prompt)
        await db_session.commit()

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.validate_mode("tracking_prompt", "full", "PUT operation")

        assert exc_info.value.status_code == 400
        assert "tracking" in exc_info.value.detail.lower()
```

**Implementation:**

```python
"""Prompt service for managing prompts across both modes."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum


class PromptService:
    """Service for prompt management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_code_prompts(
        self, prompts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Register code-based prompts with automatic versioning.

        Args:
            prompts: List of prompt data with name, template_source, template_hash

        Returns:
            List of registration results with version info and change detection
        """
        results = []

        for prompt_data in prompts:
            name = prompt_data["name"]
            template_source = prompt_data["template_source"]
            checksum = compute_checksum(template_source)

            # Find or create prompt
            result = await self.db.execute(
                select(Prompt).where(Prompt.name == name)
            )
            prompt = result.scalar_one_or_none()

            previous_version = None
            change_detected = False

            if not prompt:
                # Create new prompt in tracking mode
                prompt = Prompt(name=name, mode="tracking")
                self.db.add(prompt)
                await self.db.flush()

                # Create version 1
                version = PromptVersion(
                    prompt_id=prompt.prompt_id,
                    version_number=1,
                    template_source=template_source,
                    checksum_hash=checksum,
                    status="active"
                )
                self.db.add(version)
                await self.db.flush()

                # Set as active
                prompt.active_version_id = version.version_id

            else:
                # Check if checksum already exists
                result = await self.db.execute(
                    select(PromptVersion).where(
                        PromptVersion.prompt_id == prompt.prompt_id,
                        PromptVersion.checksum_hash == checksum
                    )
                )
                existing_version = result.scalar_one_or_none()

                if existing_version:
                    # Content unchanged - return existing version
                    version = existing_version
                else:
                    # Content changed - create new version
                    result = await self.db.execute(
                        select(PromptVersion.version_number)
                        .where(PromptVersion.prompt_id == prompt.prompt_id)
                        .order_by(PromptVersion.version_number.desc())
                        .limit(1)
                    )
                    max_version = result.scalar_one_or_none()
                    previous_version = max_version
                    next_version = (max_version or 0) + 1

                    version = PromptVersion(
                        prompt_id=prompt.prompt_id,
                        version_number=next_version,
                        template_source=template_source,
                        checksum_hash=checksum,
                        status="active"
                    )
                    self.db.add(version)
                    await self.db.flush()

                    # Update active version
                    prompt.active_version_id = version.version_id
                    change_detected = True

            await self.db.commit()

            results.append({
                "name": name,
                "mode": "tracking",
                "version": version.version_number,
                "change_detected": change_detected,
                "previous_version": previous_version
            })

        return results

    async def validate_mode(
        self, prompt_name: str, expected_mode: str, operation: str
    ) -> Prompt:
        """Validate prompt mode matches expected mode.

        Args:
            prompt_name: Name of the prompt
            expected_mode: Expected mode ('full' or 'tracking')
            operation: Description of operation for error message

        Returns:
            The validated prompt

        Raises:
            HTTPException: If prompt not found or mode mismatch
        """
        result = await self.db.execute(
            select(Prompt).where(Prompt.name == prompt_name)
        )
        prompt = result.scalar_one_or_none()

        if not prompt:
            raise HTTPException(
                status_code=404,
                detail=f"Prompt '{prompt_name}' not found"
            )

        if prompt.mode != expected_mode:
            if expected_mode == "full":
                error_msg = (
                    f"Prompt '{prompt_name}' is in {prompt.mode} mode. "
                    f"Use code-based endpoints instead."
                )
            else:
                error_msg = (
                    f"Prompt '{prompt_name}' is in {prompt.mode} mode. "
                    f"Use PUT /v1/prompts/{prompt_name} instead."
                )

            raise HTTPException(status_code=400, detail=error_msg)

        return prompt
```

---

## 3. API Endpoints Layer Changes

### 3.1 Update Existing Prompt Endpoints

**File:** `src/prompt_ledger/api/v1/endpoints/prompts.py`

**Changes:**

```python
# ADD import at top:
from prompt_ledger.services.prompt_service import PromptService

# MODIFY upsert_prompt to validate mode:
@router.put("/{name}", response_model=Dict[str, Any])
async def upsert_prompt(
    name: str,
    prompt_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create or update a prompt in full management mode."""

    # ADD mode validation:
    service = PromptService(db)

    # Check if prompt exists and validate mode
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    existing_prompt = result.scalar_one_or_none()

    if existing_prompt:
        # Validate it's in full mode
        await service.validate_mode(name, "full", "PUT operation")

    # ... rest of existing implementation ...

    # When creating NEW prompt, ensure mode='full':
    if not prompt:
        prompt = Prompt(
            name=name,
            description=description,
            owner_team=owner_team,
            mode='full'  # ADD THIS
        )
```

### 3.2 Create New Code-Based Endpoints

**File:** `src/prompt_ledger/api/v1/endpoints/code_prompts.py` (NEW FILE)

**TDD: Write tests first**

**File:** `tests/integration/test_code_prompts_api.py` (NEW FILE)

```python
"""Integration tests for code-based prompt endpoints."""

import pytest
from httpx import AsyncClient
from prompt_ledger.models.prompt import compute_checksum


class TestRegisterCodePrompts:
    """Test POST /v1/prompts/register-code endpoint."""

    async def test_register_new_code_prompts(self, client: AsyncClient):
        """Test registering new code-based prompts."""
        # Arrange
        payload = {
            "prompts": [
                {
                    "name": "WELCOME",
                    "template_source": "Hello {{name}}!",
                    "template_hash": compute_checksum("Hello {{name}}!")
                }
            ]
        }

        # Act
        response = await client.post("/v1/prompts/register-code", json=payload)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["registered"]) == 1
        assert data["registered"][0]["name"] == "WELCOME"
        assert data["registered"][0]["mode"] == "tracking"
        assert data["registered"][0]["version"] == 1

    async def test_register_detects_content_changes(self, client: AsyncClient):
        """Test change detection on re-registration."""
        # Arrange
        template_v1 = "Hello {{name}}!"
        template_v2 = "Hi {{name}}!"

        # Act - Register twice with different content
        await client.post("/v1/prompts/register-code", json={
            "prompts": [{"name": "WELCOME", "template_source": template_v1,
                        "template_hash": compute_checksum(template_v1)}]
        })

        response = await client.post("/v1/prompts/register-code", json={
            "prompts": [{"name": "WELCOME", "template_source": template_v2,
                        "template_hash": compute_checksum(template_v2)}]
        })

        # Assert
        data = response.json()
        assert data["registered"][0]["version"] == 2
        assert data["registered"][0]["change_detected"] == True


class TestExecuteCodePrompt:
    """Test POST /v1/prompts/{name}/execute endpoint."""

    async def test_execute_tracking_mode_prompt(
        self, client: AsyncClient, tracking_prompt
    ):
        """Test executing a tracking mode prompt."""
        # Arrange
        payload = {
            "variables": {"name": "John"},
            "model_name": "gpt-4o-mini",
            "mode": "sync"
        }

        # Act
        response = await client.post(
            f"/v1/prompts/{tracking_prompt.name}/execute",
            json=payload
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "execution_id" in data
        assert data["prompt_mode"] == "tracking"

    async def test_execute_full_mode_prompt_fails(
        self, client: AsyncClient, full_prompt
    ):
        """Test executing full mode prompt via code endpoint fails."""
        # Arrange
        payload = {
            "variables": {"name": "John"},
            "model_name": "gpt-4o-mini",
            "mode": "sync"
        }

        # Act
        response = await client.post(
            f"/v1/prompts/{full_prompt.name}/execute",
            json=payload
        )

        # Assert
        assert response.status_code == 400
        assert "full mode" in response.json()["detail"].lower()


class TestUnifiedAnalytics:
    """Test GET /v1/analytics/prompts endpoint."""

    async def test_analytics_returns_both_modes(
        self, client: AsyncClient, full_prompt, tracking_prompt
    ):
        """Test analytics aggregates both modes."""
        # Act
        response = await client.get("/v1/analytics/prompts?mode=all")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "by_mode" in data
        assert "full" in data["by_mode"]
        assert "tracking" in data["by_mode"]
```

**Implementation:**

```python
"""Code-based prompt management endpoints."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.db.database import get_db
from prompt_ledger.services.prompt_service import PromptService
from prompt_ledger.services.execution import ExecutionService

router = APIRouter()


@router.post("/register-code", response_model=Dict[str, Any])
async def register_code_prompts(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Register code-based prompts with automatic versioning.

    Request format:
    {
        "prompts": [
            {
                "name": "WELCOME",
                "template_source": "Hello {{name}}!",
                "template_hash": "abc123..."
            }
        ]
    }
    """
    service = PromptService(db)
    prompts = request.get("prompts", [])

    if not prompts:
        raise HTTPException(status_code=400, detail="No prompts provided")

    results = await service.register_code_prompts(prompts)

    return {"registered": results}


@router.post("/{name}/execute", response_model=Dict[str, Any])
async def execute_code_prompt(
    name: str,
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Execute a code-based (tracking mode) prompt.

    Request format:
    {
        "variables": {"name": "John"},
        "version": null,  // optional
        "model_name": "gpt-4o-mini",
        "mode": "sync"  // or "async"
    }
    """
    # Validate prompt is in tracking mode
    prompt_service = PromptService(db)
    await prompt_service.validate_mode(name, "tracking", "execute operation")

    # Build execution request
    execution_request = {
        "prompt_name": name,
        "version_number": request.get("version"),
        "variables": request.get("variables", {}),
        "model": {
            "provider": "openai",
            "model_name": request.get("model_name", "gpt-4o-mini")
        },
        "params": request.get("params", {}),
        "environment": request.get("environment", "dev")
    }

    # Execute based on mode
    execution_service = ExecutionService(db)
    mode = request.get("mode", "sync")

    if mode == "sync":
        result = await execution_service.execute_sync(execution_request)
    else:
        result = await execution_service.submit_async(execution_request)

    result["prompt_mode"] = "tracking"
    return result


@router.get("/{name}/history", response_model=Dict[str, Any])
async def get_prompt_history(
    name: str,
    mode: str = "full",
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get prompt version history (works for both modes)."""
    from sqlalchemy import select, func
    from prompt_ledger.models.prompt import Prompt, PromptVersion
    from prompt_ledger.models.execution import Execution

    # Find prompt
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Get versions with execution counts
    result = await db.execute(
        select(
            PromptVersion,
            func.count(Execution.execution_id).label("execution_count")
        )
        .outerjoin(Execution, Execution.version_id == PromptVersion.version_id)
        .where(PromptVersion.prompt_id == prompt.prompt_id)
        .group_by(PromptVersion.version_id)
        .order_by(PromptVersion.version_number.desc())
    )
    versions_data = result.all()

    versions = []
    for version, exec_count in versions_data:
        versions.append({
            "version": version.version_number,
            "template_hash": version.checksum_hash,
            "template_source": version.template_source,
            "created_at": version.created_at.isoformat(),
            "execution_count": exec_count
        })

    return {
        "prompt_name": name,
        "mode": prompt.mode,
        "current_version": versions[0]["version"] if versions else None,
        "versions": versions
    }
```

### 3.3 Create Analytics Endpoint

**File:** `src/prompt_ledger/api/v1/endpoints/analytics.py` (NEW FILE)

```python
"""Analytics endpoints for unified reporting."""

from typing import Any, Dict
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.db.database import get_db
from prompt_ledger.models.prompt import Prompt
from prompt_ledger.models.execution import Execution

router = APIRouter()


@router.get("/prompts", response_model=Dict[str, Any])
async def get_prompts_analytics(
    mode: str = Query("all", regex="^(all|full|tracking)$"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get unified analytics across both prompt modes."""

    # Total execution count
    if mode == "all":
        total_result = await db.execute(select(func.count(Execution.execution_id)))
        total_executions = total_result.scalar()

        # Count by mode
        full_count_result = await db.execute(
            select(func.count(Prompt.prompt_id))
            .where(Prompt.mode == "full")
        )
        full_prompts = full_count_result.scalar()

        tracking_count_result = await db.execute(
            select(func.count(Prompt.prompt_id))
            .where(Prompt.mode == "tracking")
        )
        tracking_prompts = tracking_count_result.scalar()

        # Execution stats by mode
        full_exec_result = await db.execute(
            select(
                func.count(Execution.execution_id).label("count"),
                func.avg(Execution.latency_ms).label("avg_latency")
            )
            .join(Prompt, Prompt.prompt_id == Execution.prompt_id)
            .where(Prompt.mode == "full")
        )
        full_stats = full_exec_result.first()

        tracking_exec_result = await db.execute(
            select(
                func.count(Execution.execution_id).label("count"),
                func.avg(Execution.latency_ms).label("avg_latency")
            )
            .join(Prompt, Prompt.prompt_id == Execution.prompt_id)
            .where(Prompt.mode == "tracking")
        )
        tracking_stats = tracking_exec_result.first()

        return {
            "summary": {
                "total_executions": total_executions,
                "full_mode_prompts": full_prompts,
                "tracking_mode_prompts": tracking_prompts
            },
            "by_mode": {
                "full": {
                    "execution_count": full_stats.count or 0,
                    "avg_latency_ms": int(full_stats.avg_latency or 0)
                },
                "tracking": {
                    "execution_count": tracking_stats.count or 0,
                    "avg_latency_ms": int(tracking_stats.avg_latency or 0)
                }
            }
        }
    else:
        # Mode-specific analytics
        # ... implementation for specific mode filtering
        pass
```

### 3.4 Update API Router

**File:** `src/prompt_ledger/api/v1/__init__.py`

```python
# ADD import:
from .endpoints import code_prompts, analytics

# ADD routes:
api.include_router(code_prompts.router, prefix="/prompts", tags=["code-prompts"])
api.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
```

---

## 4. Workers Layer Changes

### 4.1 Worker Updates

**File:** `src/prompt_ledger/workers/tasks.py`

**Changes:** Workers DON'T need changes! They work with both modes since:
- Execution table is unified
- Workers just process execution_id
- Mode is transparent to workers

**Verification Test:**

**File:** `tests/integration/test_worker_mode_agnostic.py` (NEW FILE)

```python
"""Test that workers handle both modes identically."""

import pytest


class TestWorkerModeAgnostic:
    """Verify workers work with both prompt modes."""

    async def test_worker_executes_full_mode_prompt(self, db_session, full_prompt):
        """Test worker executes full mode prompt."""
        # ... create execution for full mode prompt
        # ... worker processes it
        # ... verify success
        pass

    async def test_worker_executes_tracking_mode_prompt(
        self, db_session, tracking_prompt
    ):
        """Test worker executes tracking mode prompt."""
        # ... create execution for tracking mode prompt
        # ... worker processes it
        # ... verify success
        pass

    async def test_worker_retry_logic_same_for_both_modes(self):
        """Test retry logic doesn't depend on prompt mode."""
        # ... verify retry behavior identical
        pass
```

---

## 5. Services Layer Additional Changes

### 5.1 Update Execution Service

**File:** `src/prompt_ledger/services/execution.py`

**Changes:** Add mode validation in resolve context

```python
# MODIFY _resolve_execution_context method:
async def _resolve_execution_context(
    self, request: Dict[str, Any]
) -> tuple[Prompt, PromptVersion, Model]:
    """Resolve prompt, version, and model from request."""

    # ... existing code ...

    # ADD: Optionally validate mode if specified in request
    expected_mode = request.get("expected_mode")
    if expected_mode and prompt.mode != expected_mode:
        raise ValueError(
            f"Prompt '{prompt.name}' is in {prompt.mode} mode, "
            f"expected {expected_mode}"
        )

    # ... rest of existing code ...
```

---

## 6. Testing Strategy (TDD Order)

### Phase 1: Database & Models (Red-Green-Refactor)

1. Write test: `test_prompt_defaults_to_full_mode` → ❌ FAIL
2. Create migration `002_add_prompt_mode.py`
3. Run migration → ✅ PASS
4. Write test: `test_prompt_can_be_created_with_tracking_mode` → ❌ FAIL
5. Update `Prompt` model with `mode` field → ✅ PASS
6. Write test: `test_mode_index_exists` → ❌ FAIL
7. Verify index in migration → ✅ PASS

### Phase 2: Services (Red-Green-Refactor)

1. Write test: `test_register_new_code_prompt` → ❌ FAIL
2. Create `PromptService` class skeleton → ❌ FAIL (not implemented)
3. Implement `register_code_prompts()` → ✅ PASS
4. Write test: `test_register_unchanged_prompt_no_new_version` → ❌ FAIL
5. Add checksum comparison logic → ✅ PASS
6. Write test: `test_register_changed_prompt_creates_new_version` → ❌ FAIL
7. Add version increment logic → ✅ PASS
8. Write test: `test_validate_mode_mismatch_raises_error` → ❌ FAIL
9. Implement `validate_mode()` → ✅ PASS

### Phase 3: API Endpoints (Red-Green-Refactor)

1. Write test: `test_register_new_code_prompts` → ❌ FAIL
2. Create `code_prompts.py` router → ❌ FAIL
3. Implement `register_code_prompts` endpoint → ✅ PASS
4. Write test: `test_execute_tracking_mode_prompt` → ❌ FAIL
5. Implement `execute_code_prompt` endpoint → ✅ PASS
6. Write test: `test_execute_full_mode_prompt_fails` → ❌ FAIL
7. Add mode validation to endpoint → ✅ PASS
8. Write test: `test_analytics_returns_both_modes` → ❌ FAIL
9. Implement analytics endpoint → ✅ PASS

### Phase 4: Integration Tests

1. Write end-to-end test for full code-based workflow
2. Write mixed-mode test (both modes in same system)
3. Write performance test (mode index effectiveness)

---

## 7. Configuration Changes

### 7.1 Update Settings (if needed)

**File:** `src/prompt_ledger/settings.py`

No changes needed - modes are data-driven.

---

## 8. Documentation Updates

### 8.1 API Documentation

Update FastAPI OpenAPI docs with new endpoints:
- POST /v1/prompts/register-code
- POST /v1/prompts/{name}/execute
- GET /v1/prompts/{name}/history
- GET /v1/analytics/prompts

### 8.2 README Examples

Already updated by user.

---

## 9. Summary of Files Changed/Created

### Modified Files:
1. `src/prompt_ledger/models/prompt.py` - Add mode field
2. `src/prompt_ledger/api/v1/endpoints/prompts.py` - Add mode validation
3. `src/prompt_ledger/api/v1/__init__.py` - Register new routers
4. `src/prompt_ledger/services/execution.py` - Optional mode validation

### New Files:
1. `alembic/versions/002_add_prompt_mode.py` - Migration
2. `src/prompt_ledger/services/prompt_service.py` - Prompt service
3. `src/prompt_ledger/api/v1/endpoints/code_prompts.py` - Code endpoints
4. `src/prompt_ledger/api/v1/endpoints/analytics.py` - Analytics
5. `tests/unit/test_models_prompt_mode.py` - Model tests
6. `tests/unit/test_prompt_service.py` - Service tests
7. `tests/integration/test_code_prompts_api.py` - API tests
8. `tests/integration/test_worker_mode_agnostic.py` - Worker tests

### No Changes Needed:
- Workers (mode-agnostic by design)
- Models (execution.py, model.py)
- Provider adapters
- Celery configuration

---

## 10. Development Workflow

```bash
# 1. Create migration
alembic revision -m "Add prompt mode field"
# Edit migration file with changes from Section 1.1

# 2. Run migration
alembic upgrade head

# 3. TDD Cycle for each component:
# a. Write test (RED)
pytest tests/unit/test_models_prompt_mode.py::test_prompt_defaults_to_full_mode

# b. Implement (GREEN)
# Edit src/prompt_ledger/models/prompt.py

# c. Verify (GREEN)
pytest tests/unit/test_models_prompt_mode.py::test_prompt_defaults_to_full_mode

# d. Refactor if needed

# 4. Repeat for all components following order in Section 6

# 5. Run full test suite
pytest

# 6. Check coverage
pytest --cov=src/prompt_ledger --cov-report=html

# 7. Format and lint
black src/ tests/
isort src/ tests/
mypy src/
flake8 src/
```

---

## 11. Rollback Plan

If implementation needs to be rolled back:

```bash
# Rollback database
alembic downgrade -1

# Revert code changes
git revert <commit-hash>

# Or for complete rollback:
git reset --hard <commit-before-changes>
```

---

## ✅ Checklist

Before marking implementation complete:

- [ ] Migration created and tested
- [ ] All models updated with mode field
- [ ] All model tests passing
- [ ] PromptService created with full test coverage
- [ ] All service tests passing
- [ ] Code-based API endpoints created
- [ ] All API integration tests passing
- [ ] Analytics endpoint working
- [ ] Mode validation enforced everywhere
- [ ] Worker tests verify mode-agnostic behavior
- [ ] Full test suite passing (≥90% coverage)
- [ ] Code formatted (black, isort)
- [ ] Type checking passing (mypy)
- [ ] Linting passing (flake8)
- [ ] Documentation updated
- [ ] Manual testing completed for both modes
- [ ] Performance verified (mode index effective)

---

**Remember: TDD is mandatory. Every single change must follow Red-Green-Refactor.**
