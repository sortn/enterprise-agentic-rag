from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import time
import uuid

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from auth.models import UserContext
from config import Settings
from core.observability import current_request_id, run_id_var
from core.runtime_cache import RuntimeCache
from repositories.enterprise import EnterpriseRepository
from .errors import AccessDenied, AgentExecutionError, DocumentProcessingError, ResourceNotFound


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def serialize_knowledge_base(item) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "name": item.name,
        "description": item.description,
        "status": item.status,
        "created_by": item.created_by,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def serialize_document(item) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "knowledge_base_id": item.knowledge_base_id,
        "title": item.title,
        "source_name": item.source_name,
        "file_type": item.file_type,
        "status": item.status,
        "current_version": item.current_version,
        "created_by": item.created_by,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def serialize_conversation(item) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "user_id": item.user_id,
        "knowledge_base_id": item.knowledge_base_id,
        "title": item.title,
        "status": item.status,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def serialize_message(item) -> dict:
    return {
        "id": item.id,
        "conversation_id": item.conversation_id,
        "role": item.role,
        "content": item.content,
        "citations": item.citations_json,
        "run_id": item.run_id,
        "created_at": _iso(item.created_at),
    }


class KnowledgeBaseService:
    def __init__(self, repository: EnterpriseRepository) -> None:
        self.repository = repository

    async def create(self, context: UserContext, name: str, description: str) -> dict:
        item = await self.repository.create_knowledge_base(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            name=name.strip(),
            description=description.strip(),
        )
        await self.repository.add_audit(
            request_id=current_request_id(),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            action="CREATE_KNOWLEDGE_BASE",
            object_type="knowledge_base",
            object_id=item.id,
            outcome="success",
            detail_json={"name": item.name},
        )
        return serialize_knowledge_base(item)

    async def list(self, context: UserContext) -> list[dict]:
        items = await self.repository.list_knowledge_bases(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            admin=context.role == "admin",
        )
        return [serialize_knowledge_base(item) for item in items]

    async def require(self, context: UserContext, knowledge_base_id: str) -> object:
        item = await self.repository.get_knowledge_base(
            knowledge_base_id=knowledge_base_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            admin=context.role == "admin",
        )
        if item is None:
            raise AccessDenied("知识库不存在或当前用户没有访问权限")
        return item

    async def grant(
        self,
        context: UserContext,
        knowledge_base_id: str,
        user_id: str,
        access_level: str,
    ) -> dict:
        await self.require(context, knowledge_base_id)
        try:
            access = await self.repository.grant_knowledge_base_access(
                knowledge_base_id=knowledge_base_id,
                tenant_id=context.tenant_id,
                user_id=user_id,
                access_level=access_level,
            )
        except LookupError as exc:
            raise ResourceNotFound("用户或知识库不存在") from exc
        await self.repository.add_audit(
            request_id=current_request_id(),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            action="GRANT_KNOWLEDGE_BASE_ACCESS",
            object_type="knowledge_base",
            object_id=knowledge_base_id,
            outcome="success",
            detail_json={"target_user_id": user_id, "access_level": access_level},
        )
        return {
            "knowledge_base_id": access.knowledge_base_id,
            "user_id": access.user_id,
            "access_level": access.access_level,
        }

    async def resolve(self, context: UserContext, knowledge_base_id: str | None) -> object:
        if knowledge_base_id:
            return await self.require(context, knowledge_base_id)
        available = await self.repository.list_knowledge_bases(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            admin=context.role == "admin",
        )
        if available:
            return available[0]
        if context.role != "admin":
            raise AccessDenied("当前账号尚未被分配知识库")
        return await self.repository.create_knowledge_base(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            name="默认知识库",
            description="系统首次使用时创建的默认知识库",
        )


class ConversationService:
    def __init__(
        self, repository: EnterpriseRepository, cache: RuntimeCache, settings: Settings
    ) -> None:
        self.repository = repository
        self.cache = cache
        self.settings = settings

    async def ensure(
        self,
        context: UserContext,
        conversation_id: str | None,
        knowledge_base_id: str | None,
        question: str,
    ):
        if conversation_id:
            item = await self.repository.get_conversation(
                conversation_id=conversation_id,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
            )
            if item is not None:
                if knowledge_base_id and item.knowledge_base_id != knowledge_base_id:
                    raise AccessDenied("对话与知识库不匹配")
                return item
            # Client-generated ids (e.g. the Gradio thread_id) are adopted so the
            # first message creates the conversation under that id.
        return await self.repository.create_conversation(
            conversation_id=conversation_id or str(uuid.uuid4()),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            knowledge_base_id=knowledge_base_id,
            title=question.strip()[:50] or "新对话",
        )

    async def list(self, context: UserContext) -> list[dict]:
        items = await self.repository.list_conversations(
            tenant_id=context.tenant_id, user_id=context.user_id
        )
        return [serialize_conversation(item) for item in items]

    async def detail(self, context: UserContext, conversation_id: str) -> dict:
        item = await self.repository.get_conversation(
            conversation_id=conversation_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
        if item is None:
            raise ResourceNotFound("对话不存在")
        messages = await self._messages(conversation_id, context.tenant_id)
        return {**serialize_conversation(item), "messages": messages}

    async def append(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        role: str,
        content: str,
        citations: list[dict] | None = None,
        run_id: str | None = None,
    ) -> None:
        await self.repository.add_message(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
            citations=citations,
            run_id=run_id,
        )
        messages = await self.repository.recent_messages(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            limit=self.settings.conversation_cache_messages,
        )
        await self.cache.set_conversation(
            conversation_id, [serialize_message(item) for item in messages]
        )

    async def _messages(self, conversation_id: str, tenant_id: str) -> list[dict]:
        cached = await self.cache.get_conversation(conversation_id)
        if cached is not None:
            return cached
        messages = await self.repository.recent_messages(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            limit=self.settings.conversation_cache_messages,
        )
        serialized = [serialize_message(item) for item in messages]
        await self.cache.set_conversation(conversation_id, serialized)
        return serialized


class ChatService:
    def __init__(
        self,
        rag,
        repository: EnterpriseRepository,
        knowledge_bases: KnowledgeBaseService,
        conversations: ConversationService,
        settings: Settings,
    ) -> None:
        self.rag = rag
        self.repository = repository
        self.knowledge_bases = knowledge_bases
        self.conversations = conversations
        self.settings = settings

    async def chat(
        self,
        *,
        context: UserContext,
        question: str,
        conversation_id: str | None,
        knowledge_base_id: str | None,
    ) -> dict:
        knowledge_base = await self.knowledge_bases.resolve(context, knowledge_base_id)
        conversation = await self.conversations.ensure(
            context, conversation_id, knowledge_base.id, question
        )
        run_id = str(uuid.uuid4())
        request_id = current_request_id()
        run_token = run_id_var.set(run_id)
        started = time.perf_counter()
        await self.conversations.append(
            conversation_id=conversation.id,
            tenant_id=context.tenant_id,
            role="user",
            content=question,
        )
        await self.repository.create_agent_run(
            id=run_id,
            request_id=request_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            conversation_id=conversation.id,
            question=question,
            model=self.settings.llm_model,
            final_status="running",
        )
        agent_context = context.to_agent_context()
        agent_context["knowledge_base_id"] = knowledge_base.id
        try:
            result = await run_in_threadpool(
                self.rag.chat,
                question,
                conversation.id,
                agent_context,
            )
            total_ms = round((time.perf_counter() - started) * 1000, 3)
            await self.conversations.append(
                conversation_id=conversation.id,
                tenant_id=context.tenant_id,
                role="assistant",
                content=str(result.get("answer", "")),
                citations=list(result.get("citations", [])),
                run_id=run_id,
            )
            state = {
                "intent": result.get("intent", ""),
                "rewritten_query": result.get("rewritten_query", ""),
                "citations": result.get("citations", []),
                "grounded": bool(result.get("grounded", False)),
                "refused": bool(result.get("refused", False)),
            }
            attempts = int(result.get("retrieval_attempts", 0))
            retrieval_metrics = result.get("retrieval_metrics", {})
            await self.repository.finish_agent_run(
                run_id,
                route=str(result.get("intent", "")),
                rewrite_triggered=(
                    bool(result.get("rewritten_query"))
                    and result.get("rewritten_query") != question
                ),
                retrieve_count=attempts,
                rerank_count=attempts,
                retry_count=max(0, attempts - 1),
                retrieval_latency_ms=float(
                    retrieval_metrics.get("retrieval_latency_ms", 0.0)
                ),
                reranker_latency_ms=float(
                    retrieval_metrics.get("reranker_latency_ms", 0.0)
                ),
                llm_latency_ms=float(result.get("llm_latency_ms", 0.0)),
                prompt_tokens=int(result.get("prompt_tokens", 0)),
                completion_tokens=int(result.get("completion_tokens", 0)),
                total_latency_ms=total_ms,
                final_status="refused" if result.get("refused") else "success",
                state_json=state,
            )
            await self.repository.add_usage(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                run_id=run_id,
                model=self.settings.llm_model,
                prompt_tokens=int(result.get("prompt_tokens", 0)),
                completion_tokens=int(result.get("completion_tokens", 0)),
                estimated_cost=0.0,
            )
            await self.repository.add_audit(
                request_id=request_id,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                action="RUN_AGENT",
                object_type="conversation",
                object_id=conversation.id,
                outcome="success",
                detail_json={"run_id": run_id, "knowledge_base_id": knowledge_base.id},
            )
            return {
                **result,
                "thread_id": conversation.id,
                "conversation_id": conversation.id,
                "run_id": run_id,
                "request_id": request_id,
            }
        except Exception as exc:
            await self.repository.finish_agent_run(
                run_id,
                total_latency_ms=round((time.perf_counter() - started) * 1000, 3),
                final_status="failed",
                error_code=type(exc).__name__,
                state_json={},
            )
            await self.repository.add_audit(
                request_id=request_id,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                action="RUN_AGENT",
                object_type="conversation",
                object_id=conversation.id,
                outcome="failed",
                detail_json={"run_id": run_id, "error": type(exc).__name__},
            )
            raise AgentExecutionError() from exc
        finally:
            run_id_var.reset(run_token)


class AuditService:
    def __init__(self, repository: EnterpriseRepository) -> None:
        self.repository = repository

    async def list(self, context: UserContext, limit: int) -> list[dict]:
        records = await self.repository.list_audit_logs(
            tenant_id=context.tenant_id, limit=min(max(limit, 1), 500)
        )
        return [
            {
                "id": item.id,
                "request_id": item.request_id,
                "tenant_id": item.tenant_id,
                "user_id": item.user_id,
                "action": item.action,
                "object_type": item.object_type,
                "object_id": item.object_id,
                "outcome": item.outcome,
                "detail": item.detail_json,
                "created_at": _iso(item.created_at),
            }
            for item in records
        ]


class EvaluationService:
    def __init__(self, repository: EnterpriseRepository) -> None:
        self.repository = repository

    async def runs(self, context: UserContext, limit: int) -> list[dict]:
        records = await self.repository.list_agent_runs(
            tenant_id=context.tenant_id, limit=min(max(limit, 1), 500)
        )
        return [
            {
                "run_id": item.id,
                "request_id": item.request_id,
                "conversation_id": item.conversation_id,
                "question": item.question,
                "route": item.route,
                "rewrite_triggered": item.rewrite_triggered,
                "retrieval_attempts": item.retrieve_count,
                "retry_count": item.retry_count,
                "retrieval_latency_ms": item.retrieval_latency_ms or 0.0,
                "reranker_latency_ms": item.reranker_latency_ms or 0.0,
                "llm_latency_ms": item.llm_latency_ms or 0.0,
                "total_latency_ms": item.total_latency_ms,
                "prompt_tokens": item.prompt_tokens,
                "completion_tokens": item.completion_tokens,
                "final_status": item.final_status,
                "error": item.error_code or "",
                **(item.state_json or {}),
            }
            for item in records
        ]


class DocumentService:
    def __init__(
        self,
        rag,
        repository: EnterpriseRepository,
        knowledge_bases: KnowledgeBaseService,
        cache: RuntimeCache,
        settings: Settings,
    ) -> None:
        self.rag = rag
        self.repository = repository
        self.knowledge_bases = knowledge_bases
        self.cache = cache
        self.settings = settings

    async def list(
        self, context: UserContext, knowledge_base_id: str | None
    ) -> list[dict]:
        kb = await self.knowledge_bases.resolve(context, knowledge_base_id)
        items = await self.repository.list_documents(
            tenant_id=context.tenant_id, knowledge_base_id=kb.id
        )
        return [serialize_document(item) for item in items]

    async def upload(
        self,
        context: UserContext,
        files: list[UploadFile],
        knowledge_base_id: str | None,
    ) -> list[dict]:
        kb = await self.knowledge_bases.resolve(context, knowledge_base_id)
        rag = await run_in_threadpool(self.rag.initialize)
        results: list[dict] = []
        for upload in files:
            filename = Path(upload.filename or "").name
            suffix = Path(filename).suffix.lower()
            if not filename or suffix not in self.settings.allowed_extensions:
                raise DocumentProcessingError(f"不支持的文件：{filename}")
            scoped_directory = self.settings.upload_dir / context.tenant_id / kb.id
            scoped_directory.mkdir(parents=True, exist_ok=True)
            temporary = scoped_directory / f".{uuid.uuid4().hex}.uploading"
            destination: Path | None = None
            digest = hashlib.sha256()
            written = 0
            try:
                with temporary.open("wb") as target:
                    while block := await upload.read(1024 * 1024):
                        written += len(block)
                        if written > self.settings.max_upload_mb * 1024 * 1024:
                            raise DocumentProcessingError(
                                f"{filename} 超过 {self.settings.max_upload_mb} MB 限制"
                            )
                        digest.update(block)
                        target.write(block)
                content_hash = digest.hexdigest()
                destination = scoped_directory / f"{content_hash[:16]}_{filename}"
                temporary.replace(destination)
                result = await run_in_threadpool(
                    rag.ingestion.ingest,
                    destination,
                    False,
                    context.tenant_id,
                    kb.id,
                    filename,
                )
                stable_document_id = hashlib.sha256(
                    f"{context.tenant_id}:{kb.id}:{filename.lower()}".encode("utf-8")
                ).hexdigest()[:24]
                document = await self.repository.create_document(
                    document_id=stable_document_id,
                    tenant_id=context.tenant_id,
                    knowledge_base_id=kb.id,
                    user_id=context.user_id,
                    title=Path(filename).stem,
                    source_name=filename,
                    file_type=suffix.lstrip("."),
                    content_hash=content_hash,
                    vector_document_id=result.doc_id,
                    storage_uri=str(destination),
                    chunks=result.chunks,
                    status=result.status,
                )
                await self.cache.invalidate_knowledge_base(context.tenant_id, kb.id)
                await self.repository.add_audit(
                    request_id=current_request_id(),
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    action="UPLOAD_DOCUMENT",
                    object_type="document",
                    object_id=stable_document_id,
                    outcome="success",
                    detail_json={"knowledge_base_id": kb.id, "chunks": result.chunks},
                )
                results.append({**serialize_document(document), "chunks": result.chunks})
            except DocumentProcessingError:
                temporary.unlink(missing_ok=True)
                raise
            except Exception as exc:
                temporary.unlink(missing_ok=True)
                if destination is not None:
                    destination.unlink(missing_ok=True)
                raise DocumentProcessingError(f"{filename} 入库失败") from exc
        return results

    async def delete(
        self,
        context: UserContext,
        document_id: str,
        knowledge_base_id: str | None,
    ) -> None:
        kb = await self.knowledge_bases.resolve(context, knowledge_base_id)
        vector_document_id = await self.repository.mark_document_deleted(
            document_id=document_id,
            tenant_id=context.tenant_id,
            knowledge_base_id=kb.id,
        )
        if not vector_document_id:
            raise ResourceNotFound("文档不存在")
        rag = await run_in_threadpool(self.rag.initialize)
        await run_in_threadpool(
            rag.delete_document,
            vector_document_id,
            context.tenant_id,
            kb.id,
        )
        await self.cache.invalidate_knowledge_base(context.tenant_id, kb.id)
        await self.repository.add_audit(
            request_id=current_request_id(),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            action="DELETE_DOCUMENT",
            object_type="document",
            object_id=document_id,
            outcome="success",
            detail_json={"knowledge_base_id": kb.id},
        )
