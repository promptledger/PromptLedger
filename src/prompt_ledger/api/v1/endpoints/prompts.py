"""Prompt management endpoints."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.db.database import get_db
from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum
from prompt_ledger.settings import settings

router = APIRouter()


async def verify_api_key(api_key: str = Depends(lambda: None)) -> None:
    """Verify API key authentication."""
    # In a real implementation, you'd extract this from headers
    # For now, we'll implement a simple check
    pass


@router.put("/{name}", response_model=Dict[str, Any])
async def upsert_prompt(
    name: str,
    prompt_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create or update a prompt."""

    # Extract fields from request
    template_source = prompt_data.get("template_source", "")
    description = prompt_data.get("description")
    owner_team = prompt_data.get("owner_team")
    created_by = prompt_data.get("created_by")
    set_active = prompt_data.get("set_active", False)

    # Compute checksum
    checksum = compute_checksum(template_source)

    # Find or create prompt
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()

    if not prompt:
        # Create new prompt
        prompt = Prompt(
            name=name,
            description=description,
            owner_team=owner_team,
        )
        db.add(prompt)
        await db.flush()

    # Check if version already exists
    result = await db.execute(
        select(PromptVersion).where(
            PromptVersion.prompt_id == prompt.prompt_id,
            PromptVersion.checksum_hash == checksum,
        )
    )
    existing_version = result.scalar_one_or_none()

    version_change = False
    if existing_version:
        version = existing_version
    else:
        # Get next version number
        result = await db.execute(
            select(PromptVersion.version_number)
            .where(PromptVersion.prompt_id == prompt.prompt_id)
            .order_by(PromptVersion.version_number.desc())
            .limit(1)
        )
        max_version = result.scalar_one_or_none()
        next_version = (max_version or 0) + 1

        # Create new version
        version = PromptVersion(
            prompt_id=prompt.prompt_id,
            version_number=next_version,
            template_source=template_source,
            checksum_hash=checksum,
            created_by=created_by,
            status="active" if set_active else "draft",
        )
        db.add(version)
        version_change = True
        await db.flush()

    # Set as active version if requested
    if set_active:
        prompt.active_version_id = version.version_id
        version.status = "active"

    await db.commit()

    return {
        "prompt": {
            "prompt_id": str(prompt.prompt_id),
            "name": prompt.name,
        },
        "version": {
            "version_id": str(version.version_id),
            "version_number": version.version_number,
        },
        "version_change": version_change,
    }


@router.get("/{name}/versions", response_model=List[Dict[str, Any]])
async def list_prompt_versions(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all versions of a prompt."""

    # Find prompt
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Get versions
    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.prompt_id == prompt.prompt_id)
        .order_by(PromptVersion.version_number.desc())
    )
    versions = result.scalars().all()

    return [
        {
            "version_id": str(version.version_id),
            "version_number": version.version_number,
            "status": version.status,
            "checksum_hash": version.checksum_hash,
            "created_by": version.created_by,
            "created_at": version.created_at.isoformat(),
        }
        for version in versions
    ]


@router.get("/{name}", response_model=Dict[str, Any])
async def get_prompt(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get prompt details."""

    # Find prompt with active version
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    response = {
        "prompt_id": str(prompt.prompt_id),
        "name": prompt.name,
        "description": prompt.description,
        "owner_team": prompt.owner_team,
        "created_at": prompt.created_at.isoformat(),
        "updated_at": prompt.updated_at.isoformat(),
    }

    # Include active version if exists
    if prompt.active_version_id:
        result = await db.execute(
            select(PromptVersion).where(
                PromptVersion.version_id == prompt.active_version_id
            )
        )
        active_version = result.scalar_one_or_none()
        if active_version:
            response["active_version"] = {
                "version_id": str(active_version.version_id),
                "version_number": active_version.version_number,
                "template_source": active_version.template_source,
                "status": active_version.status,
            }

    return response
