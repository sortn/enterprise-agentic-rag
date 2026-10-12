from fastapi import APIRouter, Depends

from auth.dependencies import require_permissions
from auth.models import UserContext
from .dependencies import get_knowledge_base_service
from .schemas import KnowledgeBaseCreate, KnowledgeBaseGrant, KnowledgeBaseResponse


router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["Knowledge Bases"])


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    context: UserContext = Depends(require_permissions("knowledge_bases:read")),
    service=Depends(get_knowledge_base_service),
):
    return await service.list(context)


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    context: UserContext = Depends(require_permissions("knowledge_bases:write")),
    service=Depends(get_knowledge_base_service),
):
    return await service.create(context, payload.name, payload.description)


@router.post("/{knowledge_base_id}/members", response_model=dict)
async def grant_knowledge_base_access(
    knowledge_base_id: str,
    payload: KnowledgeBaseGrant,
    context: UserContext = Depends(require_permissions("knowledge_bases:write")),
    service=Depends(get_knowledge_base_service),
):
    return await service.grant(
        context, knowledge_base_id, payload.user_id, payload.access_level
    )
