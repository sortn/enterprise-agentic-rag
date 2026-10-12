from __future__ import annotations

from datetime import UTC, datetime
import uuid

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.models import (
    AgentRun,
    AuditLog,
    Conversation,
    Document,
    DocumentVersion,
    KnowledgeBase,
    KnowledgeBaseAccess,
    Message,
    UsageRecord,
    User,
)


class EnterpriseRepository:
    """Tenant-scoped persistence; no business rules or HTTP concerns live here."""

    def __init__(self, sessions: async_sessionmaker) -> None:
        self.sessions = sessions

    async def create_knowledge_base(
        self, *, tenant_id: str, user_id: str, name: str, description: str
    ) -> KnowledgeBase:
        item = KnowledgeBase(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_by=user_id,
        )
        async with self.sessions() as session, session.begin():
            session.add(item)
            await session.flush()
            session.add(
                KnowledgeBaseAccess(
                    knowledge_base_id=item.id,
                    user_id=user_id,
                    access_level="owner",
                )
            )
        return item

    async def list_knowledge_bases(
        self, *, tenant_id: str, user_id: str, admin: bool
    ) -> list[KnowledgeBase]:
        query = select(KnowledgeBase).where(
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.status == "active",
        )
        if not admin:
            query = query.join(
                KnowledgeBaseAccess,
                KnowledgeBaseAccess.knowledge_base_id == KnowledgeBase.id,
            ).where(KnowledgeBaseAccess.user_id == user_id)
        async with self.sessions() as session:
            return list((await session.scalars(query.order_by(KnowledgeBase.name))).all())

    async def get_knowledge_base(
        self, *, knowledge_base_id: str, tenant_id: str, user_id: str, admin: bool
    ) -> KnowledgeBase | None:
        query = select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.status == "active",
        )
        if not admin:
            query = query.join(
                KnowledgeBaseAccess,
                KnowledgeBaseAccess.knowledge_base_id == KnowledgeBase.id,
            ).where(KnowledgeBaseAccess.user_id == user_id)
        async with self.sessions() as session:
            return await session.scalar(query)

    async def grant_knowledge_base_access(
        self,
        *,
        knowledge_base_id: str,
        tenant_id: str,
        user_id: str,
        access_level: str,
    ) -> KnowledgeBaseAccess:
        async with self.sessions() as session, session.begin():
            user = await session.scalar(
                select(User).where(User.id == user_id, User.tenant_id == tenant_id)
            )
            knowledge_base = await session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                    KnowledgeBase.tenant_id == tenant_id,
                )
            )
            if user is None or knowledge_base is None:
                raise LookupError("user or knowledge base does not exist in tenant")
            key = {"knowledge_base_id": knowledge_base_id, "user_id": user_id}
            access = await session.get(KnowledgeBaseAccess, key)
            if access is None:
                access = KnowledgeBaseAccess(**key, access_level=access_level)
                session.add(access)
            else:
                access.access_level = access_level
            return access

    async def grant_knowledge_base_access(
        self,
        *,
        knowledge_base_id: str,
        tenant_id: str,
        user_id: str,
        access_level: str,
    ) -> KnowledgeBaseAccess:
        async with self.sessions() as session, session.begin():
            user = await session.scalar(
                select(User).where(User.id == user_id, User.tenant_id == tenant_id)
            )
            knowledge_base = await session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                    KnowledgeBase.tenant_id == tenant_id,
                )
            )
            if user is None or knowledge_base is None:
                raise LookupError("user or knowledge base does not exist in tenant")
            key = {"knowledge_base_id": knowledge_base_id, "user_id": user_id}
            access = await session.get(KnowledgeBaseAccess, key)
            if access is None:
                access = KnowledgeBaseAccess(**key, access_level=access_level)
                session.add(access)
            else:
                access.access_level = access_level
            return access

    async def grant_knowledge_base_access(
        self,
        *,
        knowledge_base_id: str,
        tenant_id: str,
        user_id: str,
        access_level: str,
    ) -> KnowledgeBaseAccess:
        async with self.sessions() as session, session.begin():
            user = await session.scalar(
                select(User).where(User.id == user_id, User.tenant_id == tenant_id)
            )
            knowledge_base = await session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                    KnowledgeBase.tenant_id == tenant_id,
                )
            )
            if user is None or knowledge_base is None:
                raise LookupError("user or knowledge base does not exist in tenant")
            key = {"knowledge_base_id": knowledge_base_id, "user_id": user_id}
            access = await session.get(KnowledgeBaseAccess, key)
            if access is None:
                access = KnowledgeBaseAccess(**key, access_level=access_level)
                session.add(access)
            else:
                access.access_level = access_level
            return access

    async def create_document(
        self,
        *,
        document_id: str,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: str,
        title: str,
        source_name: str,
        file_type: str,
        content_hash: str,
        vector_document_id: str,
        storage_uri: str,
        chunks: int,
        status: str,
    ) -> Document:
        async with self.sessions() as session, session.begin():
            document = await session.get(Document, document_id)
            if document is None:
                document = Document(
                    id=document_id,
                    tenant_id=tenant_id,
                    knowledge_base_id=knowledge_base_id,
                    title=title,
                    source_name=source_name,
                    file_type=file_type,
                    status=status,
                    current_version=1,
                    created_by=user_id,
                )
                session.add(document)
                version = 1
            else:
                if document.tenant_id != tenant_id or document.knowledge_base_id != knowledge_base_id:
                    raise PermissionError("document belongs to a different tenant or knowledge base")
                version = document.current_version + 1
                document.current_version = version
                document.status = status
                document.updated_at = datetime.now(UTC)
                await session.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.document_id == document_id)
                    .values(is_active=False)
                )
            session.add(
                DocumentVersion(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    tenant_id=tenant_id,
                    version=version,
                    content_hash=content_hash,
                    vector_document_id=vector_document_id,
                    storage_uri=storage_uri,
                    parse_status=status,
                    chunk_count=chunks,
                    is_active=status in {"indexed", "skipped"},
                )
            )
        return document

    async def list_documents(
        self, *, tenant_id: str, knowledge_base_id: str
    ) -> list[Document]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(Document)
                .where(
                    Document.tenant_id == tenant_id,
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.status != "deleted",
                )
                .order_by(desc(Document.updated_at))
            )
            return list(result.all())

    async def mark_document_deleted(
        self, *, document_id: str, tenant_id: str, knowledge_base_id: str
    ) -> str | None:
        async with self.sessions() as session, session.begin():
            document = await session.scalar(
                select(Document).where(
                    Document.id == document_id,
                    Document.tenant_id == tenant_id,
                    Document.knowledge_base_id == knowledge_base_id,
                )
            )
            if document is None:
                return None
            vector_document_id = await session.scalar(
                select(DocumentVersion.vector_document_id).where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.version == document.current_version,
                )
            )
            document.status = "deleted"
            document.updated_at = datetime.now(UTC)
            return str(vector_document_id or document.id)

    async def create_conversation(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        knowledge_base_id: str | None,
        title: str,
    ) -> Conversation:
        conversation = Conversation(
            id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
        )
        async with self.sessions() as session, session.begin():
            session.add(conversation)
        return conversation

    async def get_conversation(
        self, *, conversation_id: str, tenant_id: str, user_id: str
    ) -> Conversation | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                    Conversation.user_id == user_id,
                    Conversation.status == "active",
                )
            )

    async def list_conversations(
        self, *, tenant_id: str, user_id: str, limit: int = 50
    ) -> list[Conversation]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(Conversation)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.user_id == user_id,
                    Conversation.status == "active",
                )
                .order_by(desc(Conversation.updated_at))
                .limit(limit)
            )
            return list(result.all())

    async def add_message(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        role: str,
        content: str,
        citations: list[dict] | None = None,
        run_id: str | None = None,
    ) -> Message:
        message = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
            citations_json=citations or [],
            run_id=run_id,
        )
        async with self.sessions() as session, session.begin():
            session.add(message)
            conversation = await session.get(Conversation, conversation_id)
            if conversation:
                conversation.updated_at = datetime.now(UTC)
        return message

    async def recent_messages(
        self, *, conversation_id: str, tenant_id: str, limit: int = 12
    ) -> list[Message]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.tenant_id == tenant_id,
                )
                .order_by(desc(Message.created_at))
                .limit(limit)
            )
            return list(reversed(result.all()))

    async def create_agent_run(self, **values) -> AgentRun:
        run = AgentRun(**values)
        async with self.sessions() as session, session.begin():
            session.add(run)
        return run

    async def finish_agent_run(self, run_id: str, **values) -> None:
        async with self.sessions() as session, session.begin():
            run = await session.get(AgentRun, run_id)
            if run:
                for key, value in values.items():
                    setattr(run, key, value)
                run.completed_at = datetime.now(UTC)

    async def list_agent_runs(
        self, *, tenant_id: str, limit: int = 100
    ) -> list[AgentRun]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(AgentRun)
                .where(AgentRun.tenant_id == tenant_id)
                .order_by(desc(AgentRun.started_at))
                .limit(limit)
            )
            return list(result.all())

    async def list_agent_runs(
        self, *, tenant_id: str, limit: int = 100
    ) -> list[AgentRun]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(AgentRun)
                .where(AgentRun.tenant_id == tenant_id)
                .order_by(desc(AgentRun.started_at))
                .limit(limit)
            )
            return list(result.all())

    async def add_usage(self, **values) -> UsageRecord:
        record = UsageRecord(id=str(uuid.uuid4()), **values)
        async with self.sessions() as session, session.begin():
            session.add(record)
        return record

    async def add_audit(self, **values) -> AuditLog:
        record = AuditLog(id=str(uuid.uuid4()), **values)
        async with self.sessions() as session, session.begin():
            session.add(record)
        return record

    async def list_audit_logs(
        self, *, tenant_id: str, limit: int = 100
    ) -> list[AuditLog]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(desc(AuditLog.created_at))
                .limit(limit)
            )
            return list(result.all())

    async def list_audit_logs(
        self, *, tenant_id: str, limit: int = 100
    ) -> list[AuditLog]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(desc(AuditLog.created_at))
                .limit(limit)
            )
            return list(result.all())
