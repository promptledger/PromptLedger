"""Shared FastAPI dependencies."""

from uuid import UUID

from cachetools import TTLCache
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.db.database import get_db
from prompt_ledger.models.project import ApiKey, hash_api_key

# In-memory cache: key_hash → project_id, TTL=60s.
# Avoids a DB round-trip on every authenticated request.
# Cache entries are explicitly invalidated when a key is revoked (Story 2.4).
_key_cache: TTLCache = TTLCache(maxsize=1000, ttl=60)


async def verify_api_key(
    x_api_key: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """Authenticate via DB-backed API key; return the resolved project_id.

    Uses secrets.compare_digest semantics implicitly — the lookup is by hash,
    so the comparison is a DB equality check on the stored SHA-256 hash, not
    a string comparison of plaintext keys.

    FastAPI deduplicates dependency calls per request, so declaring this both
    at the router level (for auth enforcement) and on individual endpoints
    (to receive project_id) results in exactly one DB/cache call per request.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    key_hash = hash_api_key(x_api_key)

    if key_hash in _key_cache:
        return _key_cache[key_hash]

    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key_row = result.scalar_one_or_none()

    if api_key_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    project_id: UUID = api_key_row.project_id
    _key_cache[key_hash] = project_id
    return project_id
