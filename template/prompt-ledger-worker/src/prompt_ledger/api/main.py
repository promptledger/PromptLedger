"""FastAPI application main entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from ..db.database import init_db
from ..settings import settings
from .v1 import api as v1_api


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    await init_db()
    yield
    # Shutdown
    pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Prompt Registry, Execution & Lineage Service",
    lifespan=lifespan,
    proxy_headers=True,  # Enable proxy header support for Railway/cloud deployments
    forwarded_allow_ips="*",  # Trust all proxy IPs (Railway handles this)
)

# Trusted host middleware for proxy support (Railway, etc.)
# This ensures the app correctly handles X-Forwarded-* headers
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,
)

# CORS middleware
# In production, configure allow_origins to match your frontend domain(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(v1_api, prefix="/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
