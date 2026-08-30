"""SiliconFlow adapters with timeouts, retries and typed return values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import httpx
from langchain_openai import ChatOpenAI
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import Settings, get_settings


@dataclass(frozen=True)
class RerankItem:
    index: int
    score: float


def build_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    """Create the OpenAI-compatible chat client used by LangGraph."""
    settings = settings or get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.require_api_key(),
        base_url=settings.siliconflow_base_url,
        temperature=settings.llm_temperature,
        timeout=settings.request_timeout_seconds,
        max_retries=settings.request_max_retries,
        seed=42,
        max_tokens=settings.llm_max_tokens,
        extra_body={"enable_thinking": False},
        streaming=True,
    )


class SiliconFlowEmbeddings:
    """Small LangChain-compatible embedding adapter for BAAI/bge-m3."""

    def __init__(self, settings: Settings | None = None, batch_size: int = 32):
        self.settings = settings or get_settings()
        self.batch_size = batch_size
        self.client = OpenAI(
            api_key=self.settings.require_api_key(),
            base_url=self.settings.siliconflow_base_url,
            timeout=self.settings.request_timeout_seconds,
            max_retries=0,
        )

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError, ConnectionError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=list(texts),
            encoding_format="float",
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [item.embedding for item in ordered]
        for vector in vectors:
            if len(vector) != self.settings.embedding_dimension:
                raise ValueError(
                    f"Embedding dimension mismatch: configured "
                    f"{self.settings.embedding_dimension}, received {len(vector)}"
                )
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self.batch_size]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]


class SiliconFlowReranker:
    """Cross-encoder reranking through SiliconFlow's official rerank endpoint."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = httpx.Client(
            base_url=self.settings.siliconflow_base_url,
            headers={"Authorization": f"Bearer {self.settings.require_api_key()}"},
            timeout=self.settings.request_timeout_seconds,
        )

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError, ConnectionError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[RerankItem]:
        if not documents:
            return []
        response = self.client.post(
            "/rerank",
            json={
                "model": self.settings.rerank_model,
                "query": query,
                "documents": list(documents),
                "top_n": min(top_n, len(documents)),
                "return_documents": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return [
            RerankItem(index=int(item["index"]), score=float(item["relevance_score"]))
            for item in payload.get("results", [])
        ]

    def close(self) -> None:
        self.client.close()


def batched(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    """Public utility used by ingestion tests and scripts."""
    for start in range(0, len(values), size):
        yield values[start : start + size]
