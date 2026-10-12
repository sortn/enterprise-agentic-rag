from __future__ import annotations

from auth.errors import InvalidTokenError
from auth.jwt import JWTIssuer, JWTVerifier, RSAKeyManager
from auth.password import PasswordManager
from auth.service import AsyncAuthService
import pytest

from tests.auth_fakes import MemoryRefreshTokens, MemoryUserRepository


def _service(tmp_path, *, first_user_admin=False):
    repository = MemoryUserRepository("00000000-0000-0000-0000-000000000001")
    keys = RSAKeyManager(tmp_path / "private.pem", tmp_path / "public.pem", key_size=2048)
    issuer = JWTIssuer(
        keys.private_key,
        kid=keys.kid,
        issuer="issuer",
        audience="api",
        ttl_seconds=900,
    )
    verifier = JWTVerifier(
        keys.public_key,
        kid=keys.kid,
        issuer="issuer",
        audience="api",
    )
    refresh_tokens = MemoryRefreshTokens()
    return (
        AsyncAuthService(
            repository,
            refresh_tokens,
            PasswordManager(),
            issuer,
            verifier,
            access_ttl_seconds=900,
            refresh_ttl_seconds=3600,
            first_user_admin=first_user_admin,
        ),
        repository,
        refresh_tokens,
    )


@pytest.mark.asyncio
async def test_register_login_refresh_rotation_logout_and_me(tmp_path):
    service, repository, refresh_tokens = _service(tmp_path)
    registered = await service.register(
        username="alice",
        email="alice@example.com",
        password="secure-password-123",
        device_info="pytest",
    )

    stored = await repository.get_user_by_id(registered.user.id)
    assert stored is not None
    assert stored.password_hash != "secure-password-123"
    assert registered.tokens.refresh_token in refresh_tokens.records

    context = service.jwt_verifier.verify(registered.tokens.access_token)
    assert (await service.get_current_user(context)).username == "alice"

    logged_in = await service.login(
        identifier="alice",
        password="secure-password-123",
        tenant_id=None,
        device_info="pytest-login",
    )
    old_refresh = logged_in.tokens.refresh_token
    rotated = await service.refresh(old_refresh)
    assert old_refresh not in refresh_tokens.records
    assert rotated.refresh_token in refresh_tokens.records

    with pytest.raises(InvalidTokenError):
        await service.refresh(old_refresh)

    assert await service.logout(rotated.refresh_token) is True
    assert rotated.refresh_token not in refresh_tokens.records


@pytest.mark.asyncio
async def test_first_registered_user_can_bootstrap_admin_role(tmp_path):
    service, _, _ = _service(tmp_path, first_user_admin=True)

    first = await service.register(
        username="owner",
        email="owner@example.com",
        password="secure-password-123",
        device_info="pytest",
    )
    second = await service.register(
        username="member",
        email="member@example.com",
        password="secure-password-456",
        device_info="pytest",
    )

    assert first.user.primary_role == "admin"
    assert second.user.primary_role == "user"
