from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import uuid

from auth.errors import AuthConflictError
from auth.models import RefreshTokenRecord, UserRecord
from auth.repository import ROLE_PERMISSION_CODES


class MemoryUserRepository:
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self.users: dict[str, UserRecord] = {}

    async def initialize(self) -> None:
        return None

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
        target_tenant = tenant_id or self.tenant_id
        if any(
            user.tenant_id == target_tenant
            and (user.username == username or user.email == email)
            for user in self.users.values()
        ):
            raise AuthConflictError()
        effective_role = role_if_first if role_if_first and not self.users else role
        now = datetime.now(UTC).isoformat()
        user = UserRecord(
            id=str(uuid.uuid4()),
            tenant_id=target_tenant,
            username=username,
            email=email,
            password_hash=password_hash,
            status="active",
            created_at=now,
            updated_at=now,
            roles=(effective_role,),
            permissions=ROLE_PERMISSION_CODES[effective_role],
        )
        self.users[user.id] = user
        return user

    async def find_user(self, identifier: str, tenant_id: str | None = None):
        target_tenant = tenant_id or self.tenant_id
        return next(
            (
                user
                for user in self.users.values()
                if user.tenant_id == target_tenant
                and identifier in {user.username, user.email}
            ),
            None,
        )

    async def get_user_by_id(self, user_id: str):
        return self.users.get(user_id)

    async def update_password_hash(self, user_id: str, password_hash: str) -> None:
        user = self.users.get(user_id)
        if user:
            self.users[user_id] = replace(user, password_hash=password_hash)

    async def delete_user(self, user_id: str) -> None:
        self.users.pop(user_id, None)

    async def assign_role(self, user_id: str, role: str) -> None:
        user = self.users[user_id]
        roles = tuple(dict.fromkeys((*user.roles, role)))
        permissions = tuple(
            dict.fromkeys(
                permission
                for role_name in roles
                for permission in ROLE_PERMISSION_CODES[role_name]
            )
        )
        self.users[user_id] = replace(user, roles=roles, permissions=permissions)

    async def set_user_status(self, user_id: str, status: str) -> None:
        self.users[user_id] = replace(self.users[user_id], status=status)

    async def ping(self) -> bool:
        return True


class MemoryRefreshTokens:
    def __init__(self) -> None:
        self.records: dict[str, RefreshTokenRecord] = {}

    async def create(self, token, record, ttl_seconds):
        if token in self.records:
            return False
        self.records[token] = record
        return True

    async def consume(self, token):
        return self.records.pop(token, None)

    async def revoke(self, token):
        return self.records.pop(token, None) is not None

    async def ping(self):
        return True

    async def close(self):
        return None
