from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import secrets

from .errors import AuthDependencyError, InvalidCredentialsError, InvalidTokenError, UserInactiveError
from .jwt import JWTIssuer, JWTVerifier
from .models import AuthResult, RefreshTokenRecord, TokenPair, UserContext, UserRecord
from .password import PasswordManager


class AsyncAuthService:
    """Async authentication use cases backed by PostgreSQL and Redis."""

    def __init__(
        self,
        repository,
        refresh_tokens,
        password_manager: PasswordManager,
        jwt_issuer: JWTIssuer,
        jwt_verifier: JWTVerifier,
        *,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        first_user_admin: bool = False,
    ) -> None:
        self.repository = repository
        self.refresh_tokens = refresh_tokens
        self.password_manager = password_manager
        self.jwt_issuer = jwt_issuer
        self.jwt_verifier = jwt_verifier
        self.access_ttl_seconds = access_ttl_seconds
        self.refresh_ttl_seconds = refresh_ttl_seconds
        self.first_user_admin = first_user_admin

    async def initialize(self) -> None:
        await self.repository.initialize()

    async def register(
        self,
        *,
        username: str,
        email: str,
        password: str,
        device_info: str,
    ) -> AuthResult:
        await self.refresh_tokens.ping()
        user = await self.repository.create_user(
            username=username.strip().lower(),
            email=email.strip().lower(),
            password_hash=await asyncio.to_thread(self.password_manager.hash, password),
            role="user",
            role_if_first="admin" if self.first_user_admin else None,
        )
        try:
            tokens = await self._issue_tokens(user, device_info)
        except AuthDependencyError:
            await self.repository.delete_user(user.id)
            raise
        return AuthResult(user=user, tokens=tokens)

    async def login(
        self,
        *,
        identifier: str,
        password: str,
        tenant_id: str | None,
        device_info: str,
    ) -> AuthResult:
        normalized = identifier.strip().lower()
        user = await self.repository.find_user(normalized, tenant_id)
        if user is None:
            await asyncio.to_thread(self.password_manager.verify_dummy, password)
            raise InvalidCredentialsError()
        if not await asyncio.to_thread(
            self.password_manager.verify, user.password_hash, password
        ):
            raise InvalidCredentialsError()
        self._require_active(user)
        await self.refresh_tokens.ping()
        if self.password_manager.needs_rehash(user.password_hash):
            password_hash = await asyncio.to_thread(self.password_manager.hash, password)
            await self.repository.update_password_hash(
                user.id, password_hash
            )
            user = await self.repository.get_user_by_id(user.id) or user
        return AuthResult(user=user, tokens=await self._issue_tokens(user, device_info))

    async def refresh(self, refresh_token: str) -> TokenPair:
        record = await self.refresh_tokens.consume(refresh_token)
        if record is None:
            raise InvalidTokenError("Refresh Token 无效、已过期或已被使用")
        try:
            expires_at = datetime.fromisoformat(record.expires_at)
        except (TypeError, ValueError) as exc:
            raise InvalidTokenError() from exc
        if expires_at.tzinfo is None or expires_at <= datetime.now(UTC):
            raise InvalidTokenError("Refresh Token 已过期")
        user = await self.repository.get_user_by_id(record.user_id)
        if user is None:
            raise InvalidTokenError()
        self._require_active(user)
        return await self._issue_tokens(user, record.device_info)

    async def logout(self, refresh_token: str) -> bool:
        await self.refresh_tokens.revoke(refresh_token)
        return True

    async def get_current_user(self, context: UserContext) -> UserRecord:
        user = await self.repository.get_user_by_id(context.user_id)
        if user is None or user.tenant_id != context.tenant_id:
            raise InvalidTokenError()
        self._require_active(user)
        return user

    async def readiness(self) -> dict[str, str]:
        if not await self.repository.ping() or not await self.refresh_tokens.ping():
            raise AuthDependencyError()
        return {"postgresql": "ok", "redis": "ok", "jwt_keys": "ok"}

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        return self.jwt_verifier.jwks()

    async def _issue_tokens(self, user: UserRecord, device_info: str) -> TokenPair:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.refresh_ttl_seconds)
        access_token = self.jwt_issuer.issue_access_token(user)
        record = RefreshTokenRecord(
            user_id=user.id,
            device_info=device_info or "unknown",
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
        )
        refresh_token = ""
        for _ in range(3):
            candidate = secrets.token_urlsafe(48)
            if await self.refresh_tokens.create(candidate, record, self.refresh_ttl_seconds):
                refresh_token = candidate
                break
        if not refresh_token:
            raise AuthDependencyError("无法创建 Refresh Token")
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=self.access_ttl_seconds,
            refresh_expires_in=self.refresh_ttl_seconds,
        )

    @staticmethod
    def _require_active(user: UserRecord) -> None:
        if user.status != "active":
            raise UserInactiveError()
