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
        self, prompts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Register code-based prompts with automatic versioning.

        This method implements automatic version detection based on template
        content checksums. If the template hasn't changed, the existing version
        is returned. If changed, a new version is created with an incremented
        version number.

        Args:
            prompts: List of prompt data dictionaries containing:
                - name: Prompt identifier (str)
                - template_source: Jinja2 template (str)
                - template_hash: SHA256 hash of template (str, optional)

        Returns:
            List of registration result dictionaries containing:
                - name: Prompt name
                - mode: Always 'tracking'
                - version: Version number
                - change_detected: True if new version created
                - previous_version: Previous version number (if change detected)

        Example:
            >>> service = PromptService(db)
            >>> results = await service.register_code_prompts([
            ...     {"name": "WELCOME", "template_source": "Hello {{name}}!"}
            ... ])
            >>> print(results[0])
            {'name': 'WELCOME', 'mode': 'tracking', 'version': 1,
             'change_detected': False, 'previous_version': None}
        """
        results = []

        for prompt_data in prompts:
            name = prompt_data["name"]
            template_source = prompt_data["template_source"]
            checksum = compute_checksum(template_source)

            # Find or create prompt
            result = await self.db.execute(select(Prompt).where(Prompt.name == name))
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
                    status="active",
                )
                self.db.add(version)
                await self.db.flush()

                # Set as active version
                prompt.active_version_id = version.version_id

            else:
                # Prompt exists - check if checksum already exists
                result = await self.db.execute(
                    select(PromptVersion).where(
                        PromptVersion.prompt_id == prompt.prompt_id,
                        PromptVersion.checksum_hash == checksum,
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
                        status="active",
                    )
                    self.db.add(version)
                    await self.db.flush()

                    # Update active version
                    prompt.active_version_id = version.version_id
                    change_detected = True

            await self.db.commit()

            results.append(
                {
                    "name": name,
                    "mode": "tracking",
                    "version": version.version_number,
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
