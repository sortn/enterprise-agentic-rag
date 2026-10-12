from __future__ import annotations

from collections.abc import Iterable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .errors import InvalidTokenError
from .jwt import JWTVerifier


class JWTAuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        verifier: JWTVerifier,
        protected_prefixes: Iterable[str] = ("/api/v1", "/mock-api/v1"),
        public_paths: Iterable[str] = (
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/.well-known/jwks.json",
        ),
        public_prefixes: Iterable[str] = ("/api/v1/health",),
    ) -> None:
        super().__init__(app)
        self.verifier = verifier
        self.protected_prefixes = tuple(protected_prefixes)
        self.public_paths = frozenset(public_paths)
        self.public_prefixes = tuple(public_prefixes)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS" or not self._requires_authentication(request.url.path):
            return await call_next(request)
        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token.strip():
            return self._unauthorized("缺少 Bearer Token")
        try:
            request.state.user = self.verifier.verify(token.strip())
        except InvalidTokenError as exc:
            return self._unauthorized(exc.message)
        return await call_next(request)

    def _requires_authentication(self, path: str) -> bool:
        if path in self.public_paths or any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in self.public_prefixes
        ):
            return False
        return any(path.startswith(prefix) for prefix in self.protected_prefixes)

    @staticmethod
    def _unauthorized(detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"code": "invalid_token", "detail": detail},
            headers={"WWW-Authenticate": "Bearer"},
        )
