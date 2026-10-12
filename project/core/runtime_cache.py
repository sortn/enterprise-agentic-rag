from __future__ import annotations

import hashlib
import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError


class RuntimeCache:
    """Redis short-term state. PostgreSQL remains the source of truth."""

    def __init__(
        self,
        redis_url: str,
        *,
        conversation_ttl: int,
        conversation_limit: int,
        retrieval_ttl: int,
        permission_ttl: int,
    ) -> None:
        self.client = Redis.from_url(redis_url, decode_responses=True)
        self.conversation_ttl = conversation_ttl
        self.conversation_limit = conversation_limit
        self.retrieval_ttl = retrieval_ttl
        self.permission_ttl = permission_ttl

    async def get_conversation(self, conversation_id: str) -> list[dict[str, Any]] | None:
        return await self._get_json(f"chat:context:{conversation_id}")

    async def set_conversation(
        self, conversation_id: str, messages: list[dict[str, Any]]
    ) -> None:
        await self._set_json(
            f"chat:context:{conversation_id}",
            messages[-self.conversation_limit :],
            self.conversation_ttl,
        )

    async def get_permissions(self, user_id: str) -> list[str] | None:
        return await self._get_json(f"permission:{user_id}")

    async def set_permissions(self, user_id: str, permissions: list[str]) -> None:
        await self._set_json(
            f"permission:{user_id}", permissions, self.permission_ttl
        )

    async def invalidate_permissions(self, user_id: str) -> None:
        await self.client.delete(f"permission:{user_id}")

    @staticmethod
    def retrieval_key(tenant_id: str, knowledge_base_id: str, query: str) -> str:
        digest = hashlib.sha256(query.strip().encode("utf-8")).hexdigest()
        return f"retrieval:{tenant_id}:{knowledge_base_id}:{digest}"

    async def get_retrieval(
        self, tenant_id: str, knowledge_base_id: str, query: str
    ) -> list[dict[str, Any]] | None:
        return await self._get_json(self.retrieval_key(tenant_id, knowledge_base_id, query))

    async def set_retrieval(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        query: str,
        hits: list[dict[str, Any]],
    ) -> None:
        await self._set_json(
            self.retrieval_key(tenant_id, knowledge_base_id, query),
            hits,
            self.retrieval_ttl,
        )

    async def invalidate_knowledge_base(self, tenant_id: str, knowledge_base_id: str) -> int:
        pattern = f"retrieval:{tenant_id}:{knowledge_base_id}:*"
        removed = 0
        async for key in self.client.scan_iter(match=pattern, count=200):
            removed += int(await self.client.delete(key))
        return removed

    async def ping(self) -> bool:
        return bool(await self.client.ping())

    async def close(self) -> None:
        await self.client.aclose()

    async def _get_json(self, key: str):
        try:
            raw = await self.client.get(key)
        except RedisError:
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    async def _set_json(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self.client.set(
                key,
                json.dumps(value, ensure_ascii=False),
                ex=ttl,
            )
        except RedisError:
            # Cache failure must not make the source-of-truth operation fail.
            return
