from fastapi import APIRouter, Depends, Query

from auth.dependencies import require_permissions
from auth.models import UserContext
from .dependencies import get_evaluation_service


router = APIRouter(prefix="/api/v1/evaluation", tags=["Evaluation"])


@router.get("/runs", response_model=list[dict])
async def list_agent_runs(
    limit: int = Query(default=100, ge=1, le=500),
    context: UserContext = Depends(require_permissions("audit:read")),
    service=Depends(get_evaluation_service),
):
    return await service.runs(context, limit)
