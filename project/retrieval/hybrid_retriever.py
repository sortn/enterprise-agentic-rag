"""Dense, hybrid and cross-encoder-reranked retrieval pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Literal

from redis import Redis
from redis.exceptions import RedisError

from config import Settings, get_settings
from services.model_clients import SiliconFlowEmbeddings, SiliconFlowReranker
from .milvus_store import MilvusStore, SearchHit

logger = logging.getLogger(__name__)

RetrievalMode = Literal["dense", "hybrid", "hybrid_rerank"]


class HybridRetriever:
    def __init__(
        self,
        store: MilvusStore,
        embeddings: SiliconFlowEmbeddings,
        reranker: SiliconFlowReranker,
        settings: Settings | None = None,
    ):
        self.store = store
        self.embeddings = embeddings
        self.reranker = reranker
        self.settings = settings or get_settings()
        redis_url = getattr(self.settings, "redis_url", "")
        self.cache = Redis.from_url(redis_url, decode_responses=True) if redis_url else None
        self._local = threading.local()

    def retrieve(
        self,
        query: str,
        mode: RetrievalMode = "hybrid_rerank",
        top_k: int | None = None,
        query_vector: list[float] | None = None,
        tenant_id: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> list[SearchHit]:
        query = query.strip()
        if not query:
            return []
        cache_key = self._cache_key(
            query, mode, top_k, tenant_id, knowledge_base_id
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            self._local.trace = {"cache_hit": True, "retrieval_latency_ms": 0.0, "reranker_latency_ms": 0.0}
            return cached
        trace = {"cache_hit": False, "embedding_latency_ms": 0.0, "retrieval_latency_ms": 0.0, "reranker_latency_ms": 0.0}
        vector = query_vector
        embedding_error: Exception | None = None
        if vector is None:
            try:
                started = time.perf_counter()
                vector = self.embeddings.embed_query(query)
                trace["embedding_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            except Exception as exc:
                embedding_error = exc
                logger.warning("Embedding failed; trying BM25-only retrieval: %s", exc)

        if mode == "dense":
            if vector is None:
                raise RuntimeError("dense retrieval unavailable because embedding failed") from embedding_error
            started = time.perf_counter()
            results = self.store.search_dense(
                vector,
                limit=top_k or self.settings.rerank_top_k,
                **self._scope_kwargs(tenant_id, knowledge_base_id),
            )
            trace["retrieval_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            self._local.trace = trace
            self._cache_set(cache_key, results)
            return results

        candidate_limit = max(top_k or self.settings.fusion_top_k, self.settings.rerank_top_k)
        candidates: list[SearchHit] = []
        hybrid_error: Exception | None = None
        if vector is not None:
            try:
                started = time.perf_counter()
                candidates = self.store.search_hybrid(
                    query,
                    vector,
                    limit=candidate_limit,
                    **self._scope_kwargs(tenant_id, knowledge_base_id),
                )
                trace["retrieval_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            except Exception as exc:
                hybrid_error = exc
                logger.warning("Milvus hybrid search failed; trying single routes: %s", exc)

        if vector is None or hybrid_error is not None:
            candidates = self._degraded_retrieve(
                query,
                vector,
                candidate_limit,
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
            )
        if not candidates and hybrid_error is not None:
            raise RuntimeError("hybrid, dense and BM25 retrieval all failed") from hybrid_error

        if mode == "hybrid" or not candidates:
            results = candidates[: top_k or self.settings.rerank_top_k]
            self._local.trace = trace
            self._cache_set(cache_key, results)
            return results

        try:
            started = time.perf_counter()
            rankings = self.reranker.rerank(
                query,
                [hit.text for hit in candidates],
                top_n=top_k or self.settings.rerank_top_k,
            )
            trace["reranker_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        except Exception as exc:
            logger.warning("Reranker failed; returning RRF order: %s", exc)
            results = candidates[: top_k or self.settings.rerank_top_k]
            self._local.trace = trace
            self._cache_set(cache_key, results)
            return results

        reranked: list[SearchHit] = []
        for item in rankings:
            hit = candidates[item.index]
            hit.rerank_score = item.score
            hit.retrieval_method = "hybrid_rrf_bge_rerank"
            reranked.append(hit)
        self._cache_set(cache_key, reranked)
        self._local.trace = trace
        return reranked

    def _degraded_retrieve(
        self,
        query: str,
        vector: list[float] | None,
        limit: int,
        *,
        tenant_id: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> list[SearchHit]:
        dense_hits: list[SearchHit] = []
        sparse_hits: list[SearchHit] = []
        if vector is not None:
            try:
                dense_hits = self.store.search_dense(
                    vector,
                    limit=limit,
                    **self._scope_kwargs(tenant_id, knowledge_base_id),
                )
            except Exception as exc:
                logger.warning("Dense fallback failed: %s", exc)
        try:
            sparse_hits = self.store.search_sparse(
                query,
                limit=limit,
                **self._scope_kwargs(tenant_id, knowledge_base_id),
            )
        except Exception as exc:
            logger.warning("BM25 fallback failed: %s", exc)

        if dense_hits and sparse_hits:
            by_id: dict[str, SearchHit] = {}
            scores: dict[str, float] = {}
            for ranking in (dense_hits, sparse_hits):
                for rank, hit in enumerate(ranking, start=1):
                    by_id.setdefault(hit.id, hit)
                    scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (self.settings.rrf_k + rank)
            fused = sorted(by_id.values(), key=lambda hit: scores[hit.id], reverse=True)
            for hit in fused:
                hit.score = scores[hit.id]
                hit.retrieval_method = "fallback_rrf"
            return fused[:limit]
        if sparse_hits:
            for hit in sparse_hits:
                hit.retrieval_method = "bm25_degraded"
            return sparse_hits[:limit]
        if dense_hits:
            for hit in dense_hits:
                hit.retrieval_method = "dense_degraded"
            return dense_hits[:limit]
        return []

    @staticmethod
    def _scope_kwargs(
        tenant_id: str | None, knowledge_base_id: str | None
    ) -> dict[str, str]:
        # Omitting empty keyword arguments preserves compatibility with the
        # benchmark/test stores while production always passes verified scope.
        values = {}
        if tenant_id:
            values["tenant_id"] = tenant_id
        if knowledge_base_id:
            values["knowledge_base_id"] = knowledge_base_id
        return values

    def _cache_key(
        self,
        query: str,
        mode: str,
        top_k: int | None,
        tenant_id: str | None,
        knowledge_base_id: str | None,
    ) -> str | None:
        if self.cache is None or not tenant_id or not knowledge_base_id:
            return None
        payload = f"{mode}:{top_k or 0}:{query.strip()}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"retrieval:{tenant_id}:{knowledge_base_id}:{digest}"

    def _cache_get(self, key: str | None) -> list[SearchHit] | None:
        if not key or self.cache is None:
            return None
        try:
            raw = self.cache.get(key)
            if not raw:
                return None
            return [SearchHit(**item) for item in json.loads(raw)]
        except (RedisError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _cache_set(self, key: str | None, hits: list[SearchHit]) -> None:
        if not key or self.cache is None:
            return
        try:
            self.cache.set(
                key,
                json.dumps([hit.to_dict() for hit in hits], ensure_ascii=False),
                ex=int(getattr(self.settings, "retrieval_cache_ttl_seconds", 300)),
            )
        except RedisError:
            return

    def last_trace(self) -> dict[str, float | bool]:
        return dict(getattr(self._local, "trace", {}))
