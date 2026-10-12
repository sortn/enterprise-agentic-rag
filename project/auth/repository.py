from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
import uuid

from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from .errors import AuthConflictError, AuthDependencyError
from .models import RefreshTokenRecord, UserRecord
from database.models import Permission, Role, RolePermission, Tenant, User, UserRole


ROLE_IDS = {"admin": "role-admin", "user": "role-user"}
PERMISSIONS = {
    "agent:execute": "运行企业知识 Agent",
    "documents:read": "查看知识库文档",
    "documents:write": "上传知识库文档",
    "documents:delete": "删除知识库文档",
    "profile:read": "查看当前用户信息",
    "knowledge_bases:read": "查看可访问的知识库",
    "knowledge_bases:write": "创建和管理知识库",
    "conversations:read": "查看自己的对话历史",
    "audit:read": "查看租户审计记录",
}
ROLE_PERMISSION_CODES = {
    "admin": tuple(PERMISSIONS),
    "user": (
        "agent:execute",
        "documents:read",
        "profile:read",
        "knowledge_bases:read",
        "conversations:read",
    ),
}


class SQLAlchemyAuthRepository:
    """Async PostgreSQL/SQLAlchemy identity and RBAC repository."""

    def __init__(
        self,
        sessions: async_sessionmaker,
        *,
        default_tenant_id: str,
        default_tenant_name: str,
    ) -> None:
        self.sessions = sessions
        self.default_tenant_id = default_tenant_id
        self.default_tenant_name = default_tenant_name

    async def initialize(self) -> None:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            if await session.get(Tenant, self.default_tenant_id) is None:
                session.add(
                    Tenant(
                        id=self.default_tenant_id,
                        name=self.default_tenant_name,
                        slug="default",
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
            for name, role_id in ROLE_IDS.items():
                if await session.get(Role, role_id) is None:
                    session.add(
                        Role(
                            id=role_id,
                            name=name,
                            description=f"Built-in {name} role",
                            created_at=now,
                            updated_at=now,
                        )
                    )
            for code, description in PERMISSIONS.items():
                permission_id = f"permission-{code.replace(':', '-')}"
                if await session.get(Permission, permission_id) is None:
                    session.add(
                        Permission(
                            id=permission_id,
                            code=code,
                            description=description,
                            created_at=now,
                            updated_at=now,
                        )
                    )
            await session.flush()
            for role_name, codes in ROLE_PERMISSION_CODES.items():
                for code in codes:
                    key = {
                        "role_id": ROLE_IDS[role_name],
                        "permission_id": f"permission-{code.replace(':', '-')}",
                    }
                    if await session.get(RolePermission, key) is None:
                        session.add(RolePermission(**key, created_at=now))

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password_hash: str,
        tenant_id: str | None = None,
        role: str = "user",
        role_if_first: str | None = None,
    ) -> UserRecord:
        user_id = str(uuid.uuid4())
        target_tenant = tenant_id or self.default_tenant_id
        try:
            async with self.sessions() as session, session.begin():
                effective_role = role
                if role_if_first is not None:
                    count = await session.scalar(
                        select(func.count(User.id)).where(User.tenant_id == target_tenant)
                    )
                    if int(count or 0) == 0:
                        effective_role = role_if_first
                role_id = ROLE_IDS.get(effective_role)
                if role_id is None:
                    raise ValueError(f"unknown role: {effective_role}")
                session.add(
                    User(
                        id=user_id,
                        tenant_id=target_tenant,
                        username=username,
                        email=email,
                        password_hash=password_hash,
                        status="active",
                    )
                )
                await session.flush()
                session.add(UserRole(user_id=user_id, role_id=role_id))
        except IntegrityError as exc:
            raise AuthConflictError() from exc
        user = await self.get_user_by_id(user_id)
        if user is None:
            raise RuntimeError("created user could not be loaded")
        return user

    async def find_user(self, identifier: str, tenant_id: str | None = None) -> UserRecord | None:
        target_tenant = tenant_id or self.default_tenant_id
        async with self.sessions() as session:
            user = await session.scalar(
                select(User).where(
                    User.tenant_id == target_tenant,
                    (User.username == identifier) | (User.email == identifier),
                )
            )
            return await self._hydrate_user(session, user) if user else None

    async def get_user_by_id(self, user_id: str) -> UserRecord | None:
        async with self.sessions() as session:
            user = await session.get(User, user_id)
            return await self._hydrate_user(session, user) if user else None

    async def update_password_hash(self, user_id: str, password_hash: str) -> None:
        async with self.sessions() as session, session.begin():
            user = await session.get(User, user_id)
            if user:
                user.password_hash = password_hash
                user.updated_at = datetime.now(UTC)

    async def delete_user(self, user_id: str) -> None:
        async with self.sessions() as session, session.begin():
            await session.execute(delete(User).where(User.id == user_id))

    async def assign_role(self, user_id: str, role: str) -> None:
        role_id = ROLE_IDS.get(role)
        if role_id is None:
            raise ValueError(f"unknown role: {role}")
        async with self.sessions() as session, session.begin():
            key = {"user_id": user_id, "role_id": role_id}
            if await session.get(UserRole, key) is None:
                session.add(UserRole(**key))

    async def set_user_status(self, user_id: str, status: str) -> None:
        if status not in {"active", "disabled", "locked"}:
            raise ValueError("invalid user status")
        async with self.sessions() as session, session.begin():
            user = await session.get(User, user_id)
            if user:
                user.status = status
                user.updated_at = datetime.now(UTC)

    async def ping(self) -> bool:
        async with self.sessions() as session:
            count = await session.scalar(select(func.count()).select_from(Tenant))
            return int(count or 0) >= 1

    @staticmethod
    async def _hydrate_user(session, user: User) -> UserRecord:
        roles = tuple(
            (await session.scalars(
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
                .order_by(Role.name)
            )).all()
        )
        permissions = tuple(
            (await session.scalars(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(UserRole.user_id == user.id)
                .distinct()
                .order_by(Permission.code)
            )).all()
        )
        if "admin" in roles:
            roles = ("admin", *tuple(role for role in roles if role != "admin"))
        return UserRecord(
            id=user.id,
            tenant_id=user.tenant_id,
            username=user.username,
            email=user.email,
            password_hash=user.password_hash,
            status=user.status,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
            roles=roles,
            permissions=permissions,
        )


class AsyncRedisRefreshTokenRepository:
    """Non-blocking refresh-token storage for the FastAPI application."""

    _CONSUME_SCRIPT = """
    local value = redis.call('GET', KEYS[1])
    if value then redis.call('DEL', KEYS[1]) end
    return value
    """

    def __init__(self, redis_url: str, key_prefix: str = "refresh_token:") -> None:
        self.client = AsyncRedis.from_url(redis_url, decode_responses=True)
        self.key_prefix = key_prefix

    async def create(self, token: str, record: RefreshTokenRecord, ttl_seconds: int) -> bool:
        try:
            return bool(
                await self.client.set(
                    self._key(token),
                    json.dumps(asdict(record), ensure_ascii=False),
                    ex=ttl_seconds,
                    nx=True,
                )
            )
        except RedisError as exc:
            raise AuthDependencyError() from exc

    async def consume(self, token: str) -> RefreshTokenRecord | None:
        try:
            raw = await self.client.eval(self._CONSUME_SCRIPT, 1, self._key(token))
        except RedisError as exc:
            raise AuthDependencyError() from exc
        if not raw:
            return None
        try:
            return RefreshTokenRecord(**json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    async def revoke(self, token: str) -> bool:
        try:
            return bool(await self.client.delete(self._key(token)))
        except RedisError as exc:
            raise AuthDependencyError() from exc

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except RedisError as exc:
            raise AuthDependencyError() from exc

    async def close(self) -> None:
        await self.client.aclose()

    def _key(self, token: str) -> str:
        return f"{self.key_prefix}{token}"
