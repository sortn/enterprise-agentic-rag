"""FastAPI app: document management, chat/SSE, health and mock business APIs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator
import uuid

import gradio as gr
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import get_settings
from core.rag_system import RAGSystem
from ui.dashboard import APP_THEME, create_gradio_ui, custom_css
from .schemas import ChatRequest, ChatResponse, DeleteDocumentResponse

settings = get_settings()
logger = logging.getLogger(__name__)
system = RAGSystem(settings)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="LangGraph + Milvus + BGE 的企业知识库 Agentic RAG 演示",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def _ready_system() -> RAGSystem:
    try:
        return system.initialize()
    except Exception as exc:
        logger.exception("System initialization failed")
        raise HTTPException(status_code=503, detail=f"系统尚未就绪：{exc}") from exc


@app.get("/api/v1/health")
def health():
    return {
        "status": "ready" if system.initialized else "starting",
        "version": settings.app_version,
        "milvus_uri": settings.milvus_uri,
        "models": {
            "llm": settings.llm_model,
            "embedding": settings.embedding_model,
            "reranker": settings.rerank_model,
        },
    }


@app.get("/api/v1/documents")
def list_documents():
    rag = _ready_system()
    return {"documents": rag.store.list_documents()}


@app.post("/api/v1/documents")
def upload_documents(files: list[UploadFile] = File(...)):
    rag = _ready_system()
    results = []
    for upload in files:
        filename = Path(upload.filename or "").name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in settings.allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的文件：{filename}")
        if upload.size is not None and upload.size > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{filename} 超过 {settings.max_upload_mb} MB 限制")
        destination = settings.upload_dir / filename
        temporary = settings.upload_dir / f".{uuid.uuid4().hex}.uploading"
        committed = False
        try:
            written = 0
            with temporary.open("wb") as target:
                while block := upload.file.read(1024 * 1024):
                    written += len(block)
                    if written > settings.max_upload_mb * 1024 * 1024:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{filename} 超过 {settings.max_upload_mb} MB 限制",
                        )
                    target.write(block)
            temporary.replace(destination)
            committed = True
            results.append(rag.ingestion.ingest(destination).__dict__)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            if committed:
                destination.unlink(missing_ok=True)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(status_code=422, detail=f"{filename} 入库失败：{exc}") from exc
    return {"results": results}


@app.delete("/api/v1/documents/{doc_id}", response_model=DeleteDocumentResponse)
def delete_document(doc_id: str):
    rag = _ready_system()
    rag.delete_document(doc_id)
    return DeleteDocumentResponse(doc_id=doc_id, deleted=True)


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    rag = _ready_system()
    thread_id = request.thread_id or rag.new_thread_id()
    return ChatResponse(**rag.chat(request.question, thread_id))


@app.post("/api/v1/chat/stream")
def chat_stream(request: ChatRequest):
    rag = _ready_system()
    thread_id = request.thread_id or rag.new_thread_id()
    return _sse_response(rag, request.question, thread_id)


def _sse_response(rag: RAGSystem, question: str, thread_id: str) -> StreamingResponse:

    def events() -> Iterator[str]:
        try:
            for event in rag.stream(question, thread_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error = {"event": "error", "message": str(exc), "thread_id": thread_id}
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Compatibility aliases retained for the endpoint names in the project plan.
@app.post("/api/upload_doc", include_in_schema=False)
def upload_document_alias(file: UploadFile = File(...)):
    return upload_documents([file])


@app.get("/api/stream_chat", include_in_schema=False)
def stream_chat_alias(
    question: str = Query(min_length=1, max_length=2000),
    thread_id: str | None = None,
):
    rag = _ready_system()
    return _sse_response(rag, question, thread_id or rag.new_thread_id())


@app.get("/mock-api/v1/inventory/{sku}")
def mock_inventory(sku: str):
    rag = _ready_system()
    return rag.business_service.lookup("inventory", sku)


@app.get("/mock-api/v1/services/{service_name}")
def mock_service_status(service_name: str):
    rag = _ready_system()
    return rag.business_service.lookup("service_status", service_name)


app = gr.mount_gradio_app(
    app,
    create_gradio_ui(settings.api_base_url),
    path="/ui",
    theme=APP_THEME,
    css=custom_css,
    footer_links=[],
)
