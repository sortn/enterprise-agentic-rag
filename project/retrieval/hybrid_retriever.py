"""Dense, hybrid and cross-encoder-reranked retrieval pipeline."""

from __future__ import annotations

import logging
from typing import Literal

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

    def retrieve(
        self,
        query: str,
        mode: RetrievalMode = "hybrid_rerank",
        top_k: int | None = None,
        query_vector: list[float] | None = None,
    ) -> list[SearchHit]:
        query = query.strip()
        if not query:
            return []
        vector = query_vector
        embedding_error: Exception | None = None
        if vector is None:
            try:
                vector = self.embeddings.embed_query(query)
            except Exception as exc:
                embedding_error = exc
                logger.warning("Embedding failed; trying BM25-only retrieval: %s", exc)

        if mode == "dense":
            if vector is None:
                raise RuntimeError("dense retrieval unavailable because embedding failed") from embedding_error
            return self.store.search_dense(vector, limit=top_k or self.settings.rerank_top_k)

        candidate_limit = max(top_k or self.settings.fusion_top_k, self.settings.rerank_top_k)
        candidates: list[SearchHit] = []
        hybrid_error: Exception | None = None
        if vector is not None:
            try:
                candidates = self.store.search_hybrid(query, vector, limit=candidate_limit)
            except Exception as exc:
                hybrid_error = exc
                logger.warning("Milvus hybrid search failed; trying single routes: %s", exc)

        if vector is None or hybrid_error is not None:
            candidates = self._degraded_retrieve(query, vector, candidate_limit)
        if not candidates and hybrid_error is not None:
            raise RuntimeError("hybrid, dense and BM25 retrieval all failed") from hybrid_error

        if mode == "hybrid" or not candidates:
            return candidates[: top_k or self.settings.rerank_top_k]

        try:
            rankings = self.reranker.rerank(
                query,
                [hit.text for hit in candidates],
                top_n=top_k or self.settings.rerank_top_k,
            )
        except Exception as exc:
            logger.warning("Reranker failed; returning RRF order: %s", exc)
            return candidates[: top_k or self.settings.rerank_top_k]

        reranked: list[SearchHit] = []
        for item in rankings:
            hit = candidates[item.index]
            hit.rerank_score = item.score
            hit.retrieval_method = "hybrid_rrf_bge_rerank"
            reranked.append(hit)
        return reranked

    def _degraded_retrieve(
        self,
        query: str,
        vector: list[float] | None,
        limit: int,
    ) -> list[SearchHit]:
        dense_hits: list[SearchHit] = []
        sparse_hits: list[SearchHit] = []
        if vector is not None:
            try:
                dense_hits = self.store.search_dense(vector, limit=limit)
            except Exception as exc:
                logger.warning("Dense fallback failed: %s", exc)
        try:
            sparse_hits = self.store.search_sparse(query, limit=limit)
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
