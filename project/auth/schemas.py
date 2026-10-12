from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator

from .models import AuthResult, TokenPair, UserRecord


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)
    device_info: str = Field(default="unknown", max_length=512)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)
    device_info: str = Field(default="unknown", max_length=512)

    @field_validator("username")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: SecretStr = Field(min_length=32, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: SecretStr = Field(min_length=32, max_length=512)


class UserResponse(BaseModel):
    id: str
    tenant_id: str
    username: str
    email: EmailStr
    status: str
    roles: list[str]
    permissions: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, user: UserRecord) -> "UserResponse":
        return cls(
            id=user.id,
            tenant_id=user.tenant_id,
            username=user.username,
            email=user.email,
            status=user.status,
            roles=list(user.roles),
            permissions=list(user.permissions),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_expires_in: int

    @classmethod
    def from_pair(cls, tokens: TokenPair) -> "TokenResponse":
        return cls(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.access_expires_in,
            refresh_expires_in=tokens.refresh_expires_in,
        )


class AuthResponse(TokenResponse):
    user: UserResponse

    @classmethod
    def from_result(cls, result: AuthResult) -> "AuthResponse":
        return cls(
            access_token=result.tokens.access_token,
            refresh_token=result.tokens.refresh_token,
            expires_in=result.tokens.access_expires_in,
            refresh_expires_in=result.tokens.refresh_expires_in,
            user=UserResponse.from_record(result.user),
        )


class LogoutResponse(BaseModel):
    success: bool


class ErrorResponse(BaseModel):
    code: str
    detail: str
