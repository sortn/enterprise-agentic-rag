from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from auth.api import create_auth_router, create_jwks_router
from auth.dependencies import require_permissions
from auth.errors import AuthError, sanitized_validation_errors
from auth.jwt import JWTIssuer, JWTVerifier, RSAKeyManager
from auth.middleware import JWTAuthenticationMiddleware
from auth.models import UserContext
from auth.password import PasswordManager
from auth.service import AsyncAuthService

from tests.auth_fakes import MemoryRefreshTokens, MemoryUserRepository


def _client(tmp_path) -> TestClient:
    repository = MemoryUserRepository("00000000-0000-0000-0000-000000000001")
    keys = RSAKeyManager(tmp_path / "private.pem", tmp_path / "public.pem", key_size=2048)
    issuer = JWTIssuer(
        keys.private_key,
        kid="api-test-key",
        issuer="issuer",
        audience="api",
        ttl_seconds=900,
    )
    verifier = JWTVerifier(
        keys.public_key,
        kid="api-test-key",
        issuer="issuer",
        audience="api",
    )
    service = AsyncAuthService(
        repository,
        MemoryRefreshTokens(),
        PasswordManager(),
        issuer,
        verifier,
        access_ttl_seconds=900,
        refresh_ttl_seconds=3600,
        first_user_admin=True,
    )
    app = FastAPI()
    app.add_middleware(JWTAuthenticationMiddleware, verifier=verifier)
    app.include_router(create_auth_router(service))
    app.include_router(create_jwks_router(service))

    @app.exception_handler(AuthError)
    async def handle_auth_error(_request: Request, exc: AuthError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": sanitized_validation_errors(exc.errors())},
        )

    @app.get("/api/v1/private")
    def private(_context: UserContext = Depends(require_permissions("agent:execute"))):
        return {"ok": True}

    return TestClient(app)


def test_auth_http_contract_and_refresh_rotation(tmp_path):
    client = _client(tmp_path)
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": "owner",
            "email": "owner@example.com",
            "password": "secure-password-123",
            "device_info": "pytest-api",
        },
    )
    assert registration.status_code == 201
    payload = registration.json()
    assert payload["token_type"] == "Bearer"
    assert payload["user"]["roles"] == ["admin"]

    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/v1/private", headers=headers).json() == {"ok": True}

    old_refresh = payload["refresh_token"]
    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refreshed.status_code == 200
    rotated = refreshed.json()["refresh_token"]
    assert rotated != old_refresh
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    ).status_code == 401

    assert client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": rotated},
    ).json() == {"success": True}
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated},
    ).status_code == 401

    jwks = client.get("/.well-known/jwks.json").json()
    assert jwks["keys"][0]["kid"] == "api-test-key"
    openapi = client.get("/openapi.json").json()
    assert "RS256Bearer" in openapi["components"]["securitySchemes"]


def test_auth_validation_response_never_echoes_password(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422
    assert '"short"' not in response.text
