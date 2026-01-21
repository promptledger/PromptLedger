"""API v1 module."""

from fastapi import APIRouter

from .endpoints import analytics, code_prompts, executions, prompts

api = APIRouter()

api.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api.include_router(code_prompts.router, prefix="/prompts", tags=["code-prompts"])
api.include_router(executions.router, prefix="/executions", tags=["executions"])
api.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
