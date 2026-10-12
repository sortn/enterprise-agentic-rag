from __future__ import annotations

from contextvars import ContextVar
import json
import logging
import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from config import Settings


request_id_var: ContextVar[str] = ContextVar("request_id", default="")
run_id_var: ContextVar[str] = ContextVar("run_id", default="")


def current_request_id() -> str:
    return request_id_var.get() or str(uuid.uuid4())


class JsonFormatter(logging.Formatter):
    """Small dependency-free structured formatter for API and worker logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "run_id": run_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        candidate = request.headers.get("X-Request-ID", "")
        request_id = (
            candidate
            if re.fullmatch(r"[A-Za-z0-9._-]{1,36}", candidate)
            else str(uuid.uuid4())
        )
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request.state.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            logging.getLogger("http.access").info(
                "%s %s status=%s elapsed_ms=%s user_id=%s tenant_id=%s",
                request.method,
                request.url.path,
                getattr(locals().get("response"), "status_code", 500),
                request.state.elapsed_ms,
                getattr(getattr(request.state, "user", None), "user_id", ""),
                getattr(getattr(request.state, "user", None), "tenant_id", ""),
            )
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f"app;dur={request.state.elapsed_ms}"
        return response


class Observability:
    """Optional Langfuse adapter; structured local logs work without it."""

    def __init__(self, settings: Settings):
        self._enabled = bool(getattr(settings, "langfuse_enabled", False))
        self._handler = None
        self._client = None
        if not self._enabled:
            return
        if not getattr(settings, "langfuse_public_key", "") or not getattr(
            settings, "langfuse_secret_key", ""
        ):
            logging.getLogger(__name__).warning(
                "Langfuse enabled but API keys are missing; tracing disabled"
            )
            self._enabled = False
            return
        try:
            from langfuse import get_client
            from langfuse.langchain import CallbackHandler

            self._client = get_client()
            if not self._client.auth_check():
                raise RuntimeError("Langfuse authentication failed")
            self._handler = CallbackHandler()
        except Exception as exc:
            logging.getLogger(__name__).warning("Could not initialize Langfuse: %s", exc)
            self._enabled = False

    def graph_callbacks(self) -> list:
        return [self._handler] if self._handler is not None else []

    def flush(self) -> None:
        if self._client is not None:
            try:
                self._client.flush()
            except Exception:
                logging.getLogger(__name__).debug("Langfuse flush failed", exc_info=True)
