from __future__ import annotations

from fastapi import APIRouter, Depends, status

from .dependencies import get_current_user
from .models import UserContext
from .schemas import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from .service import AsyncAuthService


def create_auth_router(service: AsyncAuthService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

    @router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
    async def register(request: RegisterRequest) -> AuthResponse:
        result = await service.register(
            username=request.username,
            email=str(request.email),
            password=request.password.get_secret_value(),
            device_info=request.device_info,
        )
        return AuthResponse.from_result(result)

    @router.post("/login", response_model=AuthResponse)
    async def login(request: LoginRequest) -> AuthResponse:
        result = await service.login(
            identifier=request.username,
            password=request.password.get_secret_value(),
            tenant_id=request.tenant_id,
            device_info=request.device_info,
        )
        return AuthResponse.from_result(result)

    @router.post("/refresh", response_model=TokenResponse)
    async def refresh(request: RefreshRequest) -> TokenResponse:
        tokens = await service.refresh(request.refresh_token.get_secret_value())
        return TokenResponse.from_pair(tokens)

    @router.post("/logout", response_model=LogoutResponse)
    async def logout(request: LogoutRequest) -> LogoutResponse:
        success = await service.logout(request.refresh_token.get_secret_value())
        return LogoutResponse(success=success)

    @router.get("/me", response_model=UserResponse)
    async def current_user(context: UserContext = Depends(get_current_user)) -> UserResponse:
        user = await service.get_current_user(context)
        return UserResponse.from_record(user)

    return router


def create_jwks_router(service: AsyncAuthService) -> APIRouter:
    router = APIRouter(tags=["Authentication"])

    @router.get("/.well-known/jwks.json")
    def jwks() -> dict[str, list[dict[str, str]]]:
        return service.jwks()

    return router
