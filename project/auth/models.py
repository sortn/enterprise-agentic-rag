from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UserRecord:
    id: str
    tenant_id: str
    username: str
    email: str
    password_hash: str
    status: str
    created_at: str
    updated_at: str
    roles: tuple[str, ...] = field(default_factory=tuple)
    permissions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def primary_role(self) -> str:
        if "admin" in self.roles:
            return "admin"
        return self.roles[0] if self.roles else "user"


@dataclass(frozen=True)
class UserContext:
    user_id: str
    username: str
    role: str
    tenant_id: str
    permissions: tuple[str, ...] = field(default_factory=tuple)

    def to_agent_context(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "tenant_id": self.tenant_id,
            "permissions": list(self.permissions),
        }


@dataclass(frozen=True)
class RefreshTokenRecord:
    user_id: str
    device_info: str
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int


@dataclass(frozen=True)
class AuthResult:
    user: UserRecord
    tokens: TokenPair
