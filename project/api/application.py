"""Enterprise FastAPI application factory and dependency lifecycle."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import inspect
import json
import logging
from typing import Iterator

import gradio as gr
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from auth.api import create_auth_router, create_jwks_router
from auth.dependencies import require_permissions
from auth.errors import AuthError, sanitized_validation_errors
from auth.middleware import JWTAuthenticationMiddleware
from auth.models import UserContext
from config import get_settings
from core.container import build_application_services
from core.observability import RequestContextMiddleware, configure_logging
from services.errors import DomainError
from ui.dashboard import APP_THEME, create_gradio_ui, custom_css
from .chat import router as chat_router
from .audit import router as audit_router
from .conversations import router as conversations_router
from .documents import router as documents_router
from .evaluation import router as evaluation_router
from .knowledge_bases import router as knowledge_bases_router


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
services = build_application_services(settings)
system = services.rag
auth = services.auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.services = services
    await services.startup()
    try:
        yield
    finally:
        await services.shutdown()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="支持多租户权限隔离、混合检索和可审计 Agent 运行的企业知识库服务",
    lifespan=lifespan,
)
app.state.services = services
app.add_middleware(JWTAuthenticationMiddleware, verifier=auth.verifier)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.include_router(create_auth_router(auth.service))
app.include_router(create_jwks_router(auth.service))
app.include_router(knowledge_bases_router)
app.include_router(documents_router)
app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(audit_router)
app.include_router(evaluation_router)


@app.exception_handler(AuthError)
async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "detail": exc.message},
        headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
    )


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "detail": exc.message},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, _exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database operation failed")
    return JSONResponse(
        status_code=503,
        content={"code": "database_unavailable", "detail": "数据库服务暂时不可用"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": sanitized_validation_errors(exc.errors())},
    )


def _health_payload(status: str) -> dict:
    return {
        "status": status,
        "version": settings.app_version,
        "models": {
            "llm": settings.llm_model,
            "embedding": settings.embedding_model,
            "reranker": settings.rerank_model,
        },
    }


@app.get("/api/v1/health")
def health():
    return _health_payload("ready" if system.initialized else "starting")


@app.get("/api/v1/health/live")
def health_live():
    return {"status": "alive", "version": settings.app_version}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/")


@app.get("/api/v1/health/ready")
async def health_ready():
    try:
        checks = await auth.service.readiness()
        rag = await asyncio.to_thread(system.initialize)
        if rag.store is None:
            raise RuntimeError("Milvus store was not initialized")
        await asyncio.to_thread(rag.store.list_documents)
    except Exception as exc:
        logger.exception("Readiness probe failed")
        raise HTTPException(
            status_code=503,
            detail="系统依赖尚未就绪，请检查服务端日志。",
        ) from exc
    payload = _health_payload("ready")
    payload["checks"] = {
        **checks,
        "milvus": "ok",
        "model_api": "configured",
    }
    return payload


@app.get("/mock-api/v1/inventory/{sku}")
def mock_inventory(
    sku: str,
    _context: UserContext = Depends(require_permissions("agent:execute")),
):
    return system.initialize().tool_data_service.lookup("inventory", sku)


@app.get("/mock-api/v1/services/{service_name}")
def mock_service_status(
    service_name: str,
    _context: UserContext = Depends(require_permissions("agent:execute")),
):
    return system.initialize().tool_data_service.lookup("service_status", service_name)


def _sse_payload_response(result: dict) -> StreamingResponse:
    def events() -> Iterator[str]:
        thread_id = str(result.get("thread_id", ""))
        yield f"data: {json.dumps({'event': 'start', 'thread_id': thread_id}, ensure_ascii=False)}\n\n"
        answer = str(result.get("answer", ""))
        for start in range(0, len(answer), settings.sse_chunk_size):
            event = {
                "event": "token",
                "content": answer[start : start + settings.sse_chunk_size],
            }
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'event': 'final', **result}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


app = gr.mount_gradio_app(
    app,
    create_gradio_ui(settings.api_base_url),
    path="/ui",
    theme=APP_THEME,
    css=custom_css,
    footer_links=[],
)
