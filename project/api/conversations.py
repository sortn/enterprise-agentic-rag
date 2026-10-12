from fastapi import APIRouter, Depends

from auth.dependencies import require_permissions
from auth.models import UserContext
from .dependencies import get_conversation_service
from .schemas import ConversationDetail, ConversationResponse


router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    context: UserContext = Depends(require_permissions("conversations:read")),
    service=Depends(get_conversation_service),
):
    return await service.list(context)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    context: UserContext = Depends(require_permissions("conversations:read")),
    service=Depends(get_conversation_service),
):
    return await service.detail(context, conversation_id)
