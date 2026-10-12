from __future__ import annotations

import pytest
from sqlalchemy import text

from auth.errors import AuthConflictError
from auth.repository import SQLAlchemyAuthRepository
from database.session import DatabaseManager


TENANT_ID = "00000000-0000-0000-0000-000000000001"


def _repository(database) -> SQLAlchemyAuthRepository:
    return SQLAlchemyAuthRepository(
        database.sessions,
        default_tenant_id=TENANT_ID,
        default_tenant_name="测试企业",
    )


@pytest.mark.asyncio
async def test_repository_creates_expandable_rbac_schema_and_default_user_role(postgres_settings):
    database = DatabaseManager(postgres_settings)
    await database.initialize()
    repository = _repository(database)
    await repository.initialize()
    user = await repository.create_user(
        username="alice",
        email="alice@example.com",
        password_hash="$argon2id$test",
    )

    assert user.tenant_id == TENANT_ID
    assert user.roles == ("user",)
    assert "agent:execute" in user.permissions
    assert "documents:write" not in user.permissions

    await repository.assign_role(user.id, "admin")
    elevated = await repository.get_user_by_id(user.id)
    assert elevated is not None
    assert elevated.primary_role == "admin"
    assert "documents:delete" in elevated.permissions

    async with database.sessions() as session:
        tables = set(
            await session.scalars(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = current_schema()"
                )
            )
        )
    assert {
        "tenants",
        "users",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
    } <= tables
    await database.close()


@pytest.mark.asyncio
async def test_repository_enforces_tenant_scoped_username_and_email_uniqueness(postgres_settings):
    database = DatabaseManager(postgres_settings)
    await database.initialize()
    repository = _repository(database)
    await repository.initialize()
    await repository.create_user(
        username="alice",
        email="alice@example.com",
        password_hash="hash",
    )

    with pytest.raises(AuthConflictError):
        await repository.create_user(
            username="alice",
            email="another@example.com",
            password_hash="hash",
        )
    await database.close()
