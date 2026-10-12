from __future__ import annotations

from dataclasses import dataclass

from config import Settings
from database.session import DatabaseManager

from .jwt import JWTIssuer, JWTVerifier, RSAKeyManager
from .password import PasswordManager
from .repository import (
    AsyncRedisRefreshTokenRepository,
    SQLAlchemyAuthRepository,
)
from .service import AsyncAuthService


@dataclass(frozen=True)
class AuthContainer:
    service: AsyncAuthService
    verifier: JWTVerifier
    repository: SQLAlchemyAuthRepository
    refresh_tokens: AsyncRedisRefreshTokenRepository


def build_auth_container(settings: Settings, database: DatabaseManager) -> AuthContainer:
    repository = SQLAlchemyAuthRepository(
        database.sessions,
        default_tenant_id=settings.auth_default_tenant_id,
        default_tenant_name=settings.auth_default_tenant_name,
    )
    refresh_tokens = AsyncRedisRefreshTokenRepository(settings.redis_url)
    keys = RSAKeyManager(
        settings.auth_private_key_path,
        settings.auth_public_key_path,
        configured_kid=settings.auth_key_id,
        key_size=settings.auth_rsa_key_size,
    )
    access_ttl_seconds = settings.auth_access_token_minutes * 60
    jwt_issuer = JWTIssuer(
        keys.private_key,
        kid=keys.kid,
        issuer=settings.auth_jwt_issuer,
        audience=settings.auth_jwt_audience,
        ttl_seconds=access_ttl_seconds,
    )
    verifier = JWTVerifier(
        keys.public_key,
        kid=keys.kid,
        issuer=settings.auth_jwt_issuer,
        audience=settings.auth_jwt_audience,
    )
    service = AsyncAuthService(
        repository,
        refresh_tokens,
        PasswordManager(),
        jwt_issuer,
        verifier,
        access_ttl_seconds=access_ttl_seconds,
        refresh_ttl_seconds=settings.auth_refresh_token_days * 24 * 60 * 60,
        first_user_admin=settings.auth_first_user_admin,
    )
    return AuthContainer(
        service=service,
        verifier=verifier,
        repository=repository,
        refresh_tokens=refresh_tokens,
    )
