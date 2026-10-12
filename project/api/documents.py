from fastapi import APIRouter, Depends, File, UploadFile

from auth.dependencies import require_permissions
from auth.models import UserContext
from .dependencies import get_document_service
from .schemas import DeleteDocumentResponse, DocumentResponse


router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])


@router.get("", response_model=dict)
async def list_documents(
    knowledge_base_id: str | None = None,
    context: UserContext = Depends(require_permissions("documents:read")),
    service=Depends(get_document_service),
):
    return {"documents": await service.list(context, knowledge_base_id)}


@router.post("", response_model=dict)
async def upload_documents(
    files: list[UploadFile] = File(...),
    knowledge_base_id: str | None = None,
    context: UserContext = Depends(require_permissions("documents:write")),
    service=Depends(get_document_service),
):
    return {"results": await service.upload(context, files, knowledge_base_id)}


@router.delete("/{doc_id}", response_model=DeleteDocumentResponse)
async def delete_document(
    doc_id: str,
    knowledge_base_id: str | None = None,
    context: UserContext = Depends(require_permissions("documents:delete")),
    service=Depends(get_document_service),
):
    await service.delete(context, doc_id, knowledge_base_id)
    return DeleteDocumentResponse(doc_id=doc_id, deleted=True)
