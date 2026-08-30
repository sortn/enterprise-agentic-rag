from retrieval.hybrid_retriever import HybridRetriever
from retrieval.milvus_store import SearchHit


class RetrieverSettings:
    rerank_top_k = 4
    fusion_top_k = 6
    rrf_k = 60


def hit(identifier, method):
    return SearchHit(
        id=identifier,
        score=0.5,
        text=f"text-{identifier}",
        doc_id="a" * 24,
        parent_id=f"{'a' * 24}-p0",
        source="policy.txt",
        heading="",
        locator="",
        retrieval_method=method,
    )


class FailingHybridStore:
    def search_hybrid(self, query, vector, limit):
        raise ConnectionError("hybrid unavailable")

    def search_dense(self, vector, limit):
        return [hit("shared", "dense"), hit("dense", "dense")]

    def search_sparse(self, query, limit):
        return [hit("shared", "bm25"), hit("sparse", "bm25")]


class Embeddings:
    def embed_query(self, query):
        return [0.1, 0.2]


def test_hybrid_failure_degrades_to_local_rrf():
    retriever = HybridRetriever(
        FailingHybridStore(), Embeddings(), object(), RetrieverSettings()
    )
    results = retriever.retrieve("报销制度", mode="hybrid", top_k=3)

    assert results[0].id == "shared"
    assert all(item.retrieval_method == "fallback_rrf" for item in results)


class BrokenEmbeddings:
    def embed_query(self, query):
        raise TimeoutError("embedding unavailable")


def test_embedding_failure_degrades_to_bm25():
    retriever = HybridRetriever(
        FailingHybridStore(), BrokenEmbeddings(), object(), RetrieverSettings()
    )
    results = retriever.retrieve("NX-MEET-PRO", mode="hybrid", top_k=2)

    assert [item.id for item in results] == ["shared", "sparse"]
    assert all(item.retrieval_method == "bm25_degraded" for item in results)
