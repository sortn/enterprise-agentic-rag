from __future__ import annotations

from dataclasses import dataclass

from auth.container import AuthContainer, build_auth_container
from config import Settings
from database.session import DatabaseManager
from repositories.enterprise import EnterpriseRepository
from services.enterprise import (
    AuditService,
    ChatService,
    ConversationService,
    DocumentService,
    EvaluationService,
    KnowledgeBaseService,
)
from .observability import Observability
from .rag_system import RAGSystem
from .runtime_cache import RuntimeCache


@dataclass
class ApplicationServices:
    settings: Settings
    database: DatabaseManager
    cache: RuntimeCache
    auth: AuthContainer
    rag: RAGSystem
    repository: EnterpriseRepository
    knowledge_bases: KnowledgeBaseService
    conversations: ConversationService
    chat: ChatService
    documents: DocumentService
    audit: AuditService
    evaluation: EvaluationService
    observability: Observability

    async def startup(self) -> None:
        await self.database.initialize()
        await self.auth.service.initialize()

    async def shutdown(self) -> None:
        self.observability.flush()
        await self.auth.refresh_tokens.close()
        await self.cache.close()
        await self.database.close()


def build_application_services(settings: Settings) -> ApplicationServices:
    database = DatabaseManager(settings)
    cache = RuntimeCache(
        settings.redis_url,
        conversation_ttl=settings.conversation_cache_ttl_seconds,
        conversation_limit=settings.conversation_cache_messages,
        retrieval_ttl=settings.retrieval_cache_ttl_seconds,
        permission_ttl=settings.permission_cache_ttl_seconds,
    )
    auth = build_auth_container(settings, database)
    rag = RAGSystem(settings)
    repository = EnterpriseRepository(database.sessions)
    knowledge_bases = KnowledgeBaseService(repository)
    conversations = ConversationService(repository, cache, settings)
    return ApplicationServices(
        settings=settings,
        database=database,
        cache=cache,
        auth=auth,
        rag=rag,
        repository=repository,
        knowledge_bases=knowledge_bases,
        conversations=conversations,
        chat=ChatService(rag, repository, knowledge_bases, conversations, settings),
        documents=DocumentService(rag, repository, knowledge_bases, cache, settings),
        audit=AuditService(repository),
        evaluation=EvaluationService(repository),
        observability=rag.observability,
    )
