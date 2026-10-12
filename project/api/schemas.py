from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(default=None, max_length=256)
    conversation_id: str | None = Field(default=None, max_length=64)
    knowledge_base_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    thread_id: str
    conversation_id: str | None = None
    run_id: str | None = None
    request_id: str | None = None
    answer: str
    intent: str
    rewritten_query: str
    citations: list[dict[str, str]]
    grounded: bool
    refused: bool
    retrieval_attempts: int


class DeleteDocumentResponse(BaseModel):
    doc_id: str
    deleted: bool


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class KnowledgeBaseResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str
    status: str
    created_by: str
    created_at: str
    updated_at: str


class KnowledgeBaseGrant(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    access_level: str = Field(pattern="^(viewer|editor|owner)$")


class DocumentResponse(BaseModel):
    id: str
    tenant_id: str
    knowledge_base_id: str
    title: str
    source_name: str
    file_type: str
    status: str
    current_version: int
    created_by: str
    created_at: str
    updated_at: str


class ConversationResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    knowledge_base_id: str | None
    title: str
    status: str
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    citations: list[dict]
    run_id: str | None
    created_at: str


class ConversationDetail(ConversationResponse):
    messages: list[MessageResponse]


class AuditLogResponse(BaseModel):
    id: str
    request_id: str
    tenant_id: str
    user_id: str | None
    action: str
    object_type: str
    object_id: str | None
    outcome: str
    detail: dict
    created_at: str
