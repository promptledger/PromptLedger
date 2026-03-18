"""Project and API key management — Story 2.1."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.project import ApiKey, Project, hash_api_key


async def seed_default_api_key(db: AsyncSession, plaintext_key: str) -> None:
    """Ensure the default project and its seeded API key exist.

    Idempotent — safe to call on every startup. Creates the 'default' project
    if absent, then upserts the env-var key as a system key for that project.
    The system key cannot be deleted via the admin API (Story 2.4).
    """
    # Get or create the default project
    result = await db.execute(select(Project).where(Project.name == "default"))
    project = result.scalar_one_or_none()

    if project is None:
        project = Project(name="default")
        db.add(project)
        await db.flush()

    # Upsert the env-var key as a system key
    key_hash = hash_api_key(plaintext_key)
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    existing_key = result.scalar_one_or_none()

    if existing_key is None:
        db.add(
            ApiKey(
                key_hash=key_hash,
                project_id=project.project_id,
                label="legacy env var key",
                is_system_key=True,
            )
        )
        await db.flush()

    await db.commit()
