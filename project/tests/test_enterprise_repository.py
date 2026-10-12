from __future__ import annotations

import pytest

from auth.repository import SQLAlchemyAuthRepository
from core.container import build_application_services
from database.session import DatabaseManager
from repositories.enterprise import EnterpriseRepository


@pytest.mark.asyncio
async def test_async_repository_persists_tenant_scoped_kb_conversation_and_messages(postgres_settings):
    database = DatabaseManager(postgres_settings)
    await database.initialize()
    auth = SQLAlchemyAuthRepository(
        database.sessions,
        default_tenant_id=postgres_settings.auth_default_tenant_id,
        default_tenant_name="测试企业",
    )
    await auth.initialize()
    user = await auth.create_user(
        username="owner",
        email="owner@example.com",
        password_hash="$argon2id$test",
        role="admin",
    )

    repository = EnterpriseRepository(database.sessions)
    knowledge_base = await repository.create_knowledge_base(
        tenant_id=user.tenant_id,
        user_id=user.id,
        name="制度库",
        description="企业制度",
    )
    visible = await repository.list_knowledge_bases(
        tenant_id=user.tenant_id,
        user_id=user.id,
        admin=False,
    )
    assert [item.id for item in visible] == [knowledge_base.id]

    conversation = await repository.create_conversation(
        conversation_id="conversation-1",
        tenant_id=user.tenant_id,
        user_id=user.id,
        knowledge_base_id=knowledge_base.id,
        title="测试对话",
    )
    await repository.add_message(
        conversation_id=conversation.id,
        tenant_id=user.tenant_id,
        role="user",
        content="报销期限是多少？",
    )
    messages = await repository.recent_messages(
        conversation_id=conversation.id,
        tenant_id=user.tenant_id,
    )
    assert [(item.role, item.content) for item in messages] == [
        ("user", "报销期限是多少？")
    ]

    first = await repository.create_document(
        document_id="stable-document",
        tenant_id=user.tenant_id,
        knowledge_base_id=knowledge_base.id,
        user_id=user.id,
        title="制度",
        source_name="制度.pdf",
        file_type="pdf",
        content_hash="hash-v1",
        vector_document_id="a" * 24,
        storage_uri="local/v1.pdf",
        chunks=3,
        status="indexed",
    )
    second = await repository.create_document(
        document_id="stable-document",
        tenant_id=user.tenant_id,
        knowledge_base_id=knowledge_base.id,
        user_id=user.id,
        title="制度",
        source_name="制度.pdf",
        file_type="pdf",
        content_hash="hash-v2",
        vector_document_id="b" * 24,
        storage_uri="local/v2.pdf",
        chunks=4,
        status="indexed",
    )
    assert first.id == second.id
    assert second.current_version == 2
    current_vector = await repository.mark_document_deleted(
        document_id=second.id,
        tenant_id=user.tenant_id,
        knowledge_base_id=knowledge_base.id,
    )
    assert current_vector == "b" * 24
    await database.close()


@pytest.mark.asyncio
async def test_application_lifespan_initializes_schema_and_rbac(postgres_settings):
    services = build_application_services(postgres_settings)
    await services.startup()
    assert await services.database.ping() is True
    assert await services.auth.repository.ping() is True
    await services.shutdown()
