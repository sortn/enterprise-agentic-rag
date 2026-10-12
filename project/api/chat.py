from fastapi import APIRouter, Depends

from auth.dependencies import require_permissions
from auth.models import UserContext
from .dependencies import get_chat_service
from .schemas import ChatRequest, ChatResponse


router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    context: UserContext = Depends(require_permissions("agent:execute")),
    service=Depends(get_chat_service),
):
    return await service.chat(
        context=context,
        question=payload.question,
        conversation_id=payload.conversation_id or payload.thread_id,
        knowledge_base_id=payload.knowledge_base_id,
    )


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    context: UserContext = Depends(require_permissions("agent:execute")),
    service=Depends(get_chat_service),
):
    # The verified answer is emitted as SSE by the shared response helper. The
    # service persists the run before any final content is returned.
    from api.application import _sse_payload_response

    result = await service.chat(
        context=context,
        question=payload.question,
        conversation_id=payload.conversation_id or payload.thread_id,
        knowledge_base_id=payload.knowledge_base_id,
    )
    return _sse_payload_response(result)
