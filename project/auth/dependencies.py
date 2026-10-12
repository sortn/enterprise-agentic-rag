from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .models import UserContext


bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="RS256Bearer",
    description="RS256 Access Token",
)


def _user_from_state(request: Request) -> UserContext:
    user = getattr(request.state, "user", None)
    if not isinstance(user, UserContext):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少有效的身份认证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user(
    request: Request,
    _credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> UserContext:
    return _user_from_state(request)


def require_roles(*allowed_roles: str) -> Callable[[Request], UserContext]:
    allowed = frozenset(allowed_roles)

    def dependency(
        request: Request,
        _credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    ) -> UserContext:
        user = _user_from_state(request)
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="当前角色无权执行此操作")
        return user

    return dependency


def require_permissions(*required_permissions: str) -> Callable[[Request], UserContext]:
    required = frozenset(required_permissions)

    def dependency(
        request: Request,
        _credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    ) -> UserContext:
        user = _user_from_state(request)
        if not required.issubset(user.permissions):
            raise HTTPException(status_code=403, detail="缺少执行此操作所需的权限")
        return user

    return dependency
