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
    """

    def __init__(self, db: AsyncSession):
        """Initialize service with database session.

        Args:
            db: Async database session
        """
        self.db = db

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

            result = await self.db.execute(select(Prompt).where(Prompt.name == name))
            prompt = result.scalar_one_or_none()

            if not prompt:
                action = "new"
                hash_changed = True
                version_number = 1
                previous_version = None
                change_detected = True

                if not dry_run:
                    prompt = Prompt(name=name, mode="tracking")
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
        """Validate prompt mode matches expected mode.

        Enforces mode isolation by ensuring operations are performed on
        prompts of the correct mode. Raises appropriate HTTP exceptions
        with helpful error messages.

        Args:
            prompt_name: Name of the prompt to validate
            expected_mode: Expected mode ('full' or 'tracking')
            operation: Description of operation for error message

        Returns:
            The validated prompt object

        Raises:
            HTTPException(404): If prompt not found
            HTTPException(400): If prompt mode doesn't match expected mode

        Example:
            >>> service = PromptService(db)
            >>> prompt = await service.validate_mode(
            ...     "my_prompt", "tracking", "execute operation"
            ... )
            >>> # If prompt is in 'full' mode, raises:
            >>> # HTTPException(400, detail="Prompt 'my_prompt' is in full mode...")
        """
        result = await self.db.execute(select(Prompt).where(Prompt.name == prompt_name))
        prompt = result.scalar_one_or_none()

        if not prompt:
            raise HTTPException(
                status_code=404, detail=f"Prompt '{prompt_name}' not found"
            )

        if prompt.mode != expected_mode:
            if expected_mode == "full":
                # Trying to use full mode endpoint on tracking mode prompt
                error_msg = (
                    f"Prompt '{prompt_name}' is in {prompt.mode} mode. "
                    f"Use code-based endpoints instead."
                )
            else:
                # Trying to use tracking mode endpoint on full mode prompt
                error_msg = (
                    f"Prompt '{prompt_name}' is in {prompt.mode} mode. "
                    f"Use PUT /v1/prompts/{prompt_name} instead."
                )

            raise HTTPException(status_code=400, detail=error_msg)

        return prompt

    async def get_prompt_by_name(self, prompt_name: str) -> Optional[Prompt]:
        """Get prompt by name without mode validation.

        Utility method for retrieving prompts without enforcing mode checks.

        Args:
            prompt_name: Name of the prompt

        Returns:
            Prompt object if found, None otherwise
        """
        result = await self.db.execute(select(Prompt).where(Prompt.name == prompt_name))
        return result.scalar_one_or_none()
