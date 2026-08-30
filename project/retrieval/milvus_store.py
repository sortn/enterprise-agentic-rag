"""Milvus collection management and dense/BM25/RRF search operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable, Literal

from pymilvus import AnnSearchRequest, DataType, Function, FunctionType, MilvusClient, RRFRanker

from config import Settings, get_settings


@dataclass
class ChunkRecord:
    id: str
    doc_id: str
    parent_id: str
    source: str
    heading: str
    locator: str
    text: str
    dense: list[float]


@dataclass
class SearchHit:
    id: str
    score: float
    text: str
    doc_id: str
    parent_id: str
    source: str
    heading: str
    locator: str
    retrieval_method: str
    rerank_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


OUTPUT_FIELDS = ["doc_id", "parent_id", "source", "heading", "locator", "text"]


class MilvusStore:
    """Owns the collection schema and exposes each retrieval stage separately."""

    def __init__(self, settings: Settings | None = None, client: MilvusClient | None = None):
        self.settings = settings or get_settings()
        self.collection_name = self.settings.milvus_collection
        self.client = client or MilvusClient(
            uri=self.settings.milvus_uri,
            token=self.settings.milvus_token or None,
        )

    def ensure_collection(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.client.load_collection(self.collection_name)
            return

        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=64)
        schema.add_field("parent_id", DataType.VARCHAR, max_length=64)
        schema.add_field("source", DataType.VARCHAR, max_length=512)
        schema.add_field("heading", DataType.VARCHAR, max_length=1024)
        schema.add_field("locator", DataType.VARCHAR, max_length=256)
        schema.add_field(
            "text",
            DataType.VARCHAR,
            max_length=8192,
            enable_analyzer=True,
            analyzer_params={"tokenizer": "jieba"},
        )
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self.settings.embedding_dimension)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(
            Function(
                name="text_bm25",
                input_field_names=["text"],
                output_field_names=["sparse"],
                function_type=FunctionType.BM25,
            )
        )

        indexes = self.client.prepare_index_params()
        indexes.add_index(field_name="dense", index_type="AUTOINDEX", metric_type="COSINE")
        indexes.add_index(
            field_name="sparse",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
            params={"inverted_index_algo": "DAAT_MAXSCORE", "bm25_k1": 1.2, "bm25_b": 0.75},
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=indexes,
            consistency_level="Bounded",
        )
        self.client.load_collection(self.collection_name)

    def insert(self, records: Iterable[ChunkRecord]) -> int:
        rows = [asdict(record) for record in records]
        if not rows:
            return 0
        self.client.insert(collection_name=self.collection_name, data=rows)
        self.client.flush(collection_name=self.collection_name)
        return len(rows)

    def delete_document(self, doc_id: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{24}", doc_id):
            raise ValueError("Invalid document id")
        self.client.delete(
            collection_name=self.collection_name,
            filter=f'doc_id == "{doc_id}"',
        )

    def clear(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)
        self.ensure_collection()

    def list_documents(self) -> list[dict[str, str]]:
        rows = self.client.query(
            collection_name=self.collection_name,
            filter='doc_id != ""',
            output_fields=["doc_id", "source"],
            limit=16384,
        )
        unique = {(row["doc_id"], row["source"]) for row in rows}
        return [{"doc_id": doc_id, "source": source} for doc_id, source in sorted(unique)]

    def search_dense(self, vector: list[float], limit: int | None = None) -> list[SearchHit]:
        result = self.client.search(
            collection_name=self.collection_name,
            data=[vector],
            anns_field="dense",
            search_params={"metric_type": "COSINE", "params": {}},
            limit=limit or self.settings.dense_top_k,
            output_fields=OUTPUT_FIELDS,
        )
        return self._convert_hits(result, "dense")

    def search_sparse(self, query: str, limit: int | None = None) -> list[SearchHit]:
        result = self.client.search(
            collection_name=self.collection_name,
            data=[query],
            anns_field="sparse",
            search_params={"metric_type": "BM25", "params": {}},
            limit=limit or self.settings.sparse_top_k,
            output_fields=OUTPUT_FIELDS,
        )
        return self._convert_hits(result, "bm25")

    def search_hybrid(
        self,
        query: str,
        vector: list[float],
        limit: int | None = None,
    ) -> list[SearchHit]:
        dense_request = AnnSearchRequest(
            data=[vector],
            anns_field="dense",
            param={"metric_type": "COSINE", "params": {}},
            limit=self.settings.dense_top_k,
        )
        sparse_request = AnnSearchRequest(
            data=[query],
            anns_field="sparse",
            param={"metric_type": "BM25", "params": {}},
            limit=self.settings.sparse_top_k,
        )
        result = self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=[dense_request, sparse_request],
            ranker=RRFRanker(k=self.settings.rrf_k),
            limit=limit or self.settings.fusion_top_k,
            output_fields=OUTPUT_FIELDS,
        )
        return self._convert_hits(result, "hybrid_rrf")

    @staticmethod
    def _convert_hits(raw_result: Any, method: Literal["dense", "bm25", "hybrid_rrf"]) -> list[SearchHit]:
        hits = raw_result[0] if raw_result else []
        converted: list[SearchHit] = []
        for hit in hits:
            entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
            get_value = entity.get if hasattr(entity, "get") else lambda key, default="": default
            hit_id = hit.get("id") if isinstance(hit, dict) else getattr(hit, "id", "")
            score = hit.get("distance", hit.get("score", 0.0)) if isinstance(hit, dict) else getattr(hit, "distance", 0.0)
            converted.append(
                SearchHit(
                    id=str(hit_id),
                    score=float(score),
                    text=str(get_value("text", "")),
                    doc_id=str(get_value("doc_id", "")),
                    parent_id=str(get_value("parent_id", "")),
                    source=str(get_value("source", "")),
                    heading=str(get_value("heading", "")),
                    locator=str(get_value("locator", "")),
                    retrieval_method=method,
                )
            )
        return converted
