"""API v1 module."""

from fastapi import APIRouter, Depends

from prompt_ledger.api.dependencies import verify_api_key

from .endpoints import admin, analytics, code_prompts, executions, prompts, spans

api = APIRouter(dependencies=[Depends(verify_api_key)])

api.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api.include_router(code_prompts.router, prefix="/prompts", tags=["code-prompts"])
api.include_router(executions.router, prefix="/executions", tags=["executions"])
api.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api.include_router(spans.spans_router, prefix="/spans", tags=["spans"])
api.include_router(spans.traces_router, prefix="/traces", tags=["traces"])
api.include_router(admin.router, prefix="/admin", tags=["admin"])
