from fastapi import APIRouter, Depends, Query

from auth.dependencies import require_permissions
from auth.models import UserContext
from .dependencies import get_audit_service
from .schemas import AuditLogResponse


router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit"])


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    context: UserContext = Depends(require_permissions("audit:read")),
    service=Depends(get_audit_service),
):
    return await service.list(context, limit)
