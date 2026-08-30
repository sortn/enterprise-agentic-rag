from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    intent: str
    rewritten_query: str
    citations: list[dict[str, str]]
    grounded: bool
    retrieval_attempts: int


class DeleteDocumentResponse(BaseModel):
    doc_id: str
    deleted: bool
