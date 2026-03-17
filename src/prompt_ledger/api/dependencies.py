"""Shared FastAPI dependencies."""

import secrets

from fastapi import Header, HTTPException, status

from prompt_ledger.settings import settings


async def verify_api_key(x_api_key: str = Header(default="")) -> None:
    """Enforce X-API-Key authentication on every protected endpoint.

    Uses secrets.compare_digest() for constant-time comparison to prevent
    timing-based key enumeration attacks.
    """
    if not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
