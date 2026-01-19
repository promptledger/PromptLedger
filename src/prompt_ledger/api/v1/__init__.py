"""API v1 module."""

from fastapi import APIRouter

from .endpoints import prompts, executions

api = APIRouter()

api.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api.include_router(executions.router, prefix="/executions", tags=["executions"])
