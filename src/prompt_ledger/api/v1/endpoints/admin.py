"""Admin API endpoints for project and API key management — Story 2.4."""

import secrets
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.api.dependencies import _key_cache, require_admin_key
from prompt_ledger.db.database import get_db
from prompt_ledger.models.project import ApiKey, Project, hash_api_key

router = APIRouter(dependencies=[Depends(require_admin_key)])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str
    key_label: str = "default"


class IssueKeyRequest(BaseModel):
    label: str = "api-key"


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


def _generate_plaintext_key() -> str:
    """Generate a cryptographically secure API key prefixed with 'pl-'."""
    return "pl-" + secrets.token_urlsafe(48)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=List[Dict[str, Any]])
async def list_projects(
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all projects. Never returns key material."""
    result = await db.execute(select(Project).order_by(Project.created_at))
    projects = result.scalars().all()
    return [
        {
            "project_id": str(p.project_id),
            "name": p.name,
            "created_at": p.created_at.isoformat(),
        }
        for p in projects
    ]


@router.get("/projects/{project_id}/keys", response_model=List[Dict[str, Any]])
async def list_project_keys(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List key metadata for a project. Never returns plaintext or hashes."""
    result = await db.execute(select(Project).where(Project.project_id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.project_id == project_id)
        .order_by(ApiKey.created_at)
    )
    keys = result.scalars().all()
    return [
        {
            "key_id": str(k.key_id),
            "label": k.label,
            "created_at": k.created_at.isoformat(),
            "is_system_key": k.is_system_key,
        }
        for k in keys
    ]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create a named project and issue its first API key.

    The plaintext key is returned exactly once and never stored.
    """
    existing = await db.execute(select(Project).where(Project.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project '{body.name}' already exists",
        )

    project = Project(name=body.name)
    db.add(project)
    await db.flush()

    plaintext = _generate_plaintext_key()
    key = ApiKey(
        key_hash=hash_api_key(plaintext),
        project_id=project.project_id,
        label=body.key_label,
        is_system_key=False,
    )
    db.add(key)
    await db.flush()
    await db.commit()

    return {
        "project_id": str(project.project_id),
        "name": project.name,
        "api_key": plaintext,
        "key_id": str(key.key_id),
    }


@router.post("/projects/{project_id}/keys", status_code=status.HTTP_201_CREATED)
async def issue_additional_key(
    project_id: UUID,
    body: IssueKeyRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Issue an additional API key for an existing project (key loss recovery).

    The plaintext key is returned exactly once and never stored.
    Old keys remain valid until explicitly revoked.
    """
    result = await db.execute(select(Project).where(Project.project_id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    plaintext = _generate_plaintext_key()
    key = ApiKey(
        key_hash=hash_api_key(plaintext),
        project_id=project_id,
        label=body.label,
        is_system_key=False,
    )
    db.add(key)
    await db.flush()
    await db.commit()

    return {
        "api_key": plaintext,
        "key_id": str(key.key_id),
    }


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke an API key. System keys (seeded env-var keys) cannot be deleted.

    Cache invalidation is immediate — the revoked key stops authenticating
    within the current request.
    """
    result = await db.execute(select(ApiKey).where(ApiKey.key_id == key_id))
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
        )

    if key.is_system_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "System keys cannot be deleted. To rotate the env-var key, "
                "update API_KEY in the environment and restart the service."
            ),
        )

    key_hash = key.key_hash
    await db.delete(key)
    await db.commit()

    # Invalidate the cache entry immediately so the revoked key stops working.
    _key_cache.pop(key_hash, None)
