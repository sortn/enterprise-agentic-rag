from __future__ import annotations


class AuthError(Exception):
    def __init__(self, message: str, *, code: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class AuthConflictError(AuthError):
    def __init__(self, message: str = "用户名或邮箱已存在"):
        super().__init__(message, code="auth_conflict", status_code=409)


class InvalidCredentialsError(AuthError):
    def __init__(self, message: str = "用户名或密码错误"):
        super().__init__(message, code="invalid_credentials", status_code=401)


class InvalidTokenError(AuthError):
    def __init__(self, message: str = "Token 无效或已过期"):
        super().__init__(message, code="invalid_token", status_code=401)


class UserInactiveError(AuthError):
    def __init__(self, message: str = "用户已被禁用"):
        super().__init__(message, code="user_inactive", status_code=403)


class AuthDependencyError(AuthError):
    def __init__(self, message: str = "认证依赖暂时不可用"):
        super().__init__(message, code="auth_dependency_unavailable", status_code=503)


def sanitized_validation_errors(errors: list[dict]) -> list[dict]:
    """Remove submitted values so passwords never appear in validation responses."""
    return [
        {
            "type": error.get("type", "validation_error"),
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "请求参数无效"),
        }
        for error in errors
    ]


def sanitized_validation_errors(errors: list[dict]) -> list[dict]:
    """Remove submitted values so passwords never appear in validation responses."""
    return [
        {
            "type": error.get("type", "validation_error"),
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "请求参数无效"),
        }
        for error in errors
    ]
