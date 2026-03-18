"""Prompt service for managing prompts across both modes."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum


class PromptService:
    """Service for prompt management operations.

    Handles both full management mode and code-based tracking mode prompts.
    All queries are scoped to the provided project_id.
    """

    def __init__(self, db: AsyncSession, project_id: UUID):
        self.db = db
        self.project_id = project_id

    async def register_code_prompts(
        self, prompts: List[Dict[str, Any]], dry_run: bool = False
    ) -> List[Dict[str, Any]]:
        """Register code-based prompts with automatic versioning.

        Args:
            prompts: List of prompt data dicts with 'name' and 'template_source'.
            dry_run: If True, compute results without writing to the database.

        Returns:
            List of result dicts with 'name', 'action', 'hash_changed',
            'version', 'change_detected', 'previous_version'.
        """
        results = []

        for prompt_data in prompts:
            name = prompt_data["name"]
            template_source = prompt_data["template_source"]
            checksum = compute_checksum(template_source)

            result = await self.db.execute(
                select(Prompt).where(
                    Prompt.name == name, Prompt.project_id == self.project_id
                )
            )
            prompt = result.scalar_one_or_none()

            if not prompt:
                action = "new"
                hash_changed = True
                version_number = 1
                previous_version = None
                change_detected = True

                if not dry_run:
                    prompt = Prompt(
                        name=name, mode="tracking", project_id=self.project_id
                    )
                    self.db.add(prompt)
                    await self.db.flush()

                    version = PromptVersion(
                        prompt_id=prompt.prompt_id,
                        version_number=1,
                        template_source=template_source,
                        checksum_hash=checksum,
                        status="active",
                    )
                    self.db.add(version)
                    await self.db.flush()
                    prompt.active_version_id = version.version_id
                    await self.db.commit()
            else:
                existing_version_result = await self.db.execute(
                    select(PromptVersion).where(
                        PromptVersion.prompt_id == prompt.prompt_id,
                        PromptVersion.checksum_hash == checksum,
                    )
                )
                existing_version = existing_version_result.scalar_one_or_none()

                if existing_version:
                    action = "unchanged"
                    hash_changed = False
                    version_number = existing_version.version_number
                    previous_version = None
                    change_detected = False
                else:
                    action = "update"
                    hash_changed = True
                    change_detected = True

                    max_result = await self.db.execute(
                        select(PromptVersion.version_number)
                        .where(PromptVersion.prompt_id == prompt.prompt_id)
                        .order_by(PromptVersion.version_number.desc())
                        .limit(1)
                    )
                    max_version = max_result.scalar_one_or_none()
                    previous_version = max_version
                    version_number = (max_version or 0) + 1

                    if not dry_run:
                        new_version = PromptVersion(
                            prompt_id=prompt.prompt_id,
                            version_number=version_number,
                            template_source=template_source,
                            checksum_hash=checksum,
                            status="active",
                        )
                        self.db.add(new_version)
                        await self.db.flush()
                        prompt.active_version_id = new_version.version_id
                        await self.db.commit()

            results.append(
                {
                    "name": name,
                    "action": action,
                    "hash_changed": hash_changed,
                    "version": version_number,
                    "change_detected": change_detected,
                    "previous_version": previous_version,
                }
            )

        return results

    async def validate_mode(
        self, prompt_name: str, expected_mode: str, operation: str
    ) -> Prompt:
        """Validate prompt mode matches expected mode, scoped to project.

        Raises:
            HTTPException(404): If prompt not found in this project's namespace.
            HTTPException(400): If prompt mode doesn't match expected mode.
        """
        result = await self.db.execute(
            select(Prompt).where(
                Prompt.name == prompt_name, Prompt.project_id == self.project_id
            )
        )
        prompt = result.scalar_one_or_none()

        if not prompt:
            raise HTTPException(
                status_code=404, detail=f"Prompt '{prompt_name}' not found"
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

    async def get_prompt_by_name(self, prompt_name: str) -> Optional[Prompt]:
        """Get prompt by name within this project's namespace."""
        result = await self.db.execute(
            select(Prompt).where(
                Prompt.name == prompt_name, Prompt.project_id == self.project_id
            )
        )
        return result.scalar_one_or_none()
